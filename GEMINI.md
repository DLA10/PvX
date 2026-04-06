# PvX — Gemini CLI Build Instructions

## What This Project Is
PvX is a locally hosted, open source, agentic multi-model
orchestration platform that ships as an MCP server.
Read docs/PvX_Blueprint_v0.9.md before any architectural decision.

## Your Role
You are the primary BUILD agent.
Update docs/TASK_BOARD.md and docs/ISSUES.md as tasks complete.
Never commit unreviewed code unless instructed by the user.

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

## Target Architecture (CLI Invocation)
The PvX platform we are building invokes its configured cloud CLI (e.g., Claude Code or Gemini) as a SUBPROCESS, not SDK. For example, if configured for Claude:
  claude --print -p "prompt"

## The Configured CLI's Role In Classification
The configured CLI acts as the primary classifier.
If it is unavailable, the system falls back to keyword-based classification.
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

## Build Checklist
Run this internally before accepting your own output:
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
Current phase: PHASE 1 — Core Engine
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

---
## Claude-Owned Files — Do Not Implement

The following files are built by the Claude reviewer, not Gemini. For each one, create the file with an empty class/stub and a comment, then move on. Do not write any logic inside them.

Phase 1

models/claude.py — Leave as:
class ClaudeCodeModel(BaseModelInterface):
    """Claude Code subprocess wrapper — implemented by Claude reviewer."""
    pass

_classify_via_cli() inside core/classifier.py — Build the full TaskClassifier (keyword logic, caching, classify() flow, _classify_keywords()) but leave this one method as:
def _classify_via_cli(self, prompt: str, keyword_hint: ClassificationResult) -> ClassificationResult:
    raise NotImplementedError("Implemented by Claude reviewer.")

Phase 2

Nothing to skip. Build everything in Phase 2 fully.

Critical: The blueprint Phase 2 description says "ContextCompressor (CLI-backed)" — this is outdated. The v0.9 spec (Section 7.5) is the authority: ContextCompressor uses Qwen-3B locally via Ollama, not Claude subprocess. Build it with Qwen-3B.

Phase 3

mcp/server.py — Leave as:
# MCP server — implemented by Claude reviewer.

mcp/registry.py — Leave as:
# MCP tool registry — implemented by Claude reviewer.

mcp/security.py — Leave as:
# Security validation layer — implemented by Claude reviewer (adversarial review required).

Build everything else in Phase 3 fully: mcp/proxy.py, mcp/tools/postgres.py, mcp/tools/filesystem.py, mcp/tools/github.py, mcp/tools/discord.py.

Phase 4a and Phase 4b

Nothing to skip. Build everything fully.

Phase 5

mcp-config.json — Do not create this file. Claude writes it.

Build everything else in Phase 5 fully: release.yml, README, Docker Compose updates, PyPI build config.
