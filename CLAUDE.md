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
2. Build the 4 components listed in "Claude Builds" below
3. Update docs/TASK_BOARD.md with review results
Never commit unreviewed code.

## Claude Builds — These 4 Components Only

### 1. `models/claude.py` — ClaudeCodeModel (Every Phase)
You know your own CLI. Build this, not Gemini.
- Subprocess invocation: `claude --print -p "prompt"`
- ANSI escape code stripping from stdout
- Rate limit detection via stderr pattern matching:
    "rate_limit_error", "Too many requests", "overloaded_error", "529"
- Timeout handling (180s), FileNotFoundError handling
- Circuit breaker integration
- `is_available()` via `claude --version` check
Gemini leaves this as a stub shell. Claude implements it fully.

### 2. `_classify_via_cli()` in `core/classifier.py` (Phase 1)
The escalation prompt sent to `claude --print` must be written by Claude.
Claude knows what prompt structure produces reliable JSON from itself.
Gemini builds the full TaskClassifier (keyword logic, caching, structure)
but leaves `_classify_via_cli` as `raise NotImplementedError`.
Claude fills it in after Gemini's Phase 1 is reviewed.

### 3. `mcp/server.py` — MCP Server (Phase 3)
PvX ships as an MCP server using Anthropic's own `mcp` Python SDK.
Claude has authoritative knowledge of:
- Tool registration and schema format
- stdio transport setup and lifecycle
- How Claude Code discovers and calls MCP tools
Gemini does not build this file at all.

### 4. `mcp/security.py` — Security Validation Layer (Phase 2)
The blueprint requires adversarial review of this module before v0.1 ship.
Local LLMs at Q4 produce creative bypass attempts not covered by naive
pattern matching. Claude writes and adversarially reviews this module.
Gemini does not build this file at all.

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
