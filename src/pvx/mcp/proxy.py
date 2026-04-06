import json
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from pvx.core.events import event_bus

class ToolCall(BaseModel):
    name: str
    params: Dict[str, Any]

class ToolResult(BaseModel):
    output: Optional[str] = None
    error: Optional[str] = None

class MCPProxy:
    MAX_TOOL_RETRIES = 3

    def __init__(self, mcp_registry=None, security_layer=None):
        self.mcp_registry = mcp_registry
        self.security_layer = security_layer

    def execute_tool_call(self, model_output: str, available_tools: List[str], 
                          model_name: str, task=None, call_model_func=None) -> ToolResult:
        """
        Processes a tool call from the model output.
        """
        tool_call = self.parse_tool_call(model_output)

        if tool_call is None:
            return ToolResult(error="NO_TOOL_CALL_DETECTED")

        # Step 1: Validate tool exists
        if tool_call.name not in available_tools:
            return self.graceful_reprompt(
                model_name=model_name,
                task=task,
                attempted_tool=tool_call.name,
                available_tools=available_tools,
                attempt=1,
                call_model_func=call_model_func
            )

        # Step 2: Security validation
        if self.security_layer and not self.security_layer.validate(tool_call):
            event_bus.emit("SECURITY_REJECTED", {"tool": tool_call.name, "task_id": task.id if task else ""})
            return ToolResult(error=f"SECURITY_REJECTED: {tool_call.name}")

        # Step 3: Execute via registry (registry is stubbed but we define the flow)
        try:
            if self.mcp_registry:
                result = self.mcp_registry.execute(tool_call)
                event_bus.emit("MCP_CALL_SUCCESS", tool_call.dict())
                return result
            else:
                return ToolResult(error="MCP_REGISTRY_NOT_INITIALIZED")
        except Exception as e:
            event_bus.emit("MCP_CALL_FAILED", {"tool": tool_call.name, "error": str(e)})
            return ToolResult(error=str(e))

    def graceful_reprompt(self, model_name: str, task, attempted_tool: str, 
                          available_tools: List[str], attempt: int, call_model_func) -> ToolResult:
        if attempt > self.MAX_TOOL_RETRIES:
            event_bus.emit("MCP_HALLUCINATION_MAX_RETRIES", {
                "model": model_name,
                "attempted_tool": attempted_tool,
                "task_id": task.id if task else ""
            })
            return ToolResult(error=f"MCP_HALLUCINATION: {attempted_tool}")

        reprompt = f"""
        The tool '{attempted_tool}' does not exist.
        Available tools are:
        {", ".join(available_tools)}
        Please retry using only the tools listed above.
        """

        event_bus.emit("MCP_REPROMPT", {
            "attempt": attempt,
            "hallucinated_tool": attempted_tool,
            "model": model_name
        })

        # Recursive call via the provided function
        if call_model_func:
            new_output = call_model_func(reprompt)
            return self.execute_tool_call(new_output, available_tools, model_name, task, call_model_func)
        
        return ToolResult(error="REPROMPT_FAILED_NO_CALL_FUNC")

    def parse_tool_call(self, output: str) -> Optional[ToolCall]:
        # Balanced brace parser
        extracted = self._extract_json_balanced(str(output))
        if extracted:
            try:
                # Expecting format like {"name": "tool", "params": {}} or {"tool": "name", "args": {}}
                # Normalizing to ToolCall
                name = extracted.get("name") or extracted.get("tool") or extracted.get("function")
                params = extracted.get("params") or extracted.get("args") or extracted.get("parameters") or {}
                
                if name:
                    return ToolCall(name=name, params=params)
            except Exception:
                return None
        return None

    def _extract_json_balanced(self, text: str) -> Optional[dict]:
        start = text.find('{')
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if char == '\\' and in_string:
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return None
        return None
