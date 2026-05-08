# PvX — Hardware-Aware AI Orchestration
# STILL UNDER CONSTRUCTION

PvX is an orchestration layer that routes agentic tasks between your local
Ollama models and Claude Code based on task complexity and available VRAM.
Simple tasks run locally for free. Complex tasks escalate to Claude only when
needed. It ships as an MCP server so Claude Code can use it as a tool.

## What it does

- **Auto-routes tasks** — classifies each prompt (keyword matching + optional Claude escalation) and sends it to the right model
- **VRAM-aware scheduling** — monitors GPU memory, switches models cleanly, evicts idle models after 2 minutes
- **Priority queue** — priority 5 (critical) preempts running tasks; priority 1 (background) waits
- **Dependency chains** — task B can depend on task A; output of A becomes context for B
- **Context compression** — summarises long histories with a small local model before they overflow
- **Live streaming** — SSE endpoint streams tokens in real time while a task is running
- **MCP server** — 5 tools Claude Code can invoke: `submit_task`, `get_task_status`, `list_tasks`, `get_vram_status`, `cancel_task`
- **REST API** — full HTTP API on `localhost:8000` for scripting and CI pipelines

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Ollama](https://ollama.com) — local LLM runtime (`curl -fsSL https://ollama.com/install.sh | sh`)
- At least one Ollama model (`ollama pull qwen2.5-coder:3b`)
- NVIDIA GPU recommended (CPU fallback works but is slow)
- Claude Code optional (used for complex task classification and high-complexity routing)

## Quickstart

```bash
# 1. Install
uv tool install pvx

# 2. Create config in your working directory
mkdir my-project && cd my-project
pvx init

# 3. Edit config to match your installed models
#    (pvx doctor will tell you what's wrong)
pvx doctor

# 4. Start the platform
pvx start
```

The platform starts two servers:
- REST API on `http://localhost:8000`
- MCP server on stdio (launched separately by Claude Code)

## Connect to Claude Code

Add this to your Claude Code MCP settings (`~/.config/claude/mcp.json` or via Settings → MCP):

```json
{
  "mcpServers": {
    "pvx": {
      "command": "pvx-mcp"
    }
  }
}
```

Claude Code will now see 5 PvX tools. When it calls `submit_task`, PvX routes
the work to a local model if one fits in VRAM, or falls back to Claude.

## Submit tasks directly

```bash
# Submit a task
curl -X POST http://localhost:8000/api/tasks/ \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a binary search in Python", "priority": 3}'

# Returns: {"task_id": "task_abc123", "status": "pending", "model": "qwen2.5-coder:3b-instruct-q8_0", "category": "boilerplate"}

# Poll for result
curl http://localhost:8000/api/tasks/task_abc123

# Stream tokens live
curl -N http://localhost:8000/api/tasks/task_abc123/stream

# Check VRAM
curl http://localhost:8000/api/vram/
```

## Priority levels

| Priority | Meaning | Behaviour |
|---|---|---|
| 5 | Critical | Preempts tasks at priority ≤ 3 before they start |
| 4 | High | Preempts priority 1 |
| 3 | Normal (default) | Standard queue order |
| 2 | Low | Waits behind normal tasks |
| 1 | Background | Never preempts; runs when queue is otherwise empty |

## Task categories

PvX classifies prompts automatically. You can override with `"category"` in the request:

| Category | Routed to |
|---|---|
| `large_context`, `codebase_analysis`, `architecture`, `final_review` | Claude (always) |
| `complex_code`, `ml_pipeline`, `oop_design`, `code_review`, `algorithm_design`, `system_design` | Heavy local model |
| `boilerplate`, `simple_refactor`, `formatting`, `docstrings` | Light local model |
| `math_proof`, `chain_of_thought`, `debugging_logic` | Reasoning model |

## Development

```bash
git clone https://github.com/DLA10/PvX
cd PvX
uv sync                    # installs all dependencies including dev tools
uv run pytest              # run tests (77 tests)
uv run ruff check .        # lint
uv run ruff format .       # format
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
