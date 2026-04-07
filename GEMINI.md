# PvX — Gemini CLI Build Instructions

## What This Project Is
PvX is a locally hosted, open source, agentic multi-model
orchestration platform that ships as an MCP server.
Read docs/PvX_Blueprint_v0.9.md before any architectural decision.

## Your Role
You are the primary BUILD agent. Claude is the reviewer.
Update docs/TASK_BOARD.md and docs/ISSUES.md as tasks complete.
Never commit unreviewed code unless instructed by the user.

---

## CURRENT STATE — ALL PHASES COMPLETE

**Do not rebuild anything already done. Read this section first.**

Everything below is already built, tested, and pushed to main.
CI is green. 77 tests passing. Latest commit: 5046739

### What exists and works

**Backend (src/pvx/)**
- `core/classifier.py` — TaskClassifier: keyword → cache → Claude CLI escalation
- `core/router.py` — TaskRouter: config-driven routing with fallback chains
- `core/queue.py` — TaskQueueEngine: affinity batching, starvation guard, streaming buffer, pruning
- `core/vram.py` — VRAMManager: pynvml + nvidia-smi fallback, zombie detection, idle eviction
- `core/compressor.py` — ContextCompressor: Qwen-3B local compression at 70% context threshold
- `core/tasks.py` — Task dataclass with full state machine
- `core/events.py` — EventBus: in-memory pub/sub + SQLite persistence
- `core/circuit_breaker.py` — CircuitBreaker per model
- `core/recovery.py` — Error recovery matrix
- `core/model_discovery.py` — Auto-discovers Ollama models, assigns routing rules
- `models/claude.py` — ClaudeCodeModel: subprocess invocation, ANSI strip, rate limit detection
- `models/ollama.py` — OllamaModel: streaming generation with register_streaming_token callback
- `models/base.py` — BaseModelInterface, Message, GenerationResult
- `mcp/server.py` — MCP server (stdio transport, 5 tools exposed to Claude Code)
- `mcp/registry.py` — MCPRegistry: filesystem, postgres, github, discord tools
- `mcp/security.py` — SecurityLayer: SQL injection, path traversal, command injection patterns
- `mcp/proxy.py` — MCPProxy with graceful re-prompt loop
- `mcp/tools/` — filesystem, postgres, github, discord tool implementations
- `store/database.py` — SQLite + WAL mode + async write queue
- `store/models.py` — Session, MessageRecord, EventRecord, TaskRecord SQLModel tables
- `main.py` — AppState, orchestration loop, idle eviction, zombie hysteresis, pvx CLI

**API (src/pvx/api/)**
- `routes/tasks.py` — POST/GET/DELETE /api/tasks/, POST /api/tasks/analyze
- `routes/vram.py` — GET /api/vram/, GET /api/vram/simple
- `routes/models.py` — GET/POST /api/models/load, /api/models/unload
- `routes/stream.py` — GET /api/tasks/{id}/stream (SSE)
- `routes/stats.py` — GET /api/stats/session (tokens/model, GPT-4o cost, compressions)
- `routes/chat.py` — GET /api/chat/models, POST /api/chat/{model}/stream (SSE direct chat)
- `app.py` — FastAPI app, WebSocket /ws/events, CORS, all routers registered

**Frontend (ui/)**
- Vite 5 + React 18 + Tailwind 3 (replaced broken react-scripts)
- Retro terminal aesthetic: pure black, maroon borders, orange glow, CRT scanlines
- `Dashboard.jsx` — live VRAM bar, GPU%, loaded model, task queue stats, tokens/model
- `Feed.jsx` — TASKS view (2s poll) + EVENTS view (WebSocket /ws/events live push)
- `DirectChat.jsx` — SSE streaming chat direct to Ollama, bypass queue
- `CostTracker.jsx` — tokens/model, GPT-4o equivalent cost, savings %, compressions
- `Sidebar.jsx` — nav: DASHBOARD, TASKS, DIRECT CHAT, COST, MODELS, CONFIG
- `ShadowTerminal.jsx` — interactive: submit, vram, tasks, clear, help commands
- Run: `cd ui && npm run dev` → http://localhost:3000

**Distribution**
- `pvx init` — copies bundled example config to CWD
- `pvx doctor` — checks GPU, Ollama, Claude CLI, config
- `pvx-mcp` — entry point for MCP server (Claude Code launches this)
- `mcp-config.json` — `{"mcpServers": {"pvx": {"command": "pvx-mcp"}}}`
- `LICENSE` — Apache 2.0
- `pyproject.toml` — full packaging with dev deps separated

---

## Critical Architecture Facts

### Two-process model — NEVER forget this
```
Claude Code terminal
    │ launches pvx-mcp as stdio subprocess
    ▼
pvx-mcp process  ←── calls REST API via httpx ──→  pvx start process
                                                      (FastAPI :8000)
```
`pvx-mcp` and `pvx start` are SEPARATE OS PROCESSES with SEPARATE MEMORY.
`mcp/server.py` handlers MUST use httpx HTTP calls to localhost:8000.
NEVER import `from pvx.main import app_state` in the MCP server — it is always None there.
This bug was fixed. Do not reintroduce it.

### Install after code changes
When changing Python source, the globally installed binary must be updated:
```bash
uv tool install --editable . --force
```
Otherwise Claude Code runs the old binary from ~/.local/bin/pvx-mcp.

---

## Routing Philosophy — CRITICAL ARCHITECTURAL DECISION

PvX does NOT auto-route by default. Claude Code is the decision maker.

The correct workflow:
1. Claude Code calls list_available_models() at session start
2. Claude Code shows the user what's installed and what the GPU can handle
3. Claude Code and user agree on a routing plan collaboratively
4. Claude Code uses explicit model= params in submit_task() calls

PvX auto-routing (keyword classifier → Claude escalation) is a FALLBACK ONLY,
invoked when model= is omitted. It is not the primary path.

This is the fundamental design: PvX discovers models and provides access ("hands the keys"),
Claude Code and the user decide routing strategy, PvX executes.

## What the User Is Doing Right Now

Testing the full MCP integration with the new routing workflow:
1. `pvx start` — backend on :8000
2. `cd ui && npm run dev` — dashboard on :3000
3. `claude` (new session) — Claude Code calls list_available_models() first,
   agrees routing plan with user, then submits tasks with explicit model= params

The new test flow: list_available_models → discuss routing → submit tasks with explicit
model= → watch tasks in dashboard → verify correct models were used.

If something breaks, the most likely causes are:
- Stale pvx-mcp binary (fix: `uv tool install --editable . --force`)
- Port 8000 already in use from a previous stale `pvx start` (fix: `kill $(lsof -ti:8000)`)
- WebSocket not connecting in dashboard (websockets package is installed — check npm build)

---

## Remaining Blueprint Items (Phase 4b — v0.1.1 scope)

These are NOT done and are the next things to build:

1. **Feed intervention controls** — Edit, Fork, Pause, Retry, Abort buttons in Feed.jsx
   wired to actual API calls (cancel = DELETE /api/tasks/{id}, retry = re-submit)

2. **Task Queue dependency graph** — Visual node/edge graph in a new QueueGraph.jsx panel
   showing task dependencies from task.depends_on field

3. **Session replay** — Load completed session from SQLite, replay events in feed

If user asks you to build any of these, check blueprint Section 15 first.

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
- Vite 5 + React 18 + Tailwind 3 for frontend

## Architectural Rules — Never Violate
1. nvmlInit() ONCE in VRAMManager.__init__() — NEVER inside poll()
2. SQLite WAL mode on EVERY connection
3. ALWAYS .total_seconds() on timedelta — NEVER .seconds
4. ALWAYS Path.is_relative_to() — NEVER str.startswith()
5. JSON extraction uses balanced brace parser — NEVER r'\{[^{}]+\}'
6. MCP server calls REST API via httpx — NEVER imports app_state
7. All SQLite writes through async write queue

## Build Checklist
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
□ After code change: uv tool install --editable . --force

## Commands
uv run pytest                          Run all tests (77 passing)
pvx start                              Start backend (port 8000)
pvx doctor                             Check deps + GPU
pvx init                               Create pvx.config.yaml
uv tool install --editable . --force   Reinstall after source changes
cd ui && npm run dev                   Start dashboard (port 3000)
uv run ruff check .                    Lint
uv run ruff format .                   Format
gh run list --limit 5                  Check CI

## When Unsure
1. Check blueprint first — docs/PvX_Blueprint_v0.9.md
2. Check ISSUES.md for known gaps
3. Ask user before implementing anything not in blueprint
4. Never invent architecture not in blueprint
