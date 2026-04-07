"""
PvX MCP Server — exposes PvX capabilities to Claude Code via the MCP protocol.

This module is the entry point for Claude Code's tool discovery and invocation.
It runs over stdio transport using Anthropic's official `mcp` Python SDK.

Claude Code discovers available tools via list_tools, then invokes them via
call_tool. Each tool call is dispatched through PvXMCPHandler, which is wired
to live subsystems via app_state.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

logger: structlog.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

pvx_server: Server = Server("pvx")

# Base URL of the PvX REST API — same machine, different process.
_API_BASE = "http://127.0.0.1:8000"
_TIMEOUT  = 30.0  # seconds


def _api(path: str) -> str:
    return f"{_API_BASE}{path}"


def _unavailable(detail: str = "") -> dict[str, Any]:
    msg = "PvX backend not reachable at localhost:8000 — is `pvx start` running?"
    if detail:
        msg += f" ({detail})"
    return {"error": msg}


# ---------------------------------------------------------------------------
# Handler — calls PvX REST API over HTTP (separate process from pvx start)
# ---------------------------------------------------------------------------


class PvXMCPHandler:
    """
    Dispatches MCP tool calls to the PvX REST API via HTTP.

    pvx-mcp runs as a stdio subprocess launched by Claude Code.
    pvx start runs as a separate process serving the REST API on :8000.
    These two processes do NOT share memory — all communication goes
    through the HTTP API.
    """

    # ------------------------------------------------------------------
    # submit_task
    # ------------------------------------------------------------------

    async def submit_task(
        self,
        prompt: str,
        model: str | None = None,
        priority: int = 3,
        category: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "prompt": prompt,
            "priority": max(1, min(5, priority)),
        }
        if model:
            payload["model"] = model
        if category:
            payload["category"] = category

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.post(_api("/api/tasks/"), json=payload)
                r.raise_for_status()
                data = r.json()
                logger.info("mcp_submit_task", task_id=data.get("task_id"),
                            model=data.get("model"), category=data.get("category"))
                return data
        except httpx.ConnectError as exc:
            return _unavailable(str(exc))
        except httpx.HTTPStatusError as exc:
            return {"error": f"API error {exc.response.status_code}",
                    "detail": exc.response.text}

    # ------------------------------------------------------------------
    # get_task_status
    # ------------------------------------------------------------------

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.get(_api(f"/api/tasks/{task_id}"))
                if r.status_code == 404:
                    return {"error": "task_not_found", "task_id": task_id}
                r.raise_for_status()
                return r.json()
        except httpx.ConnectError as exc:
            return _unavailable(str(exc))
        except httpx.HTTPStatusError as exc:
            return {"error": f"API error {exc.response.status_code}",
                    "detail": exc.response.text}

    # ------------------------------------------------------------------
    # list_tasks
    # ------------------------------------------------------------------

    async def list_tasks(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.get(_api("/api/tasks/"))
                r.raise_for_status()
                tasks = r.json()
                return {"tasks": tasks, "count": len(tasks)}
        except httpx.ConnectError as exc:
            return _unavailable(str(exc))
        except httpx.HTTPStatusError as exc:
            return {"error": f"API error {exc.response.status_code}",
                    "detail": exc.response.text}

    # ------------------------------------------------------------------
    # get_vram_status
    # ------------------------------------------------------------------

    async def get_vram_status(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.get(_api("/api/vram/"))
                r.raise_for_status()
                return r.json()
        except httpx.ConnectError as exc:
            return _unavailable(str(exc))
        except httpx.HTTPStatusError as exc:
            return {"error": f"API error {exc.response.status_code}",
                    "detail": exc.response.text}

    # ------------------------------------------------------------------
    # list_available_models
    # ------------------------------------------------------------------

    async def list_available_models(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.get(_api("/api/models/available"))
                r.raise_for_status()
                return r.json()
        except httpx.ConnectError as exc:
            return _unavailable(str(exc))
        except httpx.HTTPStatusError as exc:
            return {"error": f"API error {exc.response.status_code}",
                    "detail": exc.response.text}

    # ------------------------------------------------------------------
    # cancel_task
    # ------------------------------------------------------------------

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.delete(_api(f"/api/tasks/{task_id}"))
                if r.status_code == 404:
                    return {"error": "task_not_found", "task_id": task_id}
                r.raise_for_status()
                return r.json()
        except httpx.ConnectError as exc:
            return _unavailable(str(exc))
        except httpx.HTTPStatusError as exc:
            return {"error": f"API error {exc.response.status_code}",
                    "detail": exc.response.text}


# Module-level handler instance shared by both decorators below.
_handler = PvXMCPHandler()


# ---------------------------------------------------------------------------
# Tool definitions — list_tools
# ---------------------------------------------------------------------------


@pvx_server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the full catalogue of PvX tools that Claude Code can invoke."""
    return [
        types.Tool(
            name="submit_task",
            description=(
                "Submit a new task to the PvX orchestration queue. "
                "PvX classifies the prompt automatically and routes the task to the "
                "most appropriate model (local via Ollama or Claude Code) based on "
                "VRAM availability and task category. Returns a task_id for polling."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The full prompt / instruction for the task.",
                    },
                    "model": {
                        "type": ["string", "null"],
                        "default": None,
                        "description": (
                            "Force a specific model identifier (e.g. 'qwen2.5-coder:7b-instruct-q4_K_M'). "
                            "Omit to let PvX route automatically based on task category."
                        ),
                    },
                    "priority": {
                        "type": "integer",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 5,
                        "description": (
                            "Task urgency. 5 = critical (preempts running tasks), "
                            "4 = high, 3 = normal (default), 2 = low, "
                            "1 = background (never preempts)."
                        ),
                    },
                    "category": {
                        "type": ["string", "null"],
                        "default": None,
                        "description": (
                            "Override the auto-classifier. Valid values: "
                            "complex_code, boilerplate, simple_refactor, formatting, "
                            "docstrings, algorithm_design, ml_pipeline, oop_design, "
                            "code_review, system_design, math_proof, chain_of_thought, "
                            "debugging_logic, large_context, codebase_analysis, "
                            "architecture, final_review. Omit for auto-detection."
                        ),
                    },
                },
                "required": ["prompt"],
            },
        ),
        types.Tool(
            name="get_task_status",
            description=(
                "Poll the current status of a previously submitted task. "
                "Returns state (pending / running / done / failed), "
                "the assigned model, category, and the result payload when complete. "
                "For live streaming output, use GET /api/tasks/{task_id}/stream instead."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID returned by submit_task.",
                    },
                },
                "required": ["task_id"],
            },
        ),
        types.Tool(
            name="list_tasks",
            description=(
                "Return a snapshot of all tasks currently known to PvX — "
                "queued, running, completed, and recently failed."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="get_vram_status",
            description=(
                "Query the current GPU VRAM state as seen by PvX. "
                "Returns total, used, and free VRAM in MiB, the currently loaded "
                "model (both PvX-tracked and live from Ollama /api/ps), "
                "and whether an external process is competing for the GPU."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="cancel_task",
            description=(
                "Request cancellation of a queued task. "
                "Pending tasks are immediately cancelled. "
                "Running tasks: Ollama will finish the current generation — "
                "cancellation prevents the result from being used but cannot "
                "interrupt mid-stream inference."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to cancel.",
                    },
                },
                "required": ["task_id"],
            },
        ),
        types.Tool(
            name="list_available_models",
            description=(
                "Discover all models available on this machine and hand the routing keys to Claude Code.\n\n"
                "Call this at the START of every session. It returns:\n"
                "- Every installed Ollama model with VRAM requirements, capability description, "
                "  whether it can load right now, and suggested task categories\n"
                "- Claude's own capabilities and suggested use cases\n"
                "- GPU summary (total/used/free VRAM, GPU%)\n"
                "- Hardware constraint (one Ollama model in VRAM at a time)\n\n"
                "After calling this, discuss the available models with the user, agree on a "
                "routing plan (which model handles which task types), then use explicit model= "
                "parameters in submit_task() calls rather than relying on PvX auto-routing. "
                "PvX auto-routing is a fallback only — YOU are the decision maker."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool dispatch — call_tool
# ---------------------------------------------------------------------------


@pvx_server.call_tool()
async def call_tool(
    name: str,
    arguments: dict[str, Any],
) -> list[types.TextContent]:
    """
    Dispatch an incoming tool call to the appropriate PvXMCPHandler method.

    All errors are caught and returned as a JSON-encoded TextContent so that
    Claude Code always receives a well-formed response rather than a protocol
    error.
    """
    log = logger.bind(tool=name)
    log.info("tool call received", arguments=arguments)

    try:
        result: dict[str, Any]

        if name == "submit_task":
            prompt: str = arguments["prompt"]
            result = await _handler.submit_task(
                prompt=prompt,
                model=arguments.get("model"),
                priority=int(arguments.get("priority", 3)),
                category=arguments.get("category"),
            )

        elif name == "get_task_status":
            result = await _handler.get_task_status(
                task_id=arguments["task_id"],
            )

        elif name == "list_tasks":
            result = await _handler.list_tasks()

        elif name == "get_vram_status":
            result = await _handler.get_vram_status()

        elif name == "cancel_task":
            result = await _handler.cancel_task(
                task_id=arguments["task_id"],
            )

        elif name == "list_available_models":
            result = await _handler.list_available_models()

        else:
            log.warning("unknown tool requested", tool=name)
            result = {
                "error": f"Unknown tool: '{name}'",
                "available_tools": [
                    "list_available_models",
                    "submit_task",
                    "get_task_status",
                    "list_tasks",
                    "get_vram_status",
                    "cancel_task",
                ],
            }

        log.info("tool call completed", tool=name, status=result.get("status"))
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    except KeyError as exc:
        error_payload = {
            "error": "missing_required_argument",
            "detail": f"Required argument not provided: {exc}",
            "tool": name,
        }
        log.error("missing argument in tool call", tool=name, missing=str(exc))
        return [types.TextContent(type="text", text=json.dumps(error_payload, indent=2))]

    except Exception as exc:  # noqa: BLE001
        error_payload = {
            "error": "internal_error",
            "detail": str(exc),
            "tool": name,
        }
        log.exception("unhandled error in tool call", tool=name)
        return [types.TextContent(type="text", text=json.dumps(error_payload, indent=2))]


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


async def run_server() -> None:
    """
    Start the PvX MCP server on stdio transport.

    Claude Code launches this process and communicates over stdin/stdout
    using the MCP JSON-RPC wire protocol.  The server runs until the
    parent process closes the pipe.
    """
    logger.info("pvx mcp server starting", transport="stdio")
    async with stdio_server() as (read_stream, write_stream):
        logger.info("stdio streams open, entering serve loop")
        await pvx_server.run(
            read_stream,
            write_stream,
            pvx_server.create_initialization_options(),
        )
    logger.info("pvx mcp server stopped")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def _sync_run() -> None:
    """
    Synchronous entry point for the `pvx-mcp` CLI command.

    Claude Code launches this as a subprocess and communicates over stdio.
    Add to Claude Code's MCP config:

        {"mcpServers": {"pvx": {"command": "pvx-mcp"}}}
    """
    import anyio
    anyio.run(run_server)


if __name__ == "__main__":
    _sync_run()
