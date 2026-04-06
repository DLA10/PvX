# PvX — Architecture Blueprint v0.9
> **Hardware-aware, consumer-first, open source agentic multi-model orchestration platform**
> Version 0.9 — Token-Efficient Single-CLI

---

## Changelog
| Version | Changes |
|---|---|
| v0.1 | Initial blueprint |
| v0.2 | Task classification, MCP reliability, error recovery, context management, security model, non-goals, known risks |
| v0.3 | Model affinity batching, zombie detection, context compressor, pynvml, VRAM preemption, shadow terminal, dry-run API, graceful MCP re-prompt |
| v0.4 | MCP-first distribution, competitive landscape, primary user sharpened, Phase 5 reordered |
| v0.5 | keyword fallback priority + tie-breaking, security bypass fixes, preemption partial output, pvx doctor, affinity starvation guard, balanced brace JSON parser, Phase 4 split 4a/4b |
| v0.6 | Claude Code subprocess invocation fully specified. estimate_completion replaced with token threshold. Tier 0 added. Tier 2 rate limit corrected. pvx doctor contradiction fixed. nvmlInit() cached. class regex tightened. .seconds → .total_seconds() fixed. |
| v0.8 | Dual CLI architecture removed. PvX now supports Claude Code. Classifier simplified. Router fallback chains simplified. Build phases consolidated to Claude Code only. Section 23 updated to single-agent build strategy. All dual-CLI assumptions audited and removed throughout. |
| v0.9 | Fixed duplicate TaskClassifier class (merge artifact). Fixed garbled architecture diagram. Inverted classification chain: keyword-first, Claude escalation only on low/zero confidence (saves tokens). Context compressor switched to Qwen-3B (free, local) instead of Claude subprocess. OllamaModel.generate switched to stream=True with register_streaming_token callback — fixing dead streaming buffer. ANSI escape code stripping added to Claude model wrapper. Dead code removed from router. Event Bus formatting glitch fixed. Tiers section restored (Tier 0 air-gapped, Tier 1 Claude). |

---

## Table of Contents
1. [What Is PvX](#1-what-is-pvx)
2. [Non-Goals v0.1](#2-non-goals-v01)
3. [Target Users](#3-target-users)
4. [Core Philosophy](#4-core-philosophy)
5. [Known Risks](#5-known-risks)
6. [System Architecture](#6-system-architecture)
7. [Component Breakdown](#7-component-breakdown)
   - 7.1 Task Classifier
   - 7.2 Task Router
   - 7.3 Task Queue Engine + Model Affinity Batching
   - 7.4 VRAM Manager + Zombie Detection + Preemption
   - 7.5 Context Compressor
   - 7.6 Conversation Store
   - 7.7 MCP Proxy + Graceful Re-prompt
   - 7.8 Event Bus
   - 7.9 Model Wrappers (base, ollama, claude)
8. [Technology Stack](#8-technology-stack)
9. [Data Flow](#9-data-flow)
10. [MCP Layer + Security Model](#10-mcp-layer--security-model)
11. [VRAM Manager — Full Specification](#11-vram-manager--full-specification)
12. [Task Queue Engine — Full Specification](#12-task-queue-engine--full-specification)
13. [Context Window Management](#13-context-window-management)
14. [Error Recovery & Resilience](#14-error-recovery--resilience)
15. [Web UI Specification](#15-web-ui-specification)
16. [Open Source Tiers](#16-open-source-tiers)
17. [Developer Observability](#17-developer-observability)
18. [Configuration-Driven Routing](#18-configuration-driven-routing)
19. [API Contracts](#19-api-contracts)
20. [Build Phases](#20-build-phases)
21. [Directory Structure](#21-directory-structure)
22. [Future Roadmap](#22-future-roadmap)
23. [Build Agent Strategy](#23-build-agent-strategy)

---

## 1. What Is PvX

### The Problem

Claude Code is the most capable agentic coding tool available today. It reads your codebase, executes commands, manages git workflows, and connects to external services via MCP. It is a powerhouse — and nobody should try to rebuild it from scratch.

But it has a critical operational flaw: **it burns premium tokens on tasks that don't need its intelligence.**

When Claude Code writes boilerplate, generates docstrings, or reformats code, those are tokens that a local 7B model could have handled for free. On a Claude Pro subscription with rate limits, this means you hit your ceiling mid-workflow — exactly when you need Claude most.

The instinct is obvious: keep the powerhouse for architecture and reasoning, delegate grunt work to local models. Several MCP servers have emerged to do exactly this. They prove the concept works with benchmarked savings of 60–95% on token consumption.

**But single-task delegation is where they stop.**

None of these tools solve what happens when you have a **multi-step workflow** on a **consumer GPU**. Consider building a feature end-to-end: you need DeepSeek-R1 to reason through the algorithm, Qwen-14B to implement it, Qwen-3B to write the docstrings, and your CLI to review the result. On a 12GB RTX 3060, only one local model fits in VRAM at a time. No existing tool manages this. No existing tool detects when a training job is competing for your GPU. No existing tool knows that downstream tasks should be held, retried, or rerouted when something fails mid-chain.

### What PvX Is

PvX is the orchestration layer that sits beneath your chosen CLI agent — Claude Code — managing everything it can't see.

**You configure one CLI. PvX works with it.**

```yaml
# pvx.config.yaml
orchestrator:
  cli: "claude"   
```

**How it ships:** PvX is an MCP server. Install it with one command, add one line to your CLI's config, and the full platform is live — VRAM manager, task queue, Web UI, everything. No Docker required. No server to host. No complex setup.

```bash
# Install
uvx install pvx

# Add to Claude Code
{ "pvx": { "command": "uvx", "args": ["pvx"] } }


# Start everything
pvx start
# → MCP server ready       (your CLI can now delegate)
# → Web UI at :8765        (open in browser)
# → VRAM manager running   (GPU monitoring starts)
# → Task queue ready       (all features live)
```

**What you get:**

- **VRAM-aware scheduling** — a state machine that polls your GPU, knows what's loaded, detects external processes, and prevents conflicts before they happen. This is the core differentiator. No other tool in this space has it.
- **Multi-step task chains with dependency resolution** — not just "delegate this one task" but "here are 6 tasks with dependencies, priorities, and failure recovery. Execute them in the right order on the right models."
- **An observable inter-model feed** — every delegation, every model swap, every MCP call is visible in real time. Existing tools are black boxes. PvX shows you exactly what happened, why a task was routed where it was, and what each model produced.
- **A real Web UI** — every competitor is CLI-only. PvX provides a browser dashboard with live VRAM monitoring, task dependency graph, direct chat per model, shadow terminal, and cost tracker.

### What PvX Is NOT
- A chat interface — OpenWebUI and LibreChat already do this well
- A prompt chaining framework — LangChain and LlamaIndex already do this
- A cloud-only orchestrator — requires no paid infrastructure to run
- A replacement for Claude Code — it orchestrates it
- A server you host — everything runs on the user's own machine
- A tool that requires both CLIs — one is enough

### Competitive Landscape

| Tool | What It Does Well | What It Doesn't Do |
|---|---|---|
| **Houtini-LM** | 93% token savings. Model routing, think-block stripping, SQLite caching, per-model prompt tuning. Most mature single-task delegator. | No VRAM management. No multi-step chains. No dependency resolution. No UI. Single-task only. |
| **Helix-Agents** | 60–80% token savings. Qdrant persistent memory. Multi-provider runtime. | No VRAM management. No task queue. No UI. Single-task only. |
| **CC Token Saver** | Simple, lightweight MCP delegation for Claude Code. Easy to install. | No routing intelligence, no VRAM awareness, no task chains, no UI. |
| **Ollama-Claude** | Up to 98.75% token savings on file-heavy workflows. | Single-task delegation only. No orchestration layer. |
| **Lok** | Rust CLI orchestration. Smart routing, debate mode, parallel subtasks. Closest to PvX's vision. | No VRAM management. CLI-only. No persistent task queue or dependency resolution. |

**Where PvX sits:**
```
                 Single-Task          Multi-Step
                 Delegation           Orchestration
No VRAM Mgmt │  Houtini-LM           Lok
             │  Helix-Agents
             │  CC Token Saver
             │  Ollama-Claude
─────────────┤
VRAM-Aware   │  (nobody)             PvX  ← here
```

### The Precise Niche PvX Owns
```
A developer hitting Claude Pro rate limits mid-workflow
who wants multi-step local model delegation on consumer
GPU hardware — with full visibility into what's happening
and zero infrastructure to manage.

No tool solves this cleanly today.
```

---

## 2. Non-Goals v0.1

To protect scope and set contributor expectations:

```
❌ Multi-user / team support          → v1.0 roadmap
❌ Authentication / access control    → v1.0 roadmap
❌ Horizontal scaling                 → v1.0 roadmap
❌ Training or fine-tuning models     → out of scope entirely
❌ Image / audio generation           → out of scope entirely
❌ Browser automation                 → out of scope entirely
❌ Mobile clients                     → out of scope entirely
❌ Windows support (v0.1)             → Linux / macOS only
❌ Auto-routing improvement / RL      → v0.2 roadmap
❌ Parallel local model execution     → v0.2 roadmap (multi-GPU)
❌ Vector database / RAG              → v0.3 roadmap
```

---

## 3. Target Users

### Primary: The Rate-Limited Power User

The developer who has a Claude Pro or Max subscription, uses Claude Code as their primary development tool, and keeps hitting token or rate limits mid-workflow. They already have Ollama installed. They've probably tried a single-task delegation MCP server and found it helpful but limited. They want a system that manages the full multi-step workflow — not just individual offloads.

**This is the user PvX is built for first.**

### Secondary Users

| User | Problem PvX Solves |
|---|---|
| **Consumer GPU developer (RTX 3060–4070)** | Existing tools don't manage VRAM when switching between a 14B and 7B model. Ollama silently falls back to CPU, destroying throughput from ~40 t/s to ~3 t/s. PvX's VRAM manager prevents this. |
| **Multi-model workflow developer** | Has tasks that need different models for different stages. No existing tool handles the dependency chain or routes failures. |
| **Cost-conscious indie developer** | API costs prohibitive. Wants intelligent routing that reserves paid Claude tokens strictly for quality gates. |
| **Developer learning multi-model workflows** | The observable feed is a teaching tool. Watch how tasks flow between models, see what each produces, understand why routing decisions were made. |
| **MLOps / DevOps engineer** | Wants AI-in-the-loop pipelines with familiar queue semantics. VRAM-aware scheduling maps to their mental model. |
| **Academic researcher** | Needs observable multi-model outputs for comparison and benchmarking. |

### Who PvX Is Not For (Yet)
- **Teams needing multi-user access** — v0.1 is single-developer only. Multi-user is v1.0.
- **Developers with multi-GPU setups** — v0.1 targets single consumer GPU. Multi-GPU is v0.2.
- **Production serving workloads** — PvX is a development tool, not an inference server.

---

## 4. Core Philosophy

```
1. Hardware First
   Every design decision respects consumer GPU constraints.
   VRAM is a first-class citizen, not an afterthought.
   Model swaps are expensive — minimise them by design.

2. Token-Saving by Design
   Claude tokens are spent only where they add irreplaceable value.
   Keyword classifier handles clear tasks for free.
   Qwen-3B handles context compression for free.
   Claude reserved for: ambiguous classification, architecture,
   quality gates, large-context tasks.

3. Observable by Default
   Every inter-model communication is visible to the user.
   Every system action is surfaced in the Shadow Terminal.
   Every routing decision is explainable via the dry-run API.
   No black boxes. Full audit trail.

4. Proxy Power for Local LLMs
   Local models gain MCP superpowers through the platform.
   They don't need native MCP — PvX proxies and validates it.
   Hallucinated tool calls trigger graceful re-prompt, not hard failure.

5. Sequential by Design, Parallel by Choice
   Default: sequential local model queue (consumer hardware)
   Batched by model affinity to minimise cold start latency.
   Optional in v0.2: parallel execution for multi-GPU setups.

6. Resilient by Default
   Zombie tasks are auto-detected and recovered.
   Circuit breakers protect against cascading failures.
   Every failure mode has an explicit handling strategy.
```

---

## 5. Known Risks

Honest engineering assessment of the hardest problems:

| Risk | Severity | Mitigation |
|---|---|---|
| Task classifier accuracy | HIGH | Keyword-first chain: keyword handles clear cases (confidence ≥ 0.5), Claude escalation for ambiguous/zero-match only. Saves tokens while maintaining accuracy where it matters. |
| MCP proxy JSON reliability at Q4 quantisation | HIGH | Balanced brace JSON parser + graceful re-prompt loop (max 3 retries) |
| Ollama cold start latency (5–15s per swap) | HIGH | Model affinity batching with starvation guard |
| Zombie task locking VRAM indefinitely | HIGH | Heartbeat monitor with 60s GPU utilisation timeout |
| SQLite concurrent write contention | MEDIUM | WAL mode + serialised write queue |
| Context overflow in small local models | MEDIUM | Context compressor triggered at 70% of model context limit |
| Security: AI-generated SQL injection / path traversal / command injection | HIGH | Input sanitisation layer — is_relative_to() for paths, keyword + pattern matching for SQL/commands. Adversarial review required before v0.1 ship. |
| Routing rules becoming stale as models improve | LOW | Configuration-driven routing, not hardcoded |
| tiktoken token count inaccuracy for local models | LOW | tiktoken tuned for OpenAI BPE vocabulary. Qwen/DeepSeek counts may be off ±15%. 70% compression threshold provides buffer. v0.2: per-model tokeniser. |
| Preemption partial output loss | MEDIUM | Explicit save/resume strategy: save partial if >20% complete, resume with continuation prompt |

---

## 6. System Architecture

```
╔══════════════════════════════════════════════════════════════════════╗
║                          PvX PLATFORM                               ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║   USER ENTRY POINTS                                                  ║
║   ┌─────────────┐   ┌──────────────────────────────────────────┐    ║
║   │   Web UI    │   │         Claude Code Orchestrator         │    ║
║   │  (Browser)  │   │    (Terminal — primary entry point)      │    ║
║   └──────┬──────┘   └────────────────────┬─────────────────────┘    ║
║          │                               │                           ║
║          └───────────────────────────────┘                           ║
║                              │                                       ║
║                              ▼                                       ║
║   ┌──────────────────────────────────────────────────────────────┐  ║
║   │                      MCP SERVER                              │  ║
║   │                    (Core of PvX)                            │  ║
║   │                                                              │  ║
║   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  ║
║   │  │   Task       │  │    Task      │  │  VRAM Manager    │  │  ║
║   │  │  Classifier  │  │   Router     │  │  + Zombie Det.   │  │  ║
║   │  └──────────────┘  └──────────────┘  │  + Preemption    │  │  ║
║   │                                       └──────────────────┘  │  ║
║   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  ║
║   │  │    Task      │  │   Context    │  │   MCP Proxy      │  │  ║
║   │  │Queue+Batching│  │  Compressor  │  │  + Re-prompt     │  │  ║
║   │  └──────────────┘  └──────────────┘  └──────────────────┘  │  ║
║   │                                                              │  ║
║   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  ║
║   │  │  Conv Store  │  │  Event Bus   │  │  Security Layer  │  │  ║
║   │  └──────────────┘  └──────────────┘  └──────────────────┘  │  ║
║   └──────────────────────────┬───────────────────────────────────┘  ║
║                              │                                       ║
║          ┌───────────────────┼───────────────────┐                  ║
║          ▼                   ▼                   ▼                  ║
║   ┌─────────────┐   ┌──────────────────┐  ┌──────────────────┐     ║
║   │ CLOUD LAYER │   │   LOCAL LAYER    │  │  SYSTEM LAYER    │     ║
║   │             │   │    (Ollama)      │  │                  │     ║
║   │ Anthropic   │   │                  │  │  File System     │     ║
║   │             │   │  Qwen-14B  128K  │  │  Terminal        │     ║
║   │             │   │  DeepSeek   32K  │  │  Git             │     ║
║   │ Parallel ✅  │   │  Qwen-3B    32K  │  │  PostgreSQL      │     ║
║   │             │   │                  │  │  Discord         │     ║
║   │             │   │  Sequential      │  │  GitHub          │     ║
║   │             │   │  + Batched ✅    │  │                  │     ║
║   └─────────────┘   └──────────────────┘  └──────────────────┘     ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## 7. Component Breakdown

### 7.1 Task Classifier

**The problem:** Who classifies an incoming task as "math_proof" vs "complex_code"?
**The answer:** Claude Code with keyword fallback when unavailable.

```python
@dataclass
class ClassificationResult:
    category: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    source: str = ""           # cache | cli | keyword_fallback | keyword_fallback_default
    classified_by: str = ""    # "claude" | "keyword" | "cache"
    all_matches: List[str] = field(default_factory=list)
    error: Optional[str] = None
```

```python
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

    Rationale: PvX exists to SAVE Claude tokens. Routing every task through
    Claude for classification before any local model work is the opposite of
    that goal. Most tasks (docstrings, boilerplate, formatting) are clearly
    classifiable by keyword. Claude escalation is reserved for genuinely
    ambiguous prompts where keyword matching fails or produces low confidence.
    At 40 tasks/session, this reduces Claude classification calls from 40 to
    roughly 5–10 (the ambiguous ones only).
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

    KEYWORD_CONFIDENCE_THRESHOLD = 0.5   # Below this → escalate to Claude
    DEFAULT_FALLBACK_CATEGORY = "complex_code"

    def __init__(self, cli_model: BaseModel):
        self.cli_model = cli_model
        self._cache: dict[str, ClassificationResult] = {}

    def classify(self, prompt: str) -> ClassificationResult:
        # Level 1: Cache — same prompt this session, zero cost
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        if prompt_hash in self._cache:
            cached = self._cache[prompt_hash]
            cached.source = "cache"
            return cached

        # Level 2: Keyword matching — free, zero subprocess calls
        keyword_result = self._classify_keywords(prompt)

        if keyword_result.confidence >= self.KEYWORD_CONFIDENCE_THRESHOLD:
            # High-confidence keyword match → accept, cache, return
            self._cache[prompt_hash] = keyword_result
            return keyword_result

        # Level 3: Claude escalation — only for ambiguous/zero-match cases
        # This is the expensive path. Keep it rare.
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
                confidence=0.0,       # 0.0 always triggers Claude escalation
            )

        confidence = 0.8 if len(matches) == 1 else 0.5
        return ClassificationResult(
            category=matches[0],
            source="keyword_fallback",
            classified_by="keyword",
            confidence=confidence,    # 0.5 on multi-match → Claude escalation
            all_matches=matches
        )

    def _classify_via_cli(self, prompt: str,
                           keyword_hint: ClassificationResult) -> ClassificationResult:
        """
        Claude escalation for ambiguous tasks.
        Provides keyword hint so Claude can agree or override efficiently.
        Called ONLY when keyword confidence < 0.5 or zero matches.
        """
        classification_prompt = f"""
You are a task classifier for an AI orchestration platform.
A keyword classifier suggested "{keyword_hint.category}"
with {keyword_hint.confidence:.0%} confidence.

Classify the following developer task into exactly ONE category:
math_proof, algorithm_design, debugging_logic, chain_of_thought,
ml_pipeline, oop_design, system_design, complex_code, code_review,
docstrings, boilerplate, formatting, simple_refactor, large_context,
architecture, final_review

Respond with JSON only, no preamble:
{{"category": "<category>", "confidence": 0.0-1.0, "reasoning": "one sentence"}}

Task: {prompt}
"""
        result = self.cli_model.generate(prompt=classification_prompt, history=[])
        if result.error:
            return ClassificationResult(error=result.error)

        try:
            data = self._extract_json_balanced(result.content)
            if not data:
                return ClassificationResult(error="CLI_PARSE_ERROR")
            return ClassificationResult(
                category=data["category"],
                confidence=float(data.get("confidence", 0.7)),
                reasoning=data.get("reasoning", ""),
                classified_by=self.cli_model.name(),
                source="claude-escalation"
            )
        except (KeyError, ValueError):
            return ClassificationResult(error=f"CLI_PARSE_ERROR: {result.content[:100]}")
```

### 7.2 Task Router

Routes classified tasks to the optimal model with fallback chain.

Claude Code is
treated as a single cloud model in the routing table. The router doesn't
care which CLI you chose — it just knows "local model" or "Claude Code".

```python
class TaskRouter:
    """
    Routing is configuration-driven (pvx.config.yaml), not hardcoded.
    Default routing table shipped as sensible defaults.
    Users override per their hardware and model choices.

    CLI_MODEL is a constant that resolves to whichever CLI the user configured.
    At startup: CLI_MODEL = "claude"
    """

    DEFAULT_ROUTING = {
        # Reasoning tasks → DeepSeek-R1
        "math_proof":        "deepseek-r1:7b",
        "algorithm_design":  "deepseek-r1:7b",
        "debugging_logic":   "deepseek-r1:7b",
        "chain_of_thought":  "deepseek-r1:7b",

        # Complex coding → Qwen-14B
        "ml_pipeline":       "qwen2.5-coder:14b",
        "oop_design":        "qwen2.5-coder:14b",
        "system_design":     "qwen2.5-coder:14b",
        "complex_code":      "qwen2.5-coder:14b",
        "code_review":       "qwen2.5-coder:14b",

        # Grunt work → Qwen-3B
        "docstrings":        "qwen2.5-coder:3b",
        "boilerplate":       "qwen2.5-coder:3b",
        "formatting":        "qwen2.5-coder:3b",
        "simple_refactor":   "qwen2.5-coder:3b",

        # Large context / quality → Claude Code
        # (Claude: 200K context window + superior reasoning)
        "large_context":     "claude",
        "codebase_analysis": "claude",
        "architecture":      "claude",
        "final_review":      "claude",
    }

    FALLBACK_CHAIN = {
        # Local model VRAM unavailable → fall back to Claude Code
        "deepseek-r1:7b":      ["claude"],
        "qwen2.5-coder:14b":   ["claude"],
        "qwen2.5-coder:3b":    ["qwen2.5-coder:14b", "claude"],
        # CLI unavailable → hard fail with user alert (no local fallback for CLI tasks)
        "claude":      [],
    }

    def route(self, task: Task) -> str:
        primary = self.DEFAULT_ROUTING[task.category]

        # Check VRAM availability for local models only
        # "claude" routes directly — no VRAM check needed
        if is_local_model(primary):
            if not vram_manager.can_load(primary):
                for fallback in self.FALLBACK_CHAIN[primary]:
                    actual = "claude" if fallback == "claude" else fallback
                    if fallback == "claude" or vram_manager.can_load(fallback):
                        log_routing_decision(primary, actual, reason="VRAM_UNAVAILABLE")
                        return actual

        return primary
```

### 7.3 Task Queue Engine + Model Affinity Batching

**The Ollama cold start problem:** Switching from Qwen-14B to DeepSeek-R1 takes 5–15 seconds on consumer PCIe lanes.

**Solution:** Model Affinity Batching — group same-model tasks together before strict ordering.

**The starvation problem:** A constant stream of Qwen-14B tasks could starve a DeepSeek task indefinitely if the affinity window keeps resetting. Fix: explicit starvation guard + batch limits.

```python
class TaskQueueEngine:

    # Affinity batching limits
    AFFINITY_BATCH_MAX_TASKS   = 10     # Max tasks in one affinity batch
    AFFINITY_BATCH_MAX_SECONDS = 300    # Max 5 minutes per affinity batch
    STARVATION_TIMEOUT_SECONDS = 300    # Any task waiting >5min bypasses affinity

    # Preemption partial output threshold.
    # Cannot calculate % completion when streaming (unknown total length).
    # Use token count as proxy instead — configurable in pvx.config.yaml.
    PARTIAL_SAVE_MIN_TOKENS = 150

    def __init__(self):
        self.current_batch_size: int = 0
        self.batch_start: datetime = datetime.now()
        self.affinity_reset: bool = False
        self._streaming_buffers: dict[str, str] = {}  # task_id → partial output

    def reset_affinity_batch(self):
        self.current_batch_size = 0
        self.batch_start = datetime.now()
        self.affinity_reset = True

    def register_streaming_token(self, task_id: str, token: str):
        """Called by Ollama streaming callback on each token."""
        if task_id not in self._streaming_buffers:
            self._streaming_buffers[task_id] = ""
        self._streaming_buffers[task_id] += token

    def get_current_output(self, task: Task) -> str:
        """
        Returns partial output accumulated so far for a running task.
        The Ollama streaming callback feeds tokens into _streaming_buffers
        via register_streaming_token() on every token received.
        This is how the queue engine accesses mid-generation output
        without blocking the generation stream.
        """
        return self._streaming_buffers.get(task.id, "")

    def get_next_task(self) -> Optional[Task]:
        """
        Scheduling priority order:
        0. Starvation guard     — tasks waiting > 5min bypass all affinity logic
        1. P5 Critical tasks    — immediate, regardless of model affinity
        2. Affinity batch check — reset batch if limits exceeded
        3. Model affinity       — prefer tasks matching current loaded model
        4. Priority within batch
        5. created_at FIFO within same priority
        """
        pending = self.get_pending_with_deps_resolved()
        now = datetime.now()

        # Step 0: Starvation guard — always check first
        # CRITICAL: use .total_seconds() NOT .seconds
        # .seconds only returns the seconds component of a timedelta.
        # A task created 6min 30s ago: .seconds == 30, .total_seconds() == 390.
        # Using .seconds causes the guard to fire on tasks <60s old
        # and never fire on tasks >1min old. Both are wrong.
        starved = [
            t for t in pending
            if (now - t.created_at).total_seconds() > self.STARVATION_TIMEOUT_SECONDS
        ]
        if starved:
            winner = min(starved, key=lambda t: t.created_at)
            self.emit_event("STARVATION_BYPASS", {
                "task_id": winner.id,
                "waited_seconds": (now - winner.created_at).total_seconds(),
                "bypassed_model": vram_manager.get_loaded_model()
            })
            return winner

        # Step 1: Critical tasks always go first
        critical = [t for t in pending if t.priority == 5]
        if critical:
            return max(critical, key=lambda t: t.priority)

        # Step 2: Check affinity batch limits (also use .total_seconds())
        batch_size_exceeded = self.current_batch_size >= self.AFFINITY_BATCH_MAX_TASKS
        batch_time_exceeded = (
            (now - self.batch_start).total_seconds() >= self.AFFINITY_BATCH_MAX_SECONDS
        )
        if batch_size_exceeded or batch_time_exceeded:
            self.reset_affinity_batch()

        # Step 3: Model affinity — prefer tasks matching current loaded model
        current_model = vram_manager.get_loaded_model()
        if current_model and not self.affinity_reset:
            affinity_tasks = [t for t in pending if t.model == current_model]
            if affinity_tasks:
                self.current_batch_size += 1
                return max(affinity_tasks,
                           key=lambda t: (t.priority, -t.created_at.timestamp()))

        # Step 4: No affinity match — pick highest priority available
        return max(pending, key=lambda t: (t.priority, -t.created_at.timestamp()))

    def should_preempt(self, incoming: Task, running: Task) -> bool:
        """
        VRAM Preemption rules:
        P5 incoming + P1/P2/P3 running → Preempt
        P5 incoming + P4/P5 running    → No preemption
        P4 incoming + P1 running       → Preempt after current generation
        """
        if incoming.priority == 5 and running.priority <= 3:
            return True
        if incoming.priority == 4 and running.priority == 1:
            return True
        return False

    def handle_preemption(self, incoming: Task, running: Task):
        """
        Partial output strategy on preemption.

        We cannot calculate % completion when streaming tokens from Ollama
        because we don't know the total output length in advance.
        Use token count as an implementable proxy instead.

        < PARTIAL_SAVE_MIN_TOKENS generated → Discard, restart from scratch
        ≥ PARTIAL_SAVE_MIN_TOKENS generated → Save partial, resume with
                                               continuation prompt
        """
        tokens_generated = running.tokens_generated_so_far  # tracked during streaming

        if tokens_generated < self.PARTIAL_SAVE_MIN_TOKENS:
            running.partial_output = None
            running.status = "preempted"
            running.preempted_at = datetime.now()

        else:
            running.partial_output = self.get_current_output(running)
            running.status = "preempted"
            running.preempted_at = datetime.now()
            running.resume_prompt = (
                "[PARTIAL OUTPUT FROM PREVIOUS ATTEMPT — CONTINUE FROM HERE]\n"
                f"{running.partial_output}\n"
                "[END PARTIAL — CONTINUE THE IMPLEMENTATION]"
            )

        self.emit_event("TASK_PREEMPTED", {
            "task_id": running.id,
            "tokens_generated": tokens_generated,
            "partial_saved": running.partial_output is not None,
            "preempted_by": incoming.id
        })


class Task:
    id: str
    model: str
    prompt: str
    category: str
    status: Literal["pending", "running", "done", "failed", "blocked",
                    "timeout", "preempted", "zombie"]
    priority: int
    depends_on: List[str]
    requires_vram: bool
    requires_system_idle: bool
    retry_count: int
    max_retries: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    last_heartbeat: Optional[datetime]
    output: Optional[str]
    tokens_generated_so_far: int                # Tracked during streaming
                                                # Used for partial output threshold
    partial_output: Optional[str]               # Saved on preemption if ≥ PARTIAL_SAVE_MIN_TOKENS
    resume_prompt: Optional[str]                # Continuation prompt for resumed tasks
    resumed_from_partial: bool                  # Flag for monitoring
    error: Optional[str]
    preempted_at: Optional[datetime]
    context_was_compressed: bool
```

### 7.4 VRAM Manager — Full State Machine + Zombie Detection + Preemption

```python
class VRAMManager:

    # Model VRAM requirements in MB
    MODEL_VRAM_MB = {
        "qwen2.5-coder:14b":  8700,
        "deepseek-r1:7b":     4500,
        "qwen2.5-coder:3b":   2000,
    }
    SAFETY_BUFFER_MB = 512

    # GPU utilisation zombie detection
    ZOMBIE_TIMEOUT_SECONDS = 60
    ZOMBIE_UTILISATION_THRESHOLD = 2  # % — below this = idle

    class State(Enum):
        IDLE      = "idle"
        LOADED    = "loaded"
        RUNNING   = "running"
        EXTERNAL  = "external"
        PRESSURE  = "pressure"
        ZOMBIE    = "zombie"

    def __init__(self):
        # Initialise NVML once at startup, cache handle.
        # nvmlInit() must NOT be called on every poll — it adds overhead
        # and can leak handles. Call once here, nvmlShutdown() on teardown.
        try:
            pynvml.nvmlInit()
            self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._nvml_available = True
        except pynvml.NVMLError:
            self._nvml_available = False
            # Fall back to nvidia-smi subprocess

    def shutdown(self):
        """Call on platform teardown."""
        if self._nvml_available:
            pynvml.nvmlShutdown()

    def poll(self) -> VRAMState:
        """
        Primary: pynvml with cached handle (low overhead, no subprocess)
        Fallback: nvidia-smi subprocess parsing
        Poll interval: 2 seconds
        """
        if self._nvml_available:
            return self._poll_pynvml()
        return self._poll_nvidia_smi()

    def _poll_pynvml(self) -> VRAMState:
        # Use cached handle — do NOT call nvmlInit() here
        mem  = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
        procs = pynvml.nvmlDeviceGetComputeRunningProcesses(self._nvml_handle)

        return VRAMState(
            total_mb=mem.total // 1024 // 1024,
            used_mb=mem.used // 1024 // 1024,
            free_mb=mem.free // 1024 // 1024,
            gpu_utilisation_pct=util.gpu,
            running_pids=[p.pid for p in procs],
        )

    def detect_zombie(self, running_task: Task, state: VRAMState) -> bool:
        """
        Zombie condition:
          - Task marked RUNNING in queue
          - GPU utilisation < 2% for > 60 seconds
          - Time since task started > 60 seconds

        CRITICAL: use .total_seconds() NOT .seconds
        .seconds only returns the seconds component of a timedelta.
        A task running for 6min 30s: .seconds == 30, .total_seconds() == 390.
        Using .seconds means the zombie detector never fires for tasks
        running longer than 60 seconds — the exact case it's meant to catch.
        """
        if running_task.status != "running":
            return False
        if state.gpu_utilisation_pct > self.ZOMBIE_UTILISATION_THRESHOLD:
            return False
        elapsed = (datetime.now() - running_task.started_at).total_seconds()
        return elapsed > self.ZOMBIE_TIMEOUT_SECONDS

    def handle_zombie(self, task: Task):
        """Recovery sequence for zombie tasks."""
        self.kill_ollama_process()           # Force unload
        task.status = "timeout"
        task.error = "ZOMBIE_DETECTED: GPU idle > 60s while task RUNNING"
        self.emit_event("ZOMBIE_DETECTED", task)
        self.alert_user(task)

        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = "pending"          # Re-queue
            task.started_at = None
        else:
            task.status = "failed"

    def can_load(self, model: str) -> bool:
        state = self.poll()
        required = self.MODEL_VRAM_MB.get(model, 0)
        return state.free_mb >= required + self.SAFETY_BUFFER_MB

    def detect_external(self, state: VRAMState) -> bool:
        """Detect non-Ollama processes using VRAM (e.g. training jobs)."""
        ollama_pids = self.get_ollama_pids()
        external_pids = [p for p in state.running_pids if p not in ollama_pids]
        return len(external_pids) > 0
```

### 7.5 Context Compressor

**The problem:** Local models have small context windows. Passing full conversation history overflows them silently, causing degraded or incoherent outputs.

```python
class ContextCompressor:
    """
    Context limits per model:
    ┌──────────────────────┬──────────┬────────────────────────┐
    │ Model                │ Context  │ Compression Threshold  │
    ├──────────────────────┼──────────┼────────────────────────┤
    │ qwen2.5-coder:3b     │  32K     │  22K (70%)             │
    │ deepseek-r1:7b       │  32K     │  22K (70%)             │
    │ qwen2.5-coder:14b    │  128K    │  90K (70%)             │
        │ claude          │  200K │  140K (rarely triggers)│
    └──────────────────────┴──────────┴────────────────────────┘

    When history_tokens > threshold:
      → Use Qwen-3B (local, free) to summarise history
      → Keep summary + last 5 messages verbatim
      → Log CONTEXT_COMPRESSED event to Feed
      → Mark task.context_was_compressed = True

    Why Qwen-3B for summarisation, NOT Claude?
      → Qwen-3B is already in the stack, costs zero tokens
      → Compression is already loaded or cheap to load (2GB VRAM)
      → "Good enough" summarisation is all that's needed for windowing
      → Using Claude for compression contradicts the token-saving goal:
        a session with 15 compressions = 15 extra Claude subprocess calls
      → If Qwen-3B is not loaded and VRAM is tight, skip compression
        and log a warning rather than burning Claude tokens
    """

    MODEL_CONTEXT_LIMITS = {
        "qwen2.5-coder:3b":   32_000,
        "deepseek-r1:7b":     32_000,
        "qwen2.5-coder:14b":  128_000,
        # claude context limit read from config at runtime
        # claude: 200_000
    }
    COMPRESSION_THRESHOLD = 0.70
    COMPRESSION_LOCAL_MODEL = "qwen2.5-coder:3b"  # Free, local summariser

    SUMMARY_PROMPT = """
    You are summarising a conversation history for context compression.
    The following messages will be sent to a model with a limited context window.
    Produce a dense, factual summary preserving:
    - All decisions made
    - All code written (reference filenames, not full code)
    - All errors encountered and their resolutions
    - Current state of the task
    - What remains to be done

    Be concise. Omit pleasantries. Preserve technical detail.
    Target: under 2000 tokens.

    History:
    {history}
    """

    def maybe_compress(self, model: str, history: List[Message]) -> List[Message]:
        limit = self.MODEL_CONTEXT_LIMITS.get(model, 32_000)
        threshold = int(limit * self.COMPRESSION_THRESHOLD)
        history_tokens = self.count_tokens(history)

        if history_tokens <= threshold:
            return history  # No compression needed

        # Use Qwen-3B locally — free, zero Claude tokens
        # If VRAM is too tight to load Qwen-3B, skip compression with warning
        if not vram_manager.can_load(self.COMPRESSION_LOCAL_MODEL):
            self.emit_event("CONTEXT_COMPRESSION_SKIPPED", {
                "model": model,
                "history_tokens": history_tokens,
                "reason": "VRAM_INSUFFICIENT_FOR_COMPRESSOR"
            })
            return history  # Return uncompressed — better than burning Claude tokens

        summary_result = ollama.chat(
            model=self.COMPRESSION_LOCAL_MODEL,
            messages=[{"role": "user", "content":
                self.SUMMARY_PROMPT.format(history=self.format_history(history))
            }],
            stream=False
        )
        summary = summary_result.message.content

        compressed = [
            Message(role="system", content=f"[CONTEXT SUMMARY]\n{summary}"),
            *history[-5:]  # Keep last 5 messages verbatim
        ]

        self.emit_event("CONTEXT_COMPRESSED", {
            "model": model,
            "original_tokens": history_tokens,
            "compressed_tokens": self.count_tokens(compressed),
            "reduction_pct": round((1 - len(compressed)/len(history)) * 100, 1)
        })

        return compressed
```

### 7.6 Conversation Store

```python
class ConversationStore:
    """
    Storage: SQLite with WAL mode enabled on startup.
    WAL mode prevents database-is-locked errors under concurrent
    async reads (UI) and writes (event bus, task executor).

    Initialisation:
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

    Schema:
    ┌──────────────────────────────────────────────┐
    │ sessions  (id, project, created_at, metadata)│
    │ messages  (id, session_id, model, role,      │
    │            content, token_count, timestamp)  │
    │ events    (id, session_id, from_model,       │
    │            to_model, type, payload,          │
    │            timestamp)                        │
    │ tasks     (id, session_id, model, status,    │
    │            priority, depends_on, created_at, │
    │            started_at, completed_at, error)  │
    └──────────────────────────────────────────────┘

    Write serialisation: all writes go through a single
    async queue to prevent WAL contention.
    """
```

### 7.7 MCP Proxy + Graceful Re-prompt Loop

**The problem:** Local LLMs at Q4 quantisation produce unreliable JSON. They also hallucinate tool names.

**Solution:** Constrained decoding for JSON + graceful re-prompt for hallucinated tools.

```python
class MCPProxy:

    MAX_TOOL_RETRIES = 3

    def execute_tool_call(self, model_output: str, available_tools: List[str],
                          model: str, task: Task) -> ToolResult:

        # Step 1: Parse tool call from model output
        tool_call = self.parse_tool_call(model_output)

        if tool_call is None:
            return ToolResult(error="NO_TOOL_CALL_DETECTED")

        # Step 2: Validate tool exists
        if tool_call.name not in available_tools:
            return self.graceful_reprompt(
                model=model,
                task=task,
                attempted_tool=tool_call.name,
                available_tools=available_tools,
                attempt=1
            )

        # Step 3: Security validation before execution
        if not self.security_layer.validate(tool_call):
            return ToolResult(error=f"SECURITY_REJECTED: {tool_call.name}")

        # Step 4: Execute the MCP call
        try:
            result = self.mcp_registry.execute(tool_call)
            self.emit_event("MCP_CALL_SUCCESS", tool_call)
            return result
        except Exception as e:
            self.emit_event("MCP_CALL_FAILED", {"tool": tool_call.name, "error": str(e)})
            return ToolResult(error=str(e))

    def graceful_reprompt(self, model, task, attempted_tool,
                          available_tools, attempt) -> ToolResult:
        """
        Graceful re-prompt loop for hallucinated tool calls.
        Max 3 attempts before failing task with MCP_HALLUCINATION error.
        """
        if attempt > self.MAX_TOOL_RETRIES:
            self.emit_event("MCP_HALLUCINATION_MAX_RETRIES", {
                "model": model,
                "attempted_tool": attempted_tool,
                "task_id": task.id
            })
            task.status = "failed"
            task.error = f"MCP_HALLUCINATION: model called '{attempted_tool}' " \
                         f"{self.MAX_TOOL_RETRIES} times despite correction"
            return ToolResult(error=task.error)

        reprompt = f"""
        The tool '{attempted_tool}' does not exist in this environment.

        Available tools are:
        {chr(10).join(f'- {t}' for t in available_tools)}

        Please retry your request using only the tools listed above.
        Attempt {attempt} of {self.MAX_TOOL_RETRIES}.
        """

        self.emit_event("MCP_REPROMPT", {
            "attempt": attempt,
            "hallucinated_tool": attempted_tool,
            "model": model
        })

        new_output = self.call_model(model, reprompt, task)
        return self.execute_tool_call(new_output, available_tools,
                                      model, task)

    def parse_tool_call(self, output: str) -> Optional[ToolCall]:
        """
        Strategy 1: Native function calling (Qwen-14B, DeepSeek-R1)
          → Parse structured JSON from chat template tool_calls field

        Strategy 2: Balanced brace JSON extraction (fallback)
          → Find outermost JSON object using depth tracking
          → Handles nested parameter objects correctly
          → NOTE: r'\{[^{}]+\}' regex deliberately NOT used here —
            it fails on nested JSON objects like:
            {"function": "query_db", "params": {"table": "users", "limit": 10}}

        Strategy 3: Constrained decoding (future v0.2)
          → Ollama grammar parameter for guaranteed valid JSON
        """
        # Try structured function calling first
        if hasattr(output, 'tool_calls') and output.tool_calls:
            return ToolCall.from_api_response(output.tool_calls[0])

        # Balanced brace parser — handles nested objects
        extracted = self._extract_json_balanced(str(output))
        if extracted:
            try:
                return ToolCall.model_validate(extracted)
            except ValidationError:
                return None

        return None

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
```

### 7.8 Event Bus

```python
class EventBus:
    """
    In-memory pub/sub with SQLite persistence.
    Web UI subscribes via WebSocket (SSE as fallback).

    Restart behaviour (v0.1):
      On pvx restart: in-memory subscribers are cleared.
      Web UI shows empty feed on reconnect — no automatic replay.
      User can manually load past session history via:
        GET /api/sessions/{id} → returns all stored events
      Automatic replay on reconnect is a v0.2 feature.
      This is intentional for v0.1 simplicity — state it in README.

    Event types:
    ┌─────────────────────────────────────────────────────┐
    │ Task lifecycle                                      │
    │   TASK_CREATED, TASK_CLASSIFIED, TASK_ROUTED        │
    │   TASK_STARTED, TASK_COMPLETED, TASK_FAILED         │
    │   TASK_PREEMPTED, TASK_TIMEOUT, TASK_ZOMBIE         │
    │   STARVATION_BYPASS                                 │
    │                                                     │
    │ Model lifecycle                                     │
    │   MODEL_LOADED, MODEL_UNLOADED, MODEL_SWAP_START    │
    │   MODEL_SWAP_COMPLETE                               │
    │                                                     │
    │ Inter-model communication                           │
    │   MODEL_TO_MODEL_MESSAGE                            │
    │                                                     │
    │ VRAM                                                │
    │   VRAM_UPDATE, VRAM_WARNING, VRAM_PRESSURE          │
    │   VRAM_PREEMPTION                                   │
    │                                                     │
    │ MCP                                                 │
    │   MCP_CALL_MADE, MCP_CALL_SUCCESS, MCP_CALL_FAILED  │
    │   MCP_REPROMPT, MCP_HALLUCINATION_MAX_RETRIES       │
    │                                                     │
    │ Context                                             │
    │   CONTEXT_COMPRESSED                               │
    │   CONTEXT_COMPRESSION_SKIPPED                      │
    │                                                     │
    │ System actions                                      │
    │   FILE_WRITTEN, FILE_READ, GIT_COMMIT               │
    │   TERMINAL_COMMAND, DB_QUERY                        │
    │                                                     │
    │ Resilience                                          │
    │   CIRCUIT_BREAKER_OPEN, CIRCUIT_BREAKER_CLOSED      │
    │   RATE_LIMIT_HIT, FALLBACK_ACTIVATED                │
    └─────────────────────────────────────────────────────┘
    """
```

---

## 7.9 Model Wrappers — Full Specification

This section specifies how PvX actually invokes each model type.
Previously `models/claude.py` appeared in the
directory structure without specification. This is the missing piece.

### models/base.py — Base Model Interface

```python
class BaseModel(ABC):
    """All model wrappers implement this interface."""

    @abstractmethod
    def generate(self, prompt: str, history: List[Message],
                 tools: Optional[List[dict]] = None) -> GenerationResult:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def name(self) -> str:
        pass


class GenerationResult:
    content: str
    tokens_used: int
    model: str
    duration_ms: int
    tool_calls: Optional[List[dict]]
    error: Optional[str]
```

### models/ollama.py — Ollama Client Wrapper

```python
class OllamaModel(BaseModel):
    """
    Wraps the ollama-python client.
    Handles model load/unload, streaming, token counting.
    All local models (Qwen-14B, DeepSeek-R1, Qwen-3B) use this.

    Uses stream=True so that the TaskQueueEngine's register_streaming_token()
    callback receives tokens mid-generation. This is required for the
    preemption partial output strategy to function — with stream=False,
    the streaming buffer is never populated and partial save always discards.
    """

    def __init__(self, model_name: str, task_queue: TaskQueueEngine,
                 current_task_id: Optional[str] = None):
        self.model_name = model_name
        self.task_queue = task_queue
        self.current_task_id = current_task_id

    def generate(self, prompt, history, tools=None,
                 task_id: Optional[str] = None) -> GenerationResult:
        """
        Streams generation token-by-token.
        Each token fed to task_queue.register_streaming_token()
        enabling mid-generation preemption with partial output save.
        """
        full_content = ""
        tokens_used = 0

        stream = ollama.chat(
            model=self.model_name,
            messages=self._build_messages(history, prompt),
            tools=tools,
            stream=True,                  # ← MUST be True for preemption to work
            options={"num_predict": 8192, "num_ctx": 16384, "temperature": 0.2}
        )

        for chunk in stream:
            token = chunk.message.content or ""
            full_content += token

            # Feed each token to queue engine for preemption tracking
            if task_id:
                self.task_queue.register_streaming_token(task_id, token)

            # Track token count from eval_count in final chunk
            if chunk.done and hasattr(chunk, 'eval_count'):
                tokens_used = chunk.eval_count

        return GenerationResult(
            content=full_content,
            tokens_used=tokens_used,
            tool_calls=None,  # Tool calls parsed separately from content
        )
```

### models/claude.py — Claude Code Subprocess Wrapper

```python
class ClaudeCodeModel(BaseModel):
    """
    Invokes Claude Code CLI as a subprocess.

    Claude Code is a terminal program, not a Python SDK.
    PvX shells out to it via subprocess for non-interactive tasks.

    Invocation (non-interactive print mode):
        claude --print -p "<prompt>"

    --print flag: outputs response to stdout and exits immediately.
    Does not start an interactive session.

    Used for:
        ✅ Task classification (low-confidence escalation from Claude)
        ✅ Quality gate reviews (prompt in, review out)
        ✅ Architecture decisions (prompt in, decision out)
        ❌ Multi-step agentic file-system workflows
           → These are initiated by the user in Claude Code terminal directly.
           → PvX MCP tools are available inside those sessions.
           → PvX does not spawn or manage these sessions.

    Authentication:
        Claude Code uses ANTHROPIC_API_KEY environment variable
        or ~/.claude/credentials.json from interactive setup.
        Set up via: claude (interactive first run).
        PvX never handles or stores credentials.

    Rate limit detection:
        Claude does not use clean exit codes for rate limits.
        Detect via stderr pattern matching against known error strings.
    """

    CLAUDE_CMD = "claude"
    RATE_LIMIT_PATTERNS = [
        "rate_limit_error",
        "Too many requests",
        "overloaded_error",
        "529",
    ]

    def generate(self, prompt: str, history: List[Message],
                 tools=None) -> GenerationResult:
        full_prompt = self._build_prompt(history, prompt)
        cmd = [
            self.CLAUDE_CMD,
            "--print",
            "-p", full_prompt,
        ]

        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=180,
                check=False
            )
        except subprocess.TimeoutExpired:
            return GenerationResult(error="CLAUDE_TIMEOUT")
        except FileNotFoundError:
            return GenerationResult(error="CLAUDE_CODE_NOT_FOUND")

        duration_ms = int((time.time() - start) * 1000)
        stderr = result.stderr.decode(errors="replace")

        # Rate limit detection via stderr pattern matching
        if any(pat in stderr for pat in self.RATE_LIMIT_PATTERNS):
            self.circuit_breaker.record_failure()
            return GenerationResult(error="CLAUDE_RATE_LIMITED")

        if result.returncode != 0:
            return GenerationResult(error=f"CLAUDE_ERROR: {stderr[:500]}")

        content = result.stdout.decode(errors="replace")

        # Strip ANSI escape sequences before parsing.
        # claude --print may emit coloured output with sequences like \x1b[1m.
        # Without stripping, the JSON classifier parser fails on raw ANSI.
        content = re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', content).strip()
        return GenerationResult(
            content=content,
            tokens_used=0,        # --print mode doesn't expose token count
            model="claude",  # matches "claude"
            duration_ms=duration_ms,
        )

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                [self.CLAUDE_CMD, "--version"],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
```

---

## 8. Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| MCP Server | **Python 3.11+** | MCP SDK is Python-first, async native |
| Task Queue | **Python asyncio** | Native async, no extra broker needed at v0.1 scale |
| VRAM Monitor | **pynvml** (primary) + **nvidia-smi** (fallback) | pynvml: direct C library, low overhead, structured data |
| Database | **SQLite + WAL mode via SQLModel** | Zero config, portable, WAL handles concurrent reads |
| Write Serialisation | **asyncio.Queue** (single writer) | Prevents WAL contention |
| Web Server | **FastAPI** | Async, fast, OpenAPI docs auto-generated |
| Real-time | **WebSocket** (primary) + **SSE** (fallback) | Real-time event streaming to UI |
| Frontend | **React + Tailwind** | Component reuse, rapid UI development |
| Ollama Client | **ollama-python** | Official client library |
| MCP SDK | **mcp (Anthropic)** | Official MCP protocol implementation |
| Token Counting | **tiktoken** | Fast, accurate token estimation |
| Config | **YAML + Pydantic v2** | Type-safe config with validation |
| Logging | **structlog** | Structured JSON logs for developer observability |
| Packaging | **uv + pyproject.toml** | Modern Python packaging, fast installs |
| Container | **Docker Compose** | One-command setup for users |
| Testing | **pytest + pytest-asyncio** | Async test support |

---

## 9. Data Flow

```
1. User submits task prompt
        │
2. TaskClassifier (Claude Code)
   → Returns: category, confidence, reasoning
        │
3. TaskRouter
   → Selects primary model
   → Checks VRAM availability
   → Selects fallback if needed
   → Logs routing decision
        │
4. Task pushed to Queue with:
   → model assignment
   → priority
   → dependency list
   → requires_vram flag
        │
5. Queue Scheduler runs:
   → Resolves dependencies
   → Applies model affinity batching
   → Checks VRAM via VRAMManager
   → Checks for preemption conditions
        │
6. VRAMManager loads model:
   → pynvml confirms VRAM available
   → Ollama loads model
   → MODEL_LOADED event emitted
   → Heartbeat monitor starts
        │
7. ContextCompressor runs:
   → Counts history tokens
   → If > 70% of model limit: compress via Claude
   → Returns final context for prompt
        │
8. Model generates output:
   → Streaming tokens → Event Bus → Web UI
   → Heartbeat monitor watches GPU utilisation
        │
9. MCP Proxy parses output:
   → Detects tool calls
   → Validates tool exists (graceful re-prompt if not)
   → Security layer validates intent
   → Executes MCP call
   → Returns result to model
   → Shadow Terminal shows raw output
        │
10. Output returned to orchestrator:
    → Claude Code acts on it
    → Files written, commands run, git committed
    → All system actions logged to Event Bus
        │
11. Task marked DONE:
    → Downstream tasks unblocked
    → Next task pulled from Queue
    → Model stays loaded (affinity batching window)
```

---

## 10. MCP Layer + Security Model

### Supported MCP Servers

```yaml
# pvx.config.yaml

mcp_servers:
  postgresql:
    enabled: true
    connection: "postgresql://user:pass@localhost:5432/db"
    allowed_operations: ["SELECT", "INSERT", "UPDATE"]
    blocked_operations: ["DROP", "TRUNCATE", "DELETE", "ALTER", "CREATE"]
    max_result_rows: 1000

  discord:
    enabled: false
    bot_token: "${DISCORD_BOT_TOKEN}"
    allowed_channels: ["dev-logs", "ai-feed"]

  github:
    enabled: true
    token: "${GITHUB_TOKEN}"
    allowed_repos: ["your-org/pvx"]
    allowed_operations: ["read", "create_issue", "create_pr"]
    blocked_operations: ["delete_repo", "add_collaborator"]

  filesystem:
    enabled: true
    allowed_paths:
      - "./project"
      - "~/workspace"
    blocked_paths:
      - "~/.ssh"
      - "/etc"
      - "~/.aws"
      - "~/.config/pvx"  # Don't let AI edit its own config
    max_file_size_mb: 10

  custom:
    - name: "my_custom_server"
      url: "http://localhost:8080/mcp"
      enabled: false
```

### Security Layer

```python
class SecurityLayer:
    """
    All MCP tool calls pass through security validation before execution.
    Threats: SQL injection, path traversal, command injection,
             privilege escalation via AI-generated inputs.

    This section requires adversarial review before v0.1 ship.
    Local LLMs at Q4 produce creative variations of dangerous inputs
    not covered by naive pattern matching. Treat as a first pass.
    """

    def validate(self, tool_call: ToolCall) -> bool:
        validators = {
            "query_database":  self._validate_sql,
            "write_file":      self._validate_path,
            "read_file":       self._validate_path,
            "terminal":        self._validate_command,
        }
        validator = validators.get(tool_call.name)
        return validator(tool_call) if validator else True

    def _validate_sql(self, tool_call: ToolCall) -> bool:
        query = tool_call.params.get("query", "").upper()
        # Blocked keywords — comprehensive list
        blocked = [
            "DROP", "TRUNCATE", "DELETE", "ALTER", "CREATE",
            "GRANT", "REVOKE",
            "--", ";--", "/*", "*/",          # Comment injection
            "EXEC", "EXECUTE", "XP_", "SP_",  # Stored procedure execution
            "CAST(", "CONVERT(",              # Type conversion attacks
            "0X",                             # Hex encoding
            "CHAR(",                          # String building via CHAR()
            "UNION",                          # UNION injection
        ]
        return not any(kw in query for kw in blocked)

    def _validate_path(self, tool_call: ToolCall) -> bool:
        path_str = tool_call.params.get("path", "")
        try:
            resolved = Path(path_str).resolve()
        except (ValueError, OSError):
            return False

        allowed_paths = [Path(p).resolve() for p in config.filesystem.allowed_paths]
        blocked_paths = [Path(p).resolve() for p in config.filesystem.blocked_paths]

        # Use is_relative_to() — NOT startswith()
        # startswith() is vulnerable: /home/user/allowed-path-evil/
        # passes startswith check for /home/user/allowed-path
        # is_relative_to() correctly rejects this (Python 3.9+)
        in_allowed = any(resolved.is_relative_to(a) for a in allowed_paths)
        in_blocked  = any(resolved.is_relative_to(b) for b in blocked_paths)

        return in_allowed and not in_blocked

    def _validate_command(self, tool_call: ToolCall) -> bool:
        command = tool_call.params.get("command", "")
        blocked_patterns = [
            # Recursive/force deletes
            r"rm\s+.*-[a-z]*r",           # rm -r, rm -rf, rm -fr etc.
            r"rm\s+.*--force",
            r"rm\s+.*--recursive",

            # Privilege escalation — including alternatives to sudo
            r"\bsudo\b",
            r"\bdoas\b",                   # OpenBSD sudo alternative
            r"\bpkexec\b",                 # Polkit privilege escalation
            r"\bsu\s+-",                   # su - root

            # Permission widening
            r"chmod\s+[0-9]*7[0-9]*",      # Any world-writable permission
            r"chmod\s+[0-9]*6[0-9]*",      # Group/world writable
            r"chmod\s+a\+",                # chmod a+write etc.

            # Remote code execution
            r"curl\s+.*\|\s*(ba)?sh",
            r"wget\s+.*\|\s*(ba)?sh",
            r"curl\s+.*\|\s*python",
            r"fetch\s+.*\|\s*(ba)?sh",

            # Writing to system paths
            r">\s*/etc/",
            r">\s*/sys/",
            r">\s*/proc/",
            r">\s*/boot/",
            r"tee\s+/etc/",

            # Environment manipulation
            r"export\s+PATH=",
            r"export\s+LD_",               # LD_PRELOAD attacks
        ]
        return not any(re.search(p, command, re.IGNORECASE)
                       for p in blocked_patterns)
```

---

## 11. VRAM Manager — Full Specification

```
State Machine:
──────────────
         ┌─────────────────────────────────┐
         │              IDLE               │
         │    No model loaded in VRAM      │
         └──────────────┬──────────────────┘
                        │ load_model()
                        ▼
         ┌─────────────────────────────────┐
         │             LOADED              │
         │   Model in VRAM, not running    │
         └──────────────┬──────────────────┘
                        │ start_generation()
                        ▼
         ┌─────────────────────────────────┐
         │             RUNNING             │◄──────────┐
         │   Model actively generating     │           │
         └───┬──────────┬─────────────────┘           │
             │          │                             │
             │ done     │ GPU util < 2% for 60s       │
             ▼          ▼                             │
         LOADED      ZOMBIE                           │
                        │                             │
                        │ handle_zombie()             │
                        └─────────────────────────────┘
                              retry if retries remain

         ┌─────────────────────────────────┐
         │            EXTERNAL             │
         │ Non-Ollama process on GPU       │
         │ (training job detected)         │
         │ All local LLM tasks blocked     │
         └─────────────────────────────────┘

         ┌─────────────────────────────────┐
         │            PRESSURE             │
         │ Free VRAM < SAFETY_BUFFER_MB    │
         │ Warning emitted, user alerted   │
         └─────────────────────────────────┘
```

---

## 12. Task Queue Engine — Full Specification

### Priority Levels
```
P5 — CRITICAL   Blocking other tasks. Preempts P1/P2. User waiting.
P4 — HIGH       Important implementation. Preempts P1.
P3 — NORMAL     Standard task. Default for all tasks.
P2 — LOW        Background work, documentation.
P1 — MINIMAL    Cleanup, formatting. Can be preempted by P4/P5.
```

### Dependency Failure Propagation
```
Task dependency failure strategy:
  T1 FAILS → T2 depends on T1

  Options (configurable per task):
  A. FAIL_CASCADE  → T2 marked BLOCKED_DEPENDENCY, user notified
  B. SKIP          → T2 skipped, T3 (depends on T2) also skipped
  C. REROUTE       → T1's job reassigned to fallback model, retry
  D. MANUAL        → Queue paused, user must resolve before continuing

  Default: FAIL_CASCADE with user alert
```

### Circuit Breaker — Per Model
```python
class CircuitBreaker:
    """
    Prevents hammering a failing model/service.

    States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing)

    Thresholds:
      - 3 consecutive failures → OPEN circuit
      - 30 second cooldown → HALF_OPEN
      - 1 success in HALF_OPEN → CLOSED
      - 1 failure in HALF_OPEN → OPEN again

    Applied to:
      - Each Ollama model independently
      - Claude Code (rate limit detection)
      - Each MCP server
    """
```

---

## 13. Context Window Management

```
Per-model context limits and compression thresholds:
┌──────────────────────┬──────────────┬────────────────────┐
│ Model                │ Context      │ Compress at (70%)  │
├──────────────────────┼──────────────┼────────────────────┤
│ qwen2.5-coder:3b     │  32,000      │  22,400 tokens     │
│ deepseek-r1:7b       │  32,000      │  22,400 tokens     │
│ qwen2.5-coder:14b    │  128,000     │  89,600 tokens     │
│ claude          │  200,000  │  140,000 tokens    │
└──────────────────────┴──────────────┴────────────────────┘

Compression strategy:
  Trigger:   history_tokens > threshold
  Summariser: Claude Code (200K context, no VRAM)
  Output:    summary (< 2000 tokens) + last 5 messages verbatim
  Logged:    CONTEXT_COMPRESSED event with reduction stats
  Flagged:   task.context_was_compressed = True

Token counting:
  Library: tiktoken
  Estimation: conservative (count at 95% to leave headroom)
```

---

## 14. Error Recovery & Resilience

```
Failure scenarios and handling:
┌──────────────────────────────┬────────────────────────────────────┐
│ Failure                      │ Handling                           │
├──────────────────────────────┼────────────────────────────────────┤
│ Ollama crashes mid-gen       │ Zombie detect → kill → retry       │
│ Model OOM                    │ VRAM error → fallback model        │
│ Claude rate limit hit        │ Circuit breaker → hold queue       │
│                              │ 30s cooldown → retry               │
│ Claude Code unavailable      │ Circuit breaker → Queue hold  │
│ MCP tool hallucinated        │ Graceful re-prompt (max 3x)        │
│ MCP call fails               │ Retry 2x → fail task with error    │
│ Task dependency fails        │ FAIL_CASCADE (configurable)        │
│ SQLite locked                │ WAL mode prevents this             │
│ Task hangs (zombie)          │ 60s heartbeat timeout → kill       │
│ Security validation fails    │ Task failed, SECURITY_REJECTED     │
│ Context overflow             │ Compress via Claude before sending │
│ JSON parse error from model  │ Retry with re-prompt               │
│ Preempted task               │ Re-queued, retry_count unchanged   │
└──────────────────────────────┴────────────────────────────────────┘
```

---

## 15. Web UI Specification

### Layout
```
┌──────────────────────────────────────────────────────────────────┐
│  PvX                                            v0.1  ●  LIVE   │
├──────────────┬───────────────────────────────────────────────────┤
│              │                                                   │
│  SIDEBAR     │   MAIN PANEL                                      │
│              │   (switches on sidebar click)                     │
│  🔄 Feed     │                                                   │
│              │                                                   │
│  💬 Chats    │                                                   │
│  ├─ Claude   │                                                   │
│  ├─ Qwen14B  │                                                   │
│  ├─ DeepSeek │                                                   │
│  └─ Qwen3B   │                                                   │
│              │                                                   │
│  📋 Queue    │                                                   │
│              │                                                   │
│  📊 Stats    │                                                   │
│              │                                                   │
│  💰 Cost     │                                                   │
│              │                                                   │
│  ⚙️  Config  │                                                   │
│              ├───────────────────────────────────────────────────┤
│              │  🖥️  SHADOW TERMINAL    [collapse ▲]              │
│              │  $ git commit -m "Add PaiNN layer"                │
│              │  [master 3f2a1b] Add PaiNN layer                  │
│              │  $ pytest tests/test_painn.py                     │
│              │  ....F                                            │
│              │  FAILED: shape mismatch expected [B,N,128]        │
└──────────────┴───────────────────────────────────────────────────┘
```

### Panel Specifications

**🔄 Orchestration Feed**
```
Features:
- Real-time WebSocket stream of all inter-model events
- Color coded per model:
    Claude Code  → Blue
    Qwen-14B     → Purple
    DeepSeek-R1  → Orange
    Qwen-3B      → Yellow
    System       → Grey

- Each entry shows:
    [timestamp] [from] → [to]: preview (click to expand)

- Expanded view shows:
    Full prompt sent
    Full response received
    MCP calls made within this exchange
    Tokens used
    Duration

- User interventions (the headline UX feature):
    ✏️  Edit — modify a model's output before it propagates downstream
    🍴  Fork — create a branch of the task with edited output
    ⏸️  Pause — halt the chain here, review, then continue
    🔁  Retry — re-run this specific model call with same prompt
    ❌  Abort — kill the entire task chain

- Filters: by model, event type, time range
- Export: full session to markdown or JSON
```

**💬 Direct Chat (per model)**
```
Features:
- Standard chat interface wired to specific model
- Conversation history persisted per session
- Model metadata bar:
    Current VRAM usage
    Context tokens used / limit
    Generation speed (tok/s)
    Context compressed: Yes/No
- One-click: "Send to orchestrator as task"
- One-click: "Add to task queue"
```

**📋 Task Queue**
```
Features:
- Visual dependency graph (nodes and edges)
- Drag to reprioritise (updates priority field)
- Per-task actions: cancel, retry, reprioritise, view output
- VRAM impact indicator per pending task
- Model swap cost estimate (seconds) shown when model switch needed
- Dry-run preview: click any pending task → see routing analysis
```

**📊 Stats Dashboard**
```
Active model + current task
VRAM usage bar (live, updates every 2s)
  [████████░░] 8,700 / 12,288 MB — Qwen-14B loaded
GPU utilisation % (live)
Model affinity batch status:
  "Batching 4 Qwen-14B tasks before DeepSeek swap"
Tokens used per model (session)
Tasks: 14 done | 3 pending | 1 running | 0 failed
Context compressions this session: 2
```

**💰 Cost Tracker**
```
Claude Code     Pro subscription     £0.00 marginal
Qwen-14B        Local                £0.00 + electricity
DeepSeek-R1     Local                £0.00 + electricity
Qwen-3B         Local                £0.00 + electricity
─────────────────────────────────────────────────
Total API cost this session          £0.00
Equivalent GPT-4o API cost          ~£3.40
Savings vs cloud-only                98.2%
```

**🖥️ Shadow Terminal**
```
Real-time stdout/stderr from all system-level MCP actions.
Collapsible panel at bottom of every view.
Shows:
  - File operations (reads, writes, deletes)
  - Terminal commands executed by agents
  - Git operations
  - Database queries and results
  - MCP re-prompt attempts
  - Security rejections

Colour coded:
  Green  → Success
  Red    → Error / stderr
  Yellow → Warning
  Grey   → Info / stdout
```

---

## 16. Open Source Tiers

PvX supports one configured CLI. Set in `pvx.config.yaml`:

```yaml
orchestrator:
  cli: "claude"   # only supported value in v0.1
```

### Tier 0 — Pure Local (Air-Gapped / No Internet)
```
Requirements:
  ✓ Ollama installed
  ✓ Local models pulled
  ✗ No internet required
  ✗ No cloud CLI required

Provides:
  ✓ All local Ollama models (Qwen-14B, DeepSeek-R1, Qwen-3B)
  ✓ Full task queue + VRAM manager + zombie detection
  ✓ Web UI
  ✓ MCP proxy (filesystem, postgres, github — local endpoints)
  ✓ Keyword-based task classification (no Claude calls)
  ✓ Qwen-3B context compression (no Claude calls)
  ✓ Works fully offline and in air-gapped environments

Limitations vs Tier 1:
  - Keyword classifier only (lower accuracy on ambiguous tasks)
  - No Claude quality gates or architecture review
  - Context compression quality lower (Qwen-3B vs Claude)

Suitable for:
  Privacy-first developers, air-gapped corporate environments,
  developers with no Anthropic account.
```

### Tier 1 — Claude Code + Local (v0.1 Primary)
```
orchestrator.cli: "claude"

Requirements:
  ✓ Anthropic API key or Claude Pro subscription
  ✓ Claude Code CLI installed and authenticated
  ✓ Ollama installed
  ✓ Internet access required

Provides:
  ✓ Everything in Tier 0
  ✓ Claude escalation for ambiguous task classification
    (keyword handles clear cases; Claude handles the rest — saves tokens)
  ✓ Claude quality gates and architecture review
  ✓ Context up to 200K tokens for large-context tasks
  ✓ Qwen-3B local compression (free, no Claude tokens)

Token usage philosophy:
  - Keyword classifier handles ~80% of tasks (free)
  - Claude called only for genuinely ambiguous classifications (~20%)
  - Context compression done locally by Qwen-3B (free)
  - Claude tokens reserved for: quality gates, architecture,
    large-context tasks, classification escalation
  - Claude Pro rate limits are reduced, not eliminated

Suitable for:
  Claude Pro subscribers. The primary target user of PvX.
  The author's own setup.
```

## 17. Developer Observability

Beyond the user-facing Feed, PvX emits structured logs for debugging.

```python
# structlog configuration
import structlog

log = structlog.get_logger()

# Every routing decision logged
log.info("task_routed",
    task_id=task.id,
    category=task.category,
    classifier_confidence=0.87,
    primary_model="deepseek-r1:7b",
    fallback_reason=None,
    vram_available_mb=4500,
    routing_time_ms=230
)

# Every model swap logged
log.info("model_swap",
    from_model="qwen2.5-coder:14b",
    to_model="deepseek-r1:7b",
    swap_duration_ms=8400,
    vram_before_mb=8700,
    vram_after_mb=4500,
    triggered_by_task=task.id
)

# Every MCP call logged
log.info("mcp_call",
    tool="query_database",
    model=task.model,
    task_id=task.id,
    validated=True,
    duration_ms=45,
    result_rows=12
)

# Every zombie detection logged
log.warning("zombie_detected",
    task_id=task.id,
    model=task.model,
    running_since_seconds=73,
    gpu_util_pct=0,
    action="kill_and_retry",
    retry_count=task.retry_count
)
```

Log output: structured JSON to `~/.pvx/logs/pvx.log`
Log rotation: 10MB per file, 5 files retained
Log format: JSON (parseable by jq, Grafana, any log aggregator)

---

## 18. Configuration-Driven Routing

The routing table is not hardcoded — it lives in `pvx.config.yaml` and can be overridden per project.

```yaml
# pvx.config.yaml

orchestrator:
  cli: "claude"
                             # This is the only place you declare your CLI choice.
                             # All routing rules use "claude" as a placeholder
                             # which resolves to this value at runtime.

routing:
  rules:
    math_proof:        deepseek-r1:7b
    algorithm_design:  deepseek-r1:7b
    debugging_logic:   deepseek-r1:7b
    chain_of_thought:  deepseek-r1:7b
    ml_pipeline:       qwen2.5-coder:14b
    oop_design:        qwen2.5-coder:14b
    system_design:     qwen2.5-coder:14b
    complex_code:      qwen2.5-coder:14b
    code_review:       qwen2.5-coder:14b
    docstrings:        qwen2.5-coder:3b
    boilerplate:       qwen2.5-coder:3b
    formatting:        qwen2.5-coder:3b
    simple_refactor:   qwen2.5-coder:3b
    large_context:     claude     # resolves to claude
    codebase_analysis: claude
    architecture:      claude
    final_review:      claude

  fallback_chain:
    deepseek-r1:7b:      [claude]      # VRAM unavailable → use CLI
    qwen2.5-coder:14b:   [claude]
    qwen2.5-coder:3b:    [qwen2.5-coder:14b, claude]
    claude:      []                    # CLI fails → hard fail + alert

  classifier:
    fallback: keyword-heuristic               # used when CLI unavailable
    min_confidence: 0.6                        # below this: log warning, still accept

models:
  local:
    - name: qwen2.5-coder:14b
      vram_mb: 8700
      context_tokens: 128000
      supports_function_calling: true

    - name: deepseek-r1:7b
      vram_mb: 4500
      context_tokens: 32000
      supports_function_calling: true

    - name: qwen2.5-coder:3b
      vram_mb: 2000
      context_tokens: 32000
      supports_function_calling: false

  # Cloud model config
  # No need to configure both — only the one you chose matters
  claude:
    context_tokens: 200000
    # Rate limits managed by Claude Code itself

vram:
  safety_buffer_mb: 512
  zombie_timeout_seconds: 60
  zombie_utilisation_threshold_pct: 2
  polling_interval_seconds: 2
  preemption:
    p5_preempts: [p1, p2, p3]
    p4_preempts: [p1]

queue:
  default_priority: 3
  default_max_retries: 3
  dependency_failure_strategy: fail_cascade  # fail_cascade|skip|reroute|manual
  affinity_batch_max_tasks: 10               # Max tasks before forcing model swap
  affinity_batch_max_seconds: 300            # Max seconds before forcing model swap
  starvation_timeout_seconds: 300            # Task waiting longer bypasses affinity
  partial_save_min_tokens: 150               # Min tokens generated before saving partial

context:
  compression_threshold_pct: 70
  compression_model: claude  # uses claude
  compression_keep_last_messages: 5

security:
  sql_blocked_keywords: [DROP, TRUNCATE, DELETE, ALTER, CREATE, GRANT, REVOKE]
  path_traversal_check: true
  command_injection_check: true
```

---

## 19. API Contracts

### REST Endpoints

```
# Tasks
POST   /api/tasks                Submit new task
POST   /api/tasks/analyze        Dry-run: preview routing without executing
GET    /api/tasks                List all tasks (filter by status, model, session)
GET    /api/tasks/{id}           Get task detail with full output
DELETE /api/tasks/{id}           Cancel pending/running task
POST   /api/tasks/{id}/retry     Retry failed task
PATCH  /api/tasks/{id}/priority  Update task priority

# Models
GET    /api/models               List all available models + status
POST   /api/models/load          Load model into VRAM
POST   /api/models/unload        Unload model from VRAM
GET    /api/models/{name}/status  Model status + VRAM usage

# VRAM
GET    /api/vram                  Current VRAM state (full)
GET    /api/vram/simple           Current VRAM state (UI summary)

# Sessions
GET    /api/sessions              List sessions
POST   /api/sessions              Create new session
GET    /api/sessions/{id}         Session with all messages and events
GET    /api/sessions/{id}/export  Export session as markdown or JSON
DELETE /api/sessions/{id}         Delete session

# Chat (direct model access)
POST   /api/chat                  Direct chat to specific model

# Events
GET    /api/events                Event log (paginated, filterable)

# Config
GET    /api/config                Get current config
PUT    /api/config                Update config (hot-reload where possible)
POST   /api/config/validate       Validate config without applying

# Health
GET    /api/health                Platform health check
GET    /api/health/ollama         Ollama connectivity check
GET    /api/health/claude         Claude Code check
```

### POST /api/tasks/analyze — Dry Run Response
```json
{
  "prompt": "Implement the PaiNN equivariance proof and code it",
  "classification": {
    "category": "math_proof",
    "confidence": 0.87,
    "reasoning": "Mathematical proof detected with implementation follow-up",
    "classified_by": "claude",     # or "keyword" | "cache"
    "all_keyword_matches": [],
    "overrides_claude": false
  },
  "_classified_by_values": "cache | claude | keyword_fallback | keyword_fallback_default",
  "routing": {
    "primary_model": "deepseek-r1:7b",
    "fallback_chain": ["claude"],
    "routing_reason": "math_proof → deepseek-r1:7b per routing config"
  },
  "vram": {
    "required_mb": 4500,
    "available_mb": 3588,
    "sufficient": false,
    "warning": "Insufficient VRAM — Qwen-14B unload required first",
    "estimated_swap_seconds": 12,
    "state_after_swap": "deepseek-r1:7b loaded, 7788MB free"
  },
  "context": {
    "current_history_tokens": 18400,
    "model_limit_tokens": 32000,
    "compression_needed": false,
    "compression_threshold": 22400
  }
}
```

Note: `estimated_duration_seconds` deliberately omitted from v0.1.
No benchmarking data collection exists yet to back up a prediction.
A static guess would undermine trust in a platform built on transparency.
Duration estimation returns in v0.2 when per-model throughput tracking is added.

### pvx doctor — Dependency Checker
```bash
$ pvx doctor

Checking PvX dependencies...
  ✅ Python 3.11+       found (3.11.8)
  ✅ uv                 found (0.4.2)
  ❌ Ollama             not found
     → Install: curl -fsSL https://ollama.com/install.sh | sh
  ⏭️  Ollama models     skipped (Ollama not found)
  ⚠️  Claude Code       not found (optional)
     → Install: npm install -g @anthropic-ai/claude-code
  ✅ pynvml             found
  ✅ NVIDIA GPU         detected (RTX 3060, 12288MB)

2 errors, 2 warnings.
Fix errors before running pvx start.
Run pvx doctor --fix for guided setup.
```

Correct doctor output when Ollama IS installed:
```bash
$ pvx doctor

Checking PvX dependencies...
  ✅ Python 3.11+       found (3.11.8)
  ✅ uv                 found (0.4.2)
  ✅ Ollama             running (localhost:11434)
  ✅ Ollama models      qwen2.5-coder:14b ✓  deepseek-r1:7b ✓  qwen2.5-coder:3b ✓
  ⚠️  Claude Code       not found (optional)
  ✅ pynvml             found
  ✅ NVIDIA GPU         detected (RTX 3060, 12288MB)

0 errors, 1 warning. Ready to run pvx start.
```

pvx doctor checks (in order):
1. Python version ≥ 3.11
2. uv installed
3. Ollama installed and running (attempts connection)
4. Ollama models pulled (warns if missing from default stack)
5. pynvml importable (NVIDIA GPU support)
6. NVIDIA GPU detected (warns if not found, CPU fallback noted)
7. Claude Code installed
10. pvx.config.yaml valid (Pydantic validation)

### WebSocket Event Schema
```json
{
  "id": "evt_01J8K2M...",
  "type": "MODEL_TO_MODEL_MESSAGE",
  "timestamp": "2026-04-04T14:23:01.342Z",
  "session_id": "sess_01J8...",
  "task_id": "task_01J8...",
  "payload": {
    "from_model": "claude",  # always "claude"
    "to_model": "qwen2.5-coder:14b",
    "prompt_preview": "Implement MolecularFeaturizer class using...",
    "prompt_tokens": 847,
    "full_prompt_available": true
  }
}
```

---

## 20. Build Phases

> **Note:** Timeline assumes Claude Code generates most implementation
> from this blueprint. Manual coding alone would take 3–4x longer.

### Phase 0 — Foundation (Days 1–2)

**Agent setup (do this before writing any code):**
```
□ Create CLAUDE.md (from Section 23.6)
□ Create docs/TASK_BOARD.md (from Section 23.3)
□ Create docs/ISSUES.md (empty, for blueprint gaps)
□ Copy blueprint to docs/PvX_Blueprint_v0.8.md
□ Open Claude Code terminal → paste supervisor prompt
□ Claude Code reads CLAUDE.md + blueprint, confirms plan
□ User approves plan before any code is written
```

**Claude Code (supervisor + sub-agents) builds:**
```
□ uv project init, pyproject.toml, src/pvx layout
□ All __init__.py placeholder files (full directory tree)
□ Pydantic config loader (pvx.config.yaml)
  → Include claude config from the start
□ SQLite + SQLModel setup with WAL mode enabled
□ structlog structured logging setup
□ Ollama Python client wrapper + connection test
□ pynvml VRAM polling (basic — total/used/free)
□ nvidia-smi fallback parser
□ pvx doctor command (all 10 checks)
□ pvx start command skeleton
□ pytest + pytest-asyncio configuration
□ GitHub Actions CI skeleton
□ docker-compose.yml skeleton
□ tests/unit/ stub files (one placeholder test each)
□ pvx.config.example.yaml (all options documented)
□ Update TASK_BOARD.md on completion of each item
```

**Supervisor review:**
```
□ Run review checklist on every sub-agent output
□ Run uv run pytest — all stubs should pass
□ Run uv run ruff check . — zero lint errors
□ Verify WAL mode in database.py
□ Verify nvmlInit() only in __init__()
□ Verify .total_seconds() throughout
□ Verify claude config schema
□ Commit: "feat: Phase 0 foundation complete"
```

### Phase 1 — Core Engine (Days 3–6)

**Claude Code (supervisor + sub-agents) builds:**
```
□ TaskClassifier (CLI-backed + keyword fallback — reads claude from config)
□ TaskRouter (config-driven routing + fallback chain)
□ Task dataclass + status state machine (all fields including
  tokens_generated_so_far, partial_output, resume_prompt)
□ TaskQueueEngine with asyncio + __init__ initialising all fields
□ Model affinity batching + starvation guard + reset_affinity_batch()
□ register_streaming_token() + get_current_output() streaming bridge
□ Dependency graph resolver
□ Dependency failure propagation (fail_cascade default)
□ VRAMManager full state machine with __init__ + cached handle
□ Zombie detection + heartbeat monitor (.total_seconds() throughout)
□ VRAM preemption logic + partial output save/resume
□ CircuitBreaker per model
□ EventBus (in-memory pub/sub + SQLite persistence)
□ ConversationStore (CRUD + WAL write queue)
□ Update TASK_BOARD.md on each completion
```

**Claude Code sub-agents build (in parallel):**
```
□ Integration test stubs for queue, VRAM, event bus, starvation
□ docs/TASK_BOARD.md updates for Phase 1
```

**Supervisor review:**
```
□ Run review checklist on all sub-agent outputs
□ Verify tokens_generated_so_far in Task dataclass
□ Verify __init__ initialises batch_start, current_batch_size,
  affinity_reset, _streaming_buffers
□ Verify .total_seconds() in starvation guard AND zombie detector
□ uv run pytest — all passing
□ Commit: "feat: Phase 1 core engine complete"
```

### Phase 2 — Context + Resilience (Days 7–8)

**Claude Code builds:**
```
□ ContextCompressor (CLI-backed — uses Claude Code for summarisation)
□ Token counter (tiktoken, with known inaccuracy documented)
□ Per-model context limit enforcement
□ Full error recovery matrix implementation
□ CLI rate limit detection + circuit breaker
□ Retry logic with exponential backoff
```

**Supervisor review:**
```
□ Verify compression only triggers at 70% threshold
□ Write integration test stubs: context compression, resilience
□ uv run pytest — all passing
□ Commit: "feat: Phase 2 context and resilience complete"
```

### Phase 3 — MCP Layer (Days 9–10)

**Claude Code builds (security-sensitive — Claude Code sub-agents only):**
```
□ MCP server registration + registry
□ SecurityLayer (is_relative_to() paths, comprehensive SQL/command lists)
□ MCPProxy with graceful re-prompt loop (max 3)
□ Balanced brace JSON parser
□ Function calling wrapper for Qwen/DeepSeek
□ PostgreSQL MCP integration
□ Filesystem MCP integration
□ GitHub MCP integration
□ Discord MCP integration (optional)
□ Security adversarial review checklist before merge
```

**Supervisor review:**
```
□ Security layer adversarial review — line by line
□ Write integration test stubs: MCP proxy, security, re-prompt, nested JSON
□ Update pvx.config.example.yaml with MCP config documentation
□ Verify is_relative_to() not startswith() in path validation
□ Verify balanced brace parser handles nested objects
□ Verify re-prompt loop max 3 enforced
□ uv run pytest — all passing
□ Commit: "feat: Phase 3 MCP layer complete"
```

### Phase 4a — API + Core Web UI (Days 11–13) — ships in v0.1

**Claude Code builds:**
```
□ FastAPI app + all REST endpoints
□ WebSocket real-time event streaming
□ /api/tasks/analyze dry-run endpoint (without duration estimate)
□ Orchestration Feed backend (event streaming to WebSocket)
□ Stats Dashboard backend (VRAM state, queue counts)
□ Cost Tracker backend
```

**Claude Code sub-agents build (UI):**
```
□ React app scaffold + routing structure
□ Sidebar component
□ Orchestration Feed UI (view-only — no intervention controls yet)
□ Direct Chat component (reusable per model)
□ Stats Dashboard UI + VRAM live bar
□ Cost Tracker UI
```

**Supervisor review:**
```
□ Backend API tested with httpx test client
□ WebSocket streaming verified
□ React components render without errors
□ E2E test: full pipeline from task submit to WebSocket event
□ Commit: "feat: Phase 4a API and core UI complete"
```

### Phase 4b — Advanced UI (Days 14–16) — ships in v0.1.1

**Claude Code sub-agents build:**
```
□ Feed intervention controls (Edit, Fork, Pause, Retry, Abort)
□ Task Queue UI with dependency graph visualiser
□ Shadow Terminal (collapsible, colour coded)
□ Config panel
□ Session replay from SQLite (manual load)
```

**Supervisor reviews and integrates:**
```
□ Edit/Fork state management — verify partial output handling correct
□ Dependency graph visualiser — verify reflects actual queue state
□ Shadow Terminal — verify all system actions surface correctly
□ E2E tests: interventions + dependency graph
□ Commit: "feat: Phase 4b advanced UI complete"
```

### Phase 5 — Distribution + Polish (Days 17–18)

**Claude Code builds:**
```
□ MCP server registration for Claude Code (tested end-to-end)
□ Claude Code routing verified
□ PyPI package build — uvx install pvx works
□ pvx start verified: MCP + Web UI + backend all launch together
□ mcp-config.json entry point tested end-to-end
□ Full flow: uvx install pvx → pvx doctor → pvx start → :8765
```

**Claude Code sub-agents build:**
```
□ Docker Compose (secondary distribution option)
□ README — uvx install story, pvx doctor output, quickstart
□ README sections: architecture, competitive position
□ Known limitations: no event replay on restart, tiktoken inaccuracy,
□ Contributing guide
□ Demo GIF script (sequence of commands to record)
```

**Supervisor final review:**
```
□ Full install flow tested on clean WSL2 environment
□ pvx doctor shows correct output for all dependency states
□ All tests passing: uv run pytest
□ Zero lint errors: uv run ruff check .
□ README reviewed for accuracy against blueprint
□ License: Apache 2.0 in all source files
□ Tag v0.1.0, PyPI publish via GitHub Actions
□ Create v0.1.1 milestone for Phase 4b items
□ Commit: "release: v0.1.0"
```

---

## 21. Directory Structure

```
pvx/
├── CLAUDE.md                         # Claude Code build instructions + rules
├── README.md
├── LICENSE                           # Apache 2.0
├── pyproject.toml                    # uv package config
├── pvx.config.yaml                   # User configuration (documented)
├── pvx.config.example.yaml           # Example config for new users
├── docker-compose.yml                # One-command setup
├── .github/
│   └── workflows/
│       ├── ci.yml                    # Tests + lint on PR
│       └── release.yml               # PyPI publish on tag
│
├── docs/
│   ├── PvX_Blueprint_v0.8.md         # This document
│   ├── TASK_BOARD.md                 # Live build task tracking
│   └── ISSUES.md                     # Blueprint gaps found during build
│
├── src/
│   └── pvx/
│       ├── __init__.py
│       ├── main.py                   # Entry point
│       │
│       ├── core/
│       │   ├── classifier.py         # Task Classifier (Claude Code + keyword fallback)
│       │   ├── router.py             # Task Router (config-driven)
│       │   ├── queue.py              # Task Queue + Affinity Batching
│       │   ├── vram.py               # VRAM Manager + Zombie + Preemption
│       │   ├── compressor.py         # Context Compressor
│       │   ├── events.py             # Event Bus
│       │   ├── circuit_breaker.py    # Circuit Breaker per model
│       │   └── config.py             # Config loader + Pydantic models
│       │
│       ├── models/
│       │   ├── base.py               # Base model interface
│       │   ├── ollama.py             # Ollama client wrapper
│       │   └── claude.py             # Claude Code wrapper
│       │
│       ├── mcp/
│       │   ├── server.py             # MCP server definition
│       │   ├── proxy.py              # MCP Proxy + graceful re-prompt
│       │   ├── security.py           # Security validation layer
│       │   ├── registry.py           # MCP server registry
│       │   └── tools/
│       │       ├── postgres.py
│       │       ├── filesystem.py
│       │       ├── github.py
│       │       └── discord.py
│       │
│       ├── store/
│       │   ├── database.py           # SQLite + WAL + write queue
│       │   ├── sessions.py
│       │   ├── messages.py
│       │   ├── tasks.py
│       │   └── events_store.py
│       │
│       └── api/
│           ├── app.py                # FastAPI app
│           ├── websocket.py          # WebSocket event streaming
│           └── routes/
│               ├── tasks.py          # Task CRUD + analyze
│               ├── models.py         # Model management
│               ├── vram.py           # VRAM state
│               ├── sessions.py       # Session management
│               ├── chat.py           # Direct chat
│               ├── events.py         # Event log
│               ├── config.py         # Config management
│               └── health.py         # Health checks
│
├── ui/
│   ├── package.json
│   ├── tailwind.config.js
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── Sidebar.jsx
│       │   ├── Feed.jsx              # Orchestration Feed + interventions
│       │   ├── Chat.jsx              # Direct Chat (reusable)
│       │   ├── Queue.jsx             # Task Queue + dep graph
│       │   ├── Dashboard.jsx         # Stats + VRAM live
│       │   ├── CostTracker.jsx
│       │   ├── ShadowTerminal.jsx    # Raw stdout/stderr panel
│       │   └── Config.jsx
│       └── hooks/
│           ├── useWebSocket.js       # WebSocket connection
│           ├── useVRAM.js            # VRAM polling
│           └── useQueue.js           # Queue state
│
└── tests/
    ├── unit/
    │   ├── test_classifier.py
    │   ├── test_router.py
    │   ├── test_queue.py
    │   ├── test_vram.py
    │   ├── test_compressor.py
    │   ├── test_mcp_proxy.py
    │   └── test_security.py
    ├── integration/
    │   ├── test_ollama.py
    │   ├── test_mcp.py
    │   ├── test_event_bus.py
    │   └── test_full_pipeline.py
    └── e2e/
        ├── test_task_lifecycle.py
        ├── test_zombie_recovery.py
        └── test_context_compression.py
```

```

---

## 23. Build Agent Strategy

> **Note:** This section is build-time meta-content — it describes how
> to build PvX, not what PvX does. The full content is also available
> as the standalone file `CLAUDE.md` and `docs/TASK_BOARD.md`.
> It is included here so the blueprint is fully self-contained for
> the initial build session.

PvX is built using the same multi-agent philosophy it implements.
Claude Code acts as supervisor. Claude Code sub-agents handle focused tasks.
All building happens within Claude Code — no second CLI required for the build.

### 23.1 Agent Roles

```
SUPERVISOR — Claude Code (main session)
  Reads blueprint + CLAUDE.md on every session start
  Breaks each phase into focused subtasks
  Spawns sub-agents via the Task tool
  Reviews every sub-agent output against review checklist
  Updates TASK_BOARD.md as tasks complete
  Integrates reviewed code into main branch
  Runs full test suite after each integration
  Makes all architectural decisions
  Never commits unreviewed code

CLAUDE SUB-AGENTS — Claude Code (Task tool instances)
  Each gets ONE focused task with full context
  Writes implementation + tests together
  Reports back: code written, tests written, blueprint gaps found
  Never makes architectural decisions alone
  Flags any blueprint ambiguity before proceeding
```

### 23.2 File Ownership

```
Claude Code owns (sub-agents never skip review on these):
  src/pvx/core/vram.py          ← security sensitive
  src/pvx/core/queue.py         ← complex state machine
  src/pvx/mcp/security.py       ← adversarial review required
  src/pvx/mcp/proxy.py          ← complex JSON parsing
  src/pvx/models/claude.py      ← subprocess security
  src/pvx/store/database.py     ← WAL mode critical

Claude Code sub-agents build (lower risk — supervisor spot-checks):
  All __init__.py placeholder files
  docker-compose.yml
  tests/unit/ stub files (no logic, just structure)
  docs/ documentation updates
  pvx.config.example.yaml
  ui/ React components (Phase 4b)

Shared read-only (never modified by sub-agents without supervisor approval):
  CLAUDE.md
  docs/PvX_Blueprint_v0.8.md
  pvx.config.yaml (user config — never touched by any agent)
```

### 23.3 TASK_BOARD.md

```markdown
# PvX Build Task Board
Last updated: [timestamp]
Current phase: PHASE 0

## Active Tasks
| Task | Owner | Status | Notes |
|---|---|---|---|
| pyproject.toml | Claude-Supervisor | 🔄 | |
| core/config.py | Claude-Agent-1 | ⏳ | |
| store/database.py | Claude-Agent-2 | ⏳ | |
| core/vram.py | Claude-Agent-3 | ⏳ | |
| models/ollama.py | Claude-Agent-4 | ⏳ | |
| pvx doctor | Claude-Agent-5 | ⏳ | |
| pvx start | Claude-Agent-6 | ⏳ | |
| pytest scaffold | Claude-Agent-7 | ⏳ | |
| __init__.py files | Claude-Agent-8 | ⏳ | |
| docker-compose.yml | Claude-Agent-9 | ⏳ | |
| test stubs | Claude-Agent-10 | ⏳ | |
| pvx.config.example | Claude-Agent-11 | ⏳ | |

Status codes: ⏳ Pending | 🔄 In Progress | 👁️ In Review | ✅ Done | ❌ Failed

## Review Queue
| Task | Output Location | Review Result |
|---|---|---|

## Completed This Phase
| Task | Owner | Tests Pass | Commit |
|---|---|---|---|

## Blueprint Issues Found
| Issue | Found By | Action |
|---|---|---|
```

### 23.4 Supervisor Review Checklist

Claude Code runs this on every sub-agent output before accepting:

```
□ Matches blueprint specification exactly?
□ Tests written alongside implementation?
□ All tests passing (uv run pytest)?
□ No unapproved dependencies added?
□ .total_seconds() used — never .seconds on timedelta?
□ Path.is_relative_to() used — never startswith()?
□ WAL mode on all SQLite connections?
□ nvmlInit() not called inside poll() — only in __init__()?
□ structlog used — never print()?
□ Pydantic v2 used — never v1 syntax?
□ Type hints on all functions?
□ No hardcoded paths — all from config?
□ Security-sensitive code reviewed line by line?
□ Blueprint gap found? → written to docs/ISSUES.md?
```

### 23.5 Worktree Isolation (Phase 3 Onwards)

For true parallel execution with zero file conflicts:

```bash
# Set up isolated worktrees per agent
git worktree add ../pvx-agent-config  -b agent/config
git worktree add ../pvx-agent-db      -b agent/database
git worktree add ../pvx-agent-vram    -b agent/vram
git worktree add ../pvx-claude        -b agent/scaffold

# Each agent works in its own directory
# Supervisor reviews and merges each branch into main

# Merge workflow
git checkout main
git merge --no-ff agent/config    # After supervisor review
git merge --no-ff agent/database
# Run full test suite after each merge
uv run pytest
```

### 23.6 CLAUDE.md — Full Specification

```markdown
# PvX — Claude Code Build Instructions

## What This Project Is
PvX is a locally hosted, open source, agentic multi-model
orchestration platform that ships as an MCP server.
Read docs/PvX_Blueprint_v0.8.md before any architectural decision.

## Your Role
You are the SUPERVISOR agent.
Use the Task tool to delegate focused subtasks to sub-agents.
Review every sub-agent output against the checklist below.
Update docs/TASK_BOARD.md as tasks complete.
Never commit unreviewed code.

## Tech Stack — Use These Only
- Python 3.11+
- uv for all package management (never pip directly)
- FastAPI + uvicorn for web server
- SQLModel + aiosqlite for database
- ollama-python for Ollama client
- pynvml (primary) + nvidia-smi (fallback) for VRAM
- mcp (Anthropic) for MCP server implementation
- anthropic for any direct API calls
- structlog for ALL logging (never use print())
- Pydantic v2 for all data models and config validation
- tiktoken for token counting
- httpx for HTTP client
- pytest + pytest-asyncio for all tests
- ruff for linting and formatting
- React + Tailwind for frontend (Phase 4)

## CLI Invocation — Critical
Claude Code is invoked as a SUBPROCESS, not SDK:
  claude --print -p "prompt"                    # Claude Code

## Claude Code's Role In Classification
Claude Code acts as the primary classifier.
If Claude Code is unavailable, the system falls back to keyword-based classification.
This is handled automatically by TaskClassifier.

## Architectural Rules — Never Violate
1. nvmlInit() called ONCE in VRAMManager.__init__()
   Cached as self._nvml_handle
   nvmlShutdown() called ONCE in shutdown()
   NEVER call nvmlInit() inside poll()

2. SQLite WAL mode on EVERY connection, no exceptions:
   PRAGMA journal_mode=WAL;
   PRAGMA synchronous=NORMAL;

3. ALWAYS use .total_seconds() on timedelta objects
   NEVER use .seconds — only returns seconds component
   A 6min 30s timedelta: .seconds=30, .total_seconds()=390

4. ALWAYS use Path.is_relative_to() for path validation
   NEVER use str.startswith() — has bypass vectors

5. JSON extraction uses balanced brace parser
   NEVER use r'\{[^{}]+\}' — fails on nested objects

6. Keyword fallback uses KEYWORD_PRIORITY list order
   First match wins — no arbitrary tie-breaking

7. All writes to SQLite go through async write queue
   Never write directly to SQLite from multiple coroutines

## Sub-Agent Review Checklist
Run this on every sub-agent output before accepting:
□ Matches blueprint specification exactly?
□ Tests written and passing?
□ No unapproved dependencies?
□ .total_seconds() — never .seconds?
□ Path.is_relative_to() — never startswith()?
□ WAL mode on all SQLite connections?
□ nvmlInit() only in __init__()?
□ structlog only — never print()?
□ Type hints on all functions?
□ Blueprint gap found → written to docs/ISSUES.md?

## Current Build State
Current phase: PHASE 0 — Foundation
Update this line every session start.

## Commands
uv run pytest              Run all tests
uv run pvx start           Start the platform
uv add <package>           Add dependency
uv run ruff format .       Format code
uv run ruff check .        Lint code
git worktree list          See all agent worktrees

## When Unsure
1. Check blueprint first — docs/PvX_Blueprint_v0.8.md
2. Check ISSUES.md for known gaps
3. Ask user before implementing anything not in blueprint
4. Never invent architecture not in blueprint
```

---

## 22. Future Roadmap

### v0.2 — Multi-GPU + Auto-tuning
```
□ GPU assignment per model
□ Parallel local model execution (multi-GPU)
□ Benchmarking protocol per model on user hardware
□ Routing rule auto-tuning based on task outcomes
□ Token throughput tracking per model per task type
```

### v0.3 — RAG Integration
```
□ Vector database (ChromaDB local)
□ Project-level knowledge base
□ Automatic context enrichment from codebase
□ Document ingestion pipeline
```

### v0.4 — Agent Teams
```
□ Named agent teams with defined roles
□ Automatic task distribution within teams
□ Consensus voting on outputs (majority rules)
□ Adversarial review (two models critique each other)
```

### v0.5 — Plugin System
```
□ Community MCP server plugins
□ Custom routing rule plugins
□ Custom classifier plugins
□ UI widget plugins
```

### v1.0 — Production Ready
```
□ Multi-user support
□ Authentication + RBAC
□ Rate limiting per user
□ Horizontal scaling
□ Full documentation site
□ 90%+ test coverage
□ Windows support
```

---

*PvX Blueprint v0.9 — April 2026*
*Incorporates critique from Claude Opus 4.6, engineering reviews, distribution design, adversarial security review, integration specification, and build agent strategy, single-CLI architecture*
*License: Apache 2.0*
*Built for the developer who refuses to be limited by their hardware.*
