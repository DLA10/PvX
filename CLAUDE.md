# PvX — Claude Code Build Instructions

## What This Project Is
PvX is a locally hosted, open source, agentic multi-model
orchestration platform that ships as an MCP server.
Read docs/PvX_Blueprint_v0.9.md before any architectural decision.

## Your Role
You are the REVIEWER agent.
Gemini CLI is the primary BUILD agent (see GEMINI.md for its instructions).
Your job is to:
1. Review Gemini's output against the checklist below and fix bugs
2. Build the specific components listed below — these are Claude-only
3. Update docs/TASK_BOARD.md with review results
Never commit unreviewed code.

---

## Claude Builds — Complete List Across All Phases

### Phase 1 — Core Engine

**`models/claude.py` — ClaudeCodeModel**
You know your own CLI. Gemini leaves this as an empty stub. Claude implements:
- Subprocess invocation: `claude --print -p "prompt"`
- ANSI escape code stripping from stdout (re.sub r'\x1b\[[0-9;]*[mGKHF]')
- Rate limit detection via stderr pattern matching:
    "rate_limit_error", "Too many requests", "overloaded_error", "529"
- Timeout: 180s. Handle FileNotFoundError (CLI not installed).
- `is_available()` check via `claude --version`
- circuit_breaker.record_failure() on rate limit hit
- tokens_used = 0 (--print mode does not expose token count)

**`_classify_via_cli()` in `core/classifier.py`**
Gemini builds the full TaskClassifier (keyword logic, caching, classify() flow)
but leaves this one method as `raise NotImplementedError`.
Claude writes the escalation prompt — Claude knows what prompt structure
produces reliable JSON from itself (format, constraints, output noise).

---

### Phase 2 — Context + Resilience

No Claude-owned files in Phase 2.
Gemini builds everything. Claude reviews.

IMPORTANT note to carry into Phase 2 review:
The blueprint Phase 2 description says "ContextCompressor (CLI-backed)"
but Section 7.5 (the authoritative spec) overrides this with Qwen-3B local.
v0.9 changelog explicitly changed the compressor from Claude to Qwen-3B.
If Gemini uses Claude subprocess for compression, flag it as a bug.

---

### Phase 3 — MCP Layer

**`mcp/server.py` — MCP Server**
PvX ships as an MCP server using Anthropic's own `mcp` Python SDK.
Claude has authoritative knowledge of:
- Tool registration and JSON schema format
- stdio transport setup and server lifecycle (serve_forever)
- How Claude Code discovers tools via MCP protocol
- Correct tool response format
Gemini leaves this as an empty stub. Claude implements fully.

**`mcp/registry.py` — MCP Tool Registry**
Tightly coupled to server.py. Registers which tools are available
and maps tool names to handler functions.
Gemini leaves this as an empty stub. Claude implements.

**`mcp/security.py` — Security Validation Layer**
The blueprint requires adversarial review before v0.1 ship:
"Local LLMs at Q4 produce creative variations of dangerous inputs
not covered by naive pattern matching."
Claude writes AND adversarially reviews this module.
Patterns needed: SQL injection, path traversal, command injection,
privilege escalation, hex encoding, UNION injection, CHAR() bypass,
LD_PRELOAD, chmod widening, curl|sh pipe attacks.
Gemini leaves this as an empty stub. Claude implements.

---

### Phase 4a — API + Core Web UI
No Claude-owned files. Gemini builds everything. Claude reviews.

### Phase 4b — Advanced UI
No Claude-owned files. Gemini builds everything. Claude reviews.

---

### Phase 5 — Distribution + Polish

**`mcp-config.json` — Claude Code MCP Config Entry Point**
The JSON snippet that users add to Claude Code's config to register PvX
as an MCP server. Claude knows the exact format Claude Code expects.
Gemini does not create this file. Claude writes it.

---

## Summary Table

| File | Phase | Claude Builds |
|---|---|---|
| `models/claude.py` | 1 | Full implementation |
| `_classify_via_cli()` in `core/classifier.py` | 1 | Method only (Gemini builds rest of file) |
| `mcp/server.py` | 3 | Full implementation |
| `mcp/registry.py` | 3 | Full implementation |
| `mcp/security.py` | 3 | Full implementation + adversarial review |
| `mcp-config.json` | 5 | Full file |

**Everything else across all phases → Gemini builds, Claude reviews.**

---

## Tech Stack — Use These Only
- Python 3.11+
- uv for all package management (never pip directly)
- FastAPI + uvicorn for web server
- SQLModel + aiosqlite for database
- ollama-python for Ollama client
- nvidia-ml-py (primary, imports as pynvml) + nvidia-smi (fallback) for VRAM
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
  claude --print -p "prompt"

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

## Review Checklist
Run this on every piece of Gemini's output before accepting:
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
Current phase: PHASE 1 — Core Engine (in progress)
Update this line every session start.

## Commands
uv run pytest              Run all tests
uv run pvx start           Start the platform
uv add <package>           Add dependency
uv run ruff format .       Format code
uv run ruff check .        Lint code

## When Unsure
1. Check blueprint first — docs/PvX_Blueprint_v0.9.md
2. Check ISSUES.md for known gaps
3. Ask user before implementing anything not in blueprint
4. Never invent architecture not in blueprint
