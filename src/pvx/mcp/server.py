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

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

logger: structlog.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

pvx_server: Server = Server("pvx")


# ---------------------------------------------------------------------------
# Handler — wired to live PvX subsystems via app_state
# ---------------------------------------------------------------------------


class PvXMCPHandler:
    """
    Dispatches MCP tool calls to live PvX subsystems via app_state.

    Reads from pvx.main.app_state at call time (not at import time) so the
    server module can be imported before `pvx start` initialises state.
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
        from pvx.main import app_state  # late import — avoids circular at module load
        if app_state is None:
            return {"error": "PvX not started — run `pvx start` first"}

        import uuid
        from datetime import datetime
        from pvx.core.tasks import Task

        # Classify the prompt when no category is explicitly provided.
        # Runs the full keyword → cache → Claude escalation chain.
        if category:
            cat = category
        else:
            classification = app_state.classifier.classify(prompt)
            cat = classification.category
            logger.debug("mcp_task_classified",
                         category=cat,
                         confidence=classification.confidence,
                         classified_by=classification.classified_by)

        task = Task(
            id=f"task_{uuid.uuid4().hex[:12]}",
            model=model or "",
            prompt=prompt,
            category=cat,
            status="pending",
            priority=max(1, min(5, priority)),
            depends_on=[],
            requires_vram=True,
            requires_system_idle=False,
            retry_count=0,
            max_retries=3,
            created_at=datetime.now(),
        )
        # Route if model not forced
        if not model:
            task.model = app_state.router.route(task)

        app_state.queue.pending_tasks.append(task)
        logger.info("mcp_submit_task", task_id=task.id, model=task.model,
                    priority=priority, category=cat)
        return {"task_id": task.id, "status": "pending", "model": task.model,
                "category": cat}

    # ------------------------------------------------------------------
    # get_task_status
    # ------------------------------------------------------------------

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        from pvx.main import app_state
        if app_state is None:
            return {"error": "PvX not started"}

        task = next((t for t in app_state.queue.pending_tasks if t.id == task_id), None)
        if task is None:
            return {"error": "task_not_found", "task_id": task_id}

        return {
            "task_id": task.id,
            "status": task.status,
            "model": task.model,
            "priority": task.priority,
            "category": task.category,
            "output": task.output,
            "error": task.error,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    # ------------------------------------------------------------------
    # list_tasks
    # ------------------------------------------------------------------

    async def list_tasks(self) -> dict[str, Any]:
        from pvx.main import app_state
        if app_state is None:
            return {"error": "PvX not started", "tasks": []}

        tasks = [
            {
                "task_id": t.id,
                "status": t.status,
                "model": t.model,
                "priority": t.priority,
                "category": t.category,
                "created_at": t.created_at.isoformat(),
            }
            for t in app_state.queue.pending_tasks
        ]
        return {"tasks": tasks, "count": len(tasks)}

    # ------------------------------------------------------------------
    # get_vram_status
    # ------------------------------------------------------------------

    async def get_vram_status(self) -> dict[str, Any]:
        from pvx.main import app_state
        if app_state is None:
            return {"error": "PvX not started"}

        state = app_state.vram.poll()
        # Include live Ollama ground truth alongside our tracked state
        actually_loaded = app_state.vram.get_actually_loaded_models()
        return {
            "total_mb": state.total_mb,
            "used_mb": state.used_mb,
            "free_mb": state.free_mb,
            "gpu_utilisation_pct": state.gpu_utilisation_pct,
            "vram_state": app_state.vram.state.value,
            "loaded_model": app_state.vram.get_loaded_model(),
            "ollama_loaded_models": actually_loaded,
        }

    # ------------------------------------------------------------------
    # cancel_task
    # ------------------------------------------------------------------

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        from pvx.main import app_state
        if app_state is None:
            return {"error": "PvX not started"}

        task = next((t for t in app_state.queue.pending_tasks if t.id == task_id), None)
        if task is None:
            return {"error": "task_not_found", "task_id": task_id}
        if task.status in ("done", "failed"):
            return {"error": f"task_already_{task.status}", "task_id": task_id}

        task.status = "failed"
        task.error = "CANCELLED_BY_USER"
        logger.info("mcp_cancel_task", task_id=task_id)
        return {"task_id": task_id, "status": "cancelled"}


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

        else:
            log.warning("unknown tool requested", tool=name)
            result = {
                "error": f"Unknown tool: '{name}'",
                "available_tools": [
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
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import anyio

    anyio.run(run_server)
