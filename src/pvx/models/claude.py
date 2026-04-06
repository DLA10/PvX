import re
import subprocess
import time
from typing import List, Optional

import structlog

from pvx.models.base import BaseModelInterface, GenerationResult, Message

log = structlog.get_logger()


class ClaudeCodeModel(BaseModelInterface):
    """
    Invokes Claude Code CLI as a subprocess.

    Claude Code is a terminal program, not a Python SDK.
    PvX shells out to it via subprocess for non-interactive tasks.

    Invocation (non-interactive print mode):
        claude --print -p "<prompt>"

    --print flag: outputs response to stdout and exits immediately.
    Does not start an interactive session.

    Used for:
        ✅ Task classification (low-confidence escalation)
        ✅ Quality gate reviews
        ✅ Architecture decisions
        ❌ Multi-step agentic file-system workflows (user initiates those directly)

    Authentication:
        Claude Code uses ANTHROPIC_API_KEY env var or ~/.claude/credentials.json.
        PvX never handles or stores credentials.
    """

    CLAUDE_CMD = "claude"
    TIMEOUT_SECONDS = 180

    # Patterns detected in stderr that indicate rate limiting.
    # Claude does not use clean exit codes for rate limits —
    # detection must be done via stderr string matching.
    RATE_LIMIT_PATTERNS = [
        "rate_limit_error",
        "Too many requests",
        "overloaded_error",
        "529",
    ]

    # ANSI escape sequence pattern — claude --print may emit coloured output.
    # Without stripping, the JSON classifier parser fails on raw ANSI bytes.
    _ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[mGKHF]')

    def __init__(self, circuit_breaker=None) -> None:
        self.circuit_breaker = circuit_breaker

    def generate(self, prompt: str, history: List[Message],
                 tools: Optional[List[dict]] = None,
                 task_id: Optional[str] = None) -> GenerationResult:

        if self.circuit_breaker and not self.circuit_breaker.is_allowed():
            log.warning("claude_circuit_open", task_id=task_id)
            return GenerationResult(
                content="",
                tokens_used=0,
                model="claude",
                duration_ms=0,
                error="CLAUDE_CIRCUIT_OPEN",
            )

        full_prompt = self._build_prompt(history, prompt)
        cmd = [self.CLAUDE_CMD, "--print", "-p", full_prompt]

        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            log.error("claude_timeout", task_id=task_id, timeout=self.TIMEOUT_SECONDS)
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            return GenerationResult(
                content="", tokens_used=0, model="claude",
                duration_ms=self.TIMEOUT_SECONDS * 1000,
                error="CLAUDE_TIMEOUT",
            )
        except FileNotFoundError:
            log.error("claude_not_found", hint="Install: npm install -g @anthropic-ai/claude-code")
            return GenerationResult(
                content="", tokens_used=0, model="claude",
                duration_ms=0,
                error="CLAUDE_CODE_NOT_FOUND",
            )

        duration_ms = int((time.time() - start) * 1000)
        stderr = result.stderr.decode(errors="replace")

        # Rate limit detection via stderr pattern matching.
        # Must be checked before returncode — rate limits may still exit 0.
        if any(pat in stderr for pat in self.RATE_LIMIT_PATTERNS):
            log.warning("claude_rate_limited", task_id=task_id, stderr_preview=stderr[:200])
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            return GenerationResult(
                content="", tokens_used=0, model="claude",
                duration_ms=duration_ms,
                error="CLAUDE_RATE_LIMITED",
            )

        if result.returncode != 0:
            log.error("claude_error", returncode=result.returncode, stderr=stderr[:500])
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            return GenerationResult(
                content="", tokens_used=0, model="claude",
                duration_ms=duration_ms,
                error=f"CLAUDE_ERROR: {stderr[:500]}",
            )

        content = result.stdout.decode(errors="replace")

        # Strip ANSI escape sequences before any downstream parsing.
        content = self._ANSI_ESCAPE.sub("", content).strip()

        if self.circuit_breaker:
            self.circuit_breaker.record_success()

        log.info("claude_response", task_id=task_id, duration_ms=duration_ms,
                 preview=content[:80])

        return GenerationResult(
            content=content,
            tokens_used=0,   # --print mode does not expose token count
            model="claude",
            duration_ms=duration_ms,
        )

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                [self.CLAUDE_CMD, "--version"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def name(self) -> str:
        return "claude"

    def _build_prompt(self, history: List[Message], prompt: str) -> str:
        """
        Flatten history + current prompt into a single string for --print mode.
        Claude Code --print does not accept structured message history,
        so prior turns are prefixed inline.
        """
        if not history:
            return prompt

        parts = []
        for msg in history:
            prefix = "User" if msg.role == "user" else "Assistant"
            parts.append(f"{prefix}: {msg.content}")
        parts.append(f"User: {prompt}")
        return "\n\n".join(parts)
