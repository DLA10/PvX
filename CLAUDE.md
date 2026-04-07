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

## Current Build State
**ALL PHASES COMPLETE. CI green on every commit.**

- Phase 1 ✅ Core Engine (models, classifier, queue, vram, orchestration)
- Phase 2 ✅ Context + Resilience (Qwen-3B compressor, idle eviction, pruning)
- Phase 3 ✅ MCP Layer (server, registry, security)
- Phase 4a ✅ API + Cost Tracker + Direct Chat
- Phase 4b ✅ Retro terminal dashboard (Vite + React + Tailwind)
- Phase 5 ✅ Distribution (pvx init, pvx-mcp, LICENSE, README, mcp-config.json)

**Last session work (update this each session):**
- Fixed MCP handler: was importing app_state directly (always None in MCP process).
  Now calls REST API over HTTP (httpx). File: src/pvx/mcp/server.py
- Fixed WebSocket: added websockets dependency (uvicorn was spamming warnings)
- Built Cost Tracker panel: GET /api/stats/session — tokens/model, GPT-4o equiv cost
- Built Direct Chat panel: POST /api/chat/{model}/stream — SSE streaming to Ollama
- Built retro terminal dashboard: maroon/orange on black, CRT scanlines, ASCII bars
- All CI passing. Latest commit: bdb7a92

**Next session — user wants to:**
Test the full MCP integration end-to-end:
1. `pvx start` in Terminal 1
2. `cd ui && npm run dev` in Terminal 2 → http://localhost:3000
3. `claude` in Terminal 3 → paste the test prompt below
4. Watch tasks appear live in the dashboard

**Test prompt to give Claude Code (paste in a fresh `claude` session):**
```
You have access to a PvX MCP server running at localhost:8000.
PvX is a local AI orchestration platform that routes tasks to local Ollama models.

Your MCP tools: submit_task, get_task_status, list_tasks, get_vram_status, cancel_task

TEST PLAN — do all steps in order:

STEP 1: Call get_vram_status(). Report VRAM available and loaded model.

STEP 2: submit_task(prompt="Write a Python dataclass called UserProfile with fields:
id (UUID), name (str), email (str), created_at (datetime). Include __post_init__
validation that email contains @. Add a to_dict() method.", priority=3)
Poll get_task_status every 5s until done. Report output and which model handled it.

STEP 3: submit_task(prompt="Implement a generic LRU cache in Python using OrderedDict.
Support get(key), put(key, value), configurable max_size. Type hints + thread safety
with Lock.", priority=3)
Poll until done. Report model and output.

STEP 4: submit_task(prompt="Review the architecture of a VRAM-aware task queue that
dispatches work to local LLMs. What are the top 3 failure modes and resilience
strategies for each?", priority=4, category="architecture")
Poll until done. This should route to claude.

STEP 5: Call list_tasks(). Report counts and models used.
STEP 6: Call get_vram_status() again. Report final VRAM state.

Final summary: Did all tools work? Correct routing? Any failures?
```

---

## How PvX Works — Architecture Summary

```
Claude Code (user's terminal)
    │  calls MCP tools via stdio
    ▼
pvx-mcp (subprocess, stdio transport)
    │  makes HTTP calls to localhost:8000
    ▼
pvx start (FastAPI on :8000)
    │  task queue + classifier + router
    ▼
Ollama (local GPU — qwen2.5-coder:7b or :3b)
    │  generates output
    ▼
result returned to Claude Code via get_task_status()
```

CRITICAL: pvx-mcp and pvx start are SEPARATE PROCESSES.
MCP handler MUST use httpx HTTP calls — never import app_state.
src/pvx/mcp/server.py is the authoritative file for this.

---

## API Endpoints (all at localhost:8000)

| Endpoint | Method | Purpose |
|---|---|---|
| /api/health | GET | Health + pvx_ready flag |
| /api/vram/ | GET | VRAM state, loaded model, GPU% |
| /api/tasks/ | GET | List all tasks |
| /api/tasks/ | POST | Submit task {prompt, priority, model, category} |
| /api/tasks/{id} | GET | Task detail + output |
| /api/tasks/{id} | DELETE | Cancel task |
| /api/tasks/{id}/stream | GET | SSE streaming output |
| /api/tasks/analyze | POST | Dry-run: classify + route without queuing |
| /api/models/ | GET | List models |
| /api/models/load | POST | Load model into VRAM |
| /api/models/unload | POST | Unload model from VRAM |
| /api/stats/session | GET | Tokens/model, GPT-4o equiv cost, compressions |
| /api/chat/models | GET | Available Ollama models for direct chat |
| /api/chat/{model}/stream | POST | SSE direct chat (bypasses queue) |
| /ws/events | WebSocket | Live event stream for dashboard |

## MCP Tools (exposed to Claude Code)

| Tool | What it does |
|---|---|
| submit_task(prompt, priority, model, category) | Queue a task, returns task_id |
| get_task_status(task_id) | Poll status + output |
| list_tasks() | All tasks snapshot |
| get_vram_status() | GPU VRAM + loaded model |
| cancel_task(task_id) | Cancel queued task |

## Dashboard (ui/)

Run: `cd ui && npm run dev` → http://localhost:3000
Panels:
- DASHBOARD (right sidebar) — live VRAM bar, GPU%, task queue counts, tokens, batch status
- FEED (centre) — TASKS view (2s poll) + EVENTS view (WebSocket /ws/events)
- DIRECT CHAT — SSE streaming chat direct to Ollama model
- COST — session token counts, GPT-4o equivalent cost, savings %
- CONFIG — read-only config reference
- SHADOW TERMINAL — type `submit <prompt>`, `vram`, `tasks`, `help`

Retro terminal aesthetic: pure black #000000, maroon borders, orange glow text,
ASCII █░ progress bars, CRT scanlines overlay.

---

## Known Bugs Fixed This Session

| Bug | Fix |
|---|---|
| MCP tools returned "PvX not started" always | Handler now calls REST API via httpx instead of importing app_state |
| WebSocket spam: "No supported WebSocket library" | Added `websockets` dependency |
| classifier never called on task submit | Wired in tasks.py POST handler |
| pkill -f ollama killed the server | Replaced with keep_alive=0 API call |
| task.model split-brain | task.model updated after router.route() |
| GENERAL_CATEGORIES never routed | Fixed in model_discovery.py |
| ContextCompressor never called | Wired into orchestration loop |
| Streaming buffer never freed | release_streaming_buffer() in finally block |
| No idle VRAM eviction | 120s idle → unload_model() |
| No task pruning | prune_completed_tasks() every 30s |
| Zombie false positives | 5-poll hysteresis before kill |
| react-scripts broken (UI) | Replaced with Vite 5 |

---

## Claude Builds — Complete List

| File | Phase | Status |
|---|---|---|
| `models/claude.py` | 1 | ✅ Done |
| `_classify_via_cli()` in `core/classifier.py` | 1 | ✅ Done |
| `mcp/server.py` | 3 | ✅ Done (HTTP fix applied) |
| `mcp/registry.py` | 3 | ✅ Done |
| `mcp/security.py` | 3 | ✅ Done |
| `ui/` (all files) | 4b | ✅ Done |
| `src/pvx/api/routes/stats.py` | 4a | ✅ Done |
| `src/pvx/api/routes/chat.py` | 4a | ✅ Done |
| `mcp-config.json` | 5 | ✅ Done |

---

## Tech Stack — Use These Only
- Python 3.11+
- uv for all package management (never pip directly)
- FastAPI + uvicorn + websockets for web server
- SQLModel + aiosqlite for database
- ollama-python for Ollama client
- nvidia-ml-py (primary, imports as pynvml) + nvidia-smi (fallback) for VRAM
- mcp (Anthropic) for MCP server implementation
- httpx for HTTP client (including MCP→API calls)
- structlog for ALL logging (never use print())
- Pydantic v2 for all data models and config validation
- tiktoken for token counting
- pytest + pytest-asyncio for all tests
- ruff for linting and formatting
- Vite 5 + React 18 + Tailwind 3 for frontend — `cd ui && npm run dev`

## Architectural Rules — Never Violate
1. nvmlInit() called ONCE in VRAMManager.__init__()
   NEVER call nvmlInit() inside poll()

2. SQLite WAL mode on EVERY connection:
   PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;

3. ALWAYS use .total_seconds() on timedelta — NEVER .seconds

4. ALWAYS use Path.is_relative_to() — NEVER str.startswith()

5. JSON extraction uses balanced brace parser — NEVER r'\{[^{}]+\}'

6. MCP server calls REST API via httpx — NEVER imports app_state

7. All SQLite writes go through async write queue

## Commands
uv run pytest              Run all tests (77 passing)
pvx start                  Start the platform (port 8000)
pvx doctor                 Check dependencies + GPU
pvx init                   Create pvx.config.yaml in CWD
pvx-mcp                    Start MCP server (Claude Code launches this)
cd ui && npm run dev       Start dashboard (port 3000)
uv run ruff check .        Lint
uv run ruff format .       Format
gh run list --limit 5      Check CI status

## Review Checklist
□ Matches blueprint specification exactly?
□ Tests written and passing?
□ No unapproved dependencies?
□ .total_seconds() — never .seconds?
□ Path.is_relative_to() — never startswith()?
□ WAL mode on all SQLite connections?
□ nvmlInit() only in __init__()?
□ structlog only — never print()?
□ Type hints on all functions?
□ MCP handler uses httpx — never app_state import?

## When Unsure
1. Check blueprint first — docs/PvX_Blueprint_v0.9.md
2. Check ISSUES.md for known gaps
3. Ask user before implementing anything not in blueprint
4. Never invent architecture not in blueprint
