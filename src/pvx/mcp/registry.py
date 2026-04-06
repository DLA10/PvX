"""
MCP Tool Registry — maps MCP tool names to handler functions.

This is the bridge between the MCP server's call_tool dispatcher and the
actual tool implementations (FilesystemTool, PostgresTool, GitHubTool,
DiscordTool). Only tools whose corresponding service block is present and
enabled in AppConfig are registered; everything else is a no-op.
"""

import asyncio
import inspect
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog

from pvx.core.config import AppConfig
from pvx.mcp.proxy import ToolCall, ToolResult
from pvx.mcp.tools.discord import DiscordTool
from pvx.mcp.tools.filesystem import FilesystemTool
from pvx.mcp.tools.github import GitHubTool
from pvx.mcp.tools.postgres import PostgresTool

log: structlog.BoundLogger = structlog.get_logger(__name__)

# Each entry is (bound_method, ordered_param_names_for_positional_kwarg_dispatch)
_HandlerEntry = Tuple[Callable[..., Any], List[str]]


def _run_coroutine(coro: Any) -> Any:
    """Execute a coroutine from a synchronous context.

    Creates a fresh event loop when no running loop exists (the normal
    case when called from the MCP server's sync dispatch path), and
    re-uses the existing loop only when already inside one (e.g. tests
    that patch asyncio).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # We are already inside an async context — schedule on the loop and
        # block the *current* thread with a Future.  This happens in tests.
        import concurrent.futures

        future: concurrent.futures.Future[Any] = concurrent.futures.Future()

        async def _runner() -> None:
            try:
                result = await coro
                future.set_result(result)
            except Exception as exc:  # noqa: BLE001
                future.set_exception(exc)

        loop.create_task(_runner())
        return future.result(timeout=60)

    # Normal path: no running loop — create one just for this call.
    return asyncio.run(coro)


class MCPRegistry:
    """Registry that maps MCP tool names to their handler methods.

    Attributes
    ----------
    _handlers:
        Mapping of tool name → (bound callable, list of parameter names in
        declaration order).  The parameter list is used to extract the right
        keys from ``ToolCall.params`` and pass them as keyword arguments.
    """

    def __init__(self, config: AppConfig) -> None:
        self._handlers: Dict[str, _HandlerEntry] = {}

        if config.mcp_servers is None:
            log.info("mcp_registry.no_servers_configured")
            return

        servers = config.mcp_servers

        # --- Filesystem ---
        if servers.filesystem is not None and servers.filesystem.enabled:
            fs_cfg = servers.filesystem
            fs_tool = FilesystemTool(
                allowed_paths=fs_cfg.allowed_paths,
                blocked_paths=fs_cfg.blocked_paths,
            )
            self._register("read_file", fs_tool.read_file)
            self._register("write_file", fs_tool.write_file)
            self._register("list_directory", fs_tool.list_directory)
            log.info("mcp_registry.registered_tool_group", group="filesystem")

        # --- PostgreSQL ---
        if servers.postgresql is not None and servers.postgresql.enabled:
            pg_cfg = servers.postgresql
            pg_tool = PostgresTool(
                connection_str=pg_cfg.connection,
                allowed_ops=pg_cfg.allowed_operations,
                blocked_ops=pg_cfg.blocked_operations,
                max_rows=pg_cfg.max_result_rows,
            )
            self._register("query_database", pg_tool.query)
            log.info("mcp_registry.registered_tool_group", group="postgresql")

        # --- GitHub ---
        if servers.github is not None and servers.github.enabled:
            gh_cfg = servers.github
            gh_tool = GitHubTool(
                token=gh_cfg.token,
                allowed_repos=gh_cfg.allowed_repos,
            )
            self._register("get_repo_contents", gh_tool.get_repo_contents)
            self._register("create_issue", gh_tool.create_issue)
            log.info("mcp_registry.registered_tool_group", group="github")

        # --- Discord ---
        if servers.discord is not None and servers.discord.enabled:
            dc_cfg = servers.discord
            dc_tool = DiscordTool(
                bot_token=dc_cfg.bot_token,
                allowed_channels=dc_cfg.allowed_channels,
            )
            self._register("send_discord_message", dc_tool.send_message)
            log.info("mcp_registry.registered_tool_group", group="discord")

        log.info(
            "mcp_registry.initialised",
            registered_tools=list(self._handlers.keys()),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register(self, tool_name: str, method: Callable[..., Any]) -> None:
        """Register *method* under *tool_name*.

        The parameter names are extracted from the method signature (excluding
        ``self``) so that ``execute`` can pull the right keys from
        ``ToolCall.params`` in declaration order.
        """
        sig = inspect.signature(method)
        param_names: List[str] = [
            name
            for name, param in sig.parameters.items()
            if param.kind
            not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
        ]
        self._handlers[tool_name] = (method, param_names)
        log.debug("mcp_registry.tool_registered", tool=tool_name, params=param_names)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_available_tools(self) -> List[str]:
        """Return the list of currently registered tool names."""
        return list(self._handlers.keys())

    def execute(self, tool_call: ToolCall) -> ToolResult:
        """Dispatch *tool_call* to the appropriate handler.

        Parameters
        ----------
        tool_call:
            The parsed tool call containing a ``name`` and a ``params`` dict.

        Returns
        -------
        ToolResult
            ``output`` is a JSON-serialised string of the handler's return
            value on success.  ``error`` is set on any failure.
        """
        tool_name = tool_call.name

        if tool_name not in self._handlers:
            log.warning("mcp_registry.unknown_tool", tool=tool_name)
            return ToolResult(error=f"Unknown tool: '{tool_name}'")

        handler, param_names = self._handlers[tool_name]

        # Build keyword arguments from ToolCall.params using the declared
        # parameter names so we forward only what the handler expects.
        kwargs: Dict[str, Any] = {}
        missing: List[str] = []
        for name in param_names:
            if name in tool_call.params:
                kwargs[name] = tool_call.params[name]
            else:
                missing.append(name)

        if missing:
            log.warning(
                "mcp_registry.missing_params",
                tool=tool_name,
                missing=missing,
            )
            return ToolResult(
                error=f"Tool '{tool_name}' is missing required parameters: {missing}"
            )

        log.debug("mcp_registry.dispatching", tool=tool_name, kwargs=list(kwargs.keys()))

        try:
            if inspect.iscoroutinefunction(handler):
                raw_result = _run_coroutine(handler(**kwargs))
            else:
                raw_result = handler(**kwargs)

            output = json.dumps(raw_result)
            log.info("mcp_registry.tool_success", tool=tool_name)
            return ToolResult(output=output)

        except Exception as exc:  # noqa: BLE001
            log.exception("mcp_registry.tool_error", tool=tool_name, error=str(exc))
            return ToolResult(error=f"Tool '{tool_name}' raised an exception: {exc}")
