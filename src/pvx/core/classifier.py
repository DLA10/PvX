import hashlib
import re
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from pvx.models.base import BaseModelInterface

@dataclass
class ClassificationResult:
    category: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    source: str = ""           # cache | cli | keyword_fallback | keyword_fallback_default
    classified_by: str = ""    # "claude" | "keyword" | "cache"
    all_matches: List[str] = field(default_factory=list)
    error: Optional[str] = None

class TaskClassifier:
    """
    Classification chain — keyword-FIRST to save Claude tokens:

    1. Keyword     → pattern matching with priority ordering
                     confidence ≥ 0.5 AND clear single match → accept (free)
                     zero matches OR confidence < 0.5 → escalate to Claude
    2. Cache       → same prompt+result seen this session → return cached
    3. Claude      → called ONLY on ambiguous/zero-match tasks
                     subprocess call: claude --print -p "classify: {prompt}"
                     result cached for session
    """

    KEYWORD_PRIORITY = [
        "math_proof", "algorithm_design", "ml_pipeline", "oop_design",
        "debugging_logic", "chain_of_thought", "complex_code",
        "large_context", "code_review", "system_design", "docstrings",
        "boilerplate", "simple_refactor", "formatting",
    ]

    KEYWORD_PATTERNS = {
        "math_proof":        r"prove|proof|theorem|lemma|derive|derivation",
        "algorithm_design":  r"algorithm|complexity|O\(n\)|optimis|big.?o",
        "ml_pipeline":       r"pipeline|training|loss|dataset|epoch|batch|torch|tensorflow",
        "oop_design":        r"class\s+(hierarch|diagram|design|structure)|interface|abstract\s+base|design\s+pattern|inherit(ance)?|polymorphi",
        "debugging_logic":   r"\bdebug\b|\bfix\b|traceback|exception|error|crash|bug",
        "chain_of_thought":  r"reason|step.by.step|think through|analyse",
        "complex_code":      r"implement|build|create|develop|construct",
        "large_context":     r"codebase|entire repo|whole project|all files",
        "code_review":       r"review|audit|check|validate|inspect",
        "system_design":     r"architecture|design|system|component|structure",
        "docstrings":        r"docstring|document|comment|annotate",
        "boilerplate":       r"boilerplate|scaffold|template|skeleton|init",
        "simple_refactor":   r"refactor|rename|move|extract|inline",
        "formatting":        r"format|lint|style|pep8|black|prettier",
    }

    KEYWORD_CONFIDENCE_THRESHOLD = 0.6   # Below this → escalate to Claude
    DEFAULT_FALLBACK_CATEGORY = "complex_code"

    def __init__(self, cli_model: BaseModelInterface, circuit_breaker=None):
        self.cli_model = cli_model
        self._cache: Dict[str, ClassificationResult] = {}
        self.circuit_breaker = circuit_breaker

    def classify(self, prompt: str) -> ClassificationResult:
        # Level 1: Cache — same prompt this session, zero cost
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        if prompt_hash in self._cache:
            cached = self._cache[prompt_hash]
            cached.source = "cache"
            return cached

        # Level 2: Keyword matching — free, zero subprocess calls
        keyword_result = self._classify_keywords(prompt)

        if keyword_result.confidence > self.KEYWORD_CONFIDENCE_THRESHOLD:
            # High-confidence keyword match → accept, cache, return
            self._cache[prompt_hash] = keyword_result
            return keyword_result

        # Level 3: Claude escalation — only for ambiguous/zero-match cases
        if self.cli_model.is_available():
            claude_result = self._classify_via_cli(prompt, keyword_hint=keyword_result)
            if not claude_result.error:
                self._cache[prompt_hash] = claude_result
                return claude_result

        # Claude unavailable or failed → return best keyword result anyway
        self._cache[prompt_hash] = keyword_result
        return keyword_result

    def _classify_keywords(self, prompt: str) -> ClassificationResult:
        matches = []
        for category in self.KEYWORD_PRIORITY:
            if re.search(self.KEYWORD_PATTERNS[category], prompt, re.IGNORECASE):
                matches.append(category)

        if not matches:
            # Zero matches → low confidence, triggers Claude escalation
            return ClassificationResult(
                category=self.DEFAULT_FALLBACK_CATEGORY,
                source="keyword_fallback_default",
                classified_by="keyword",
                confidence=0.0,
            )

        if len(matches) == 1:
            confidence = 0.8
        elif len(matches) == 2:
            confidence = 0.65   # two matches, still above threshold — no escalation
        else:
            confidence = 0.5    # 3+ matches = genuinely ambiguous, escalate
        return ClassificationResult(
            category=matches[0],
            source="keyword_fallback",
            classified_by="keyword",
            confidence=confidence,
            all_matches=matches
        )

    def _extract_json_balanced(self, text: str) -> Optional[dict]:
        """
        Extract first complete JSON object from text using
        balanced brace depth tracking. Handles nested objects.
        """
        start = text.find('{')
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if char == '\\' and in_string:
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return None

        return None

    def _classify_via_cli(self, prompt: str,
                          keyword_hint: ClassificationResult) -> ClassificationResult:
        """
        Claude escalation for ambiguous tasks.

        Called ONLY when keyword confidence < 0.5 or zero matches.
        Provides the keyword hint so Claude can agree or override efficiently —
        this reduces Claude's reasoning burden and produces more consistent JSON.

        Prompt is designed to:
        - Give Claude a constrained category list (no free-form answers)
        - Anchor on the keyword hint (agree/override pattern is reliable)
        - Demand JSON-only output (no preamble — strips cleanly after ANSI removal)
        - Keep the prompt short to minimise tokens spent on classification
        """
        valid_categories = ", ".join(self.KEYWORD_PRIORITY + ["architecture", "final_review"])

        classification_prompt = (
            f'You are a task classifier for an AI orchestration platform.\n'
            f'A keyword classifier suggested "{keyword_hint.category}" '
            f'with {keyword_hint.confidence:.0%} confidence.\n\n'
            f'Classify the following developer task into exactly ONE of these categories:\n'
            f'{valid_categories}\n\n'
            f'Rules:\n'
            f'- Respond with JSON only. No explanation, no preamble, no markdown fences.\n'
            f'- "confidence" must be a float 0.0–1.0.\n'
            f'- "reasoning" must be one sentence maximum.\n\n'
            f'Response format:\n'
            f'{{"category": "<category>", "confidence": 0.0, "reasoning": "<one sentence>"}}\n\n'
            f'Task: {prompt}'
        )

        if self.circuit_breaker and not self.circuit_breaker.is_allowed():
            return ClassificationResult(error="CLASSIFIER_CIRCUIT_OPEN")

        result = self.cli_model.generate(prompt=classification_prompt, history=[])

        if result.error:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            return ClassificationResult(error=result.error)

        if not result.content:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            return ClassificationResult(error="CLI_EMPTY_RESPONSE")

        data = self._extract_json_balanced(result.content)
        if not data:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            return ClassificationResult(error=f"CLI_PARSE_ERROR: {result.content[:100]}")

        category = data.get("category", "").strip()
        if category not in self.KEYWORD_PRIORITY + ["architecture", "final_review"]:
            # Claude returned a category outside the allowed set — fall back
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            return ClassificationResult(
                error=f"CLI_INVALID_CATEGORY: {category}"
            )

        try:
            confidence = float(data.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7

        if self.circuit_breaker:
            self.circuit_breaker.record_success()

        return ClassificationResult(
            category=category,
            confidence=min(max(confidence, 0.0), 1.0),  # clamp to [0, 1]
            reasoning=str(data.get("reasoning", "")),
            classified_by="claude",
            source="claude-escalation",
        )
