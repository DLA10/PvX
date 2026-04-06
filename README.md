# PvX — Hardware-aware AI Orchestration Platform

PvX is an intelligent orchestration layer that sits beneath your chosen CLI agent — **Claude Code** — managing everything it can't see. It reserves premium cloud tokens for complex reasoning while delegating grunt work to local models, all while managing consumer GPU VRAM in real-time.

## Key Features

- **VRAM-aware scheduling** — Prevents GPU conflicts by monitoring VRAM and managing model swaps automatically.
- **Multi-step task chains** — Execute complex workflows with dependency resolution across multiple models.
- **Observable inter-model feed** — Real-time visibility into every delegation and model swap.
- **Rich Web UI** — Browser-based dashboard with hardware monitoring, task graphs, and direct chat.
- **MCP superpower for local LLMs** — Proxies and validates MCP calls for local models like Qwen and DeepSeek.

## Quickstart

```bash
# Install via uv
uv tool install pvx

# Run the dependency checker
pvx doctor

# Start the platform
pvx start
```

Then add PvX to your Claude Code config:
```json
{ "pvx": { "command": "uvx", "args": ["pvx"] } }
```

## Architecture

PvX acts as an MCP server that intercepts agentic tasks. It uses a **Keyword-first Task Classifier** to minimize cloud token usage, a **VRAM Manager** to handle consumer hardware constraints, and an **Event Bus** to provide full observability.

## Development

```bash
# Install dev dependencies
uv sync --all-extras --dev

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## License

Apache 2.0
