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

**`ui/` — Retro Terminal Dashboard** ✅ COMPLETE
Claude built the full UI (Gemini left static mockup with hardcoded data).
- Vite 5 + React 18 + Tailwind 3 (replaced broken react-scripts)
- Full black background, maroon/orange CRT terminal aesthetic
- `Dashboard.jsx` — live VRAM gauge, GPU%, loaded model, task queue stats (2s poll)
- `Feed.jsx` — task list + WebSocket /ws/events live event stream
- `Sidebar.jsx` — health check, session uptime, nav
- `ShadowTerminal.jsx` — interactive terminal: submit/vram/tasks/clear/help
- `App.jsx` — layout shell with Config routing
- Vite proxy: /api and /ws → localhost:8000 (no CORS issues)
- Run: `cd ui && npm install && npm run dev` → http://localhost:3000

---

### Phase 5 — Distribution + Polish

**`mcp-config.json` — Claude Code MCP Config Entry Point**
The JSON snippet that users add to Claude Code's config to register PvX
as an MCP server. Claude knows the exact format Claude Code expects.
Gemini does not create this file. Claude writes it.

---

## Summary Table

| File | Phase | Claude Builds | Status |
|---|---|---|---|
| `models/claude.py` | 1 | Full implementation | ✅ Done |
| `_classify_via_cli()` in `core/classifier.py` | 1 | Method only | ✅ Done |
| `mcp/server.py` | 3 | Full implementation | ✅ Done |
| `mcp/registry.py` | 3 | Full implementation | ✅ Done |
| `mcp/security.py` | 3 | Full implementation + adversarial review | ✅ Done |
| `ui/` (all files) | 4b | Full dashboard (Gemini left static mockup) | ✅ Done |
| `mcp-config.json` | 5 | Full file | ✅ Done |

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
- Vite 5 + React 18 + Tailwind 3 for frontend (Phase 4) — run via `cd ui && npm run dev`

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
Current phase: PHASE 5 COMPLETE — all phases shipped, CI green
- Phase 1 ✅ Core Engine (models, classifier, queue, vram, orchestration)
- Phase 2 ✅ Context + Resilience (compressor wired, idle eviction, pruning)
- Phase 3 ✅ MCP Layer (server, registry, security)
- Phase 4a ✅ API (FastAPI routes: tasks, vram, models, stream, health, ws)
- Phase 4b ✅ Retro terminal dashboard (ui/ — Vite + React + Tailwind)
- Phase 5 ✅ Distribution (pvx init, pvx-mcp entry point, LICENSE, README, mcp-config.json)
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
