# Contributing to PvX

We welcome contributions! PvX is built with a focus on hardware awareness and token efficiency.

## Getting Started

1. Fork the repository.
2. Clone your fork.
3. Install dependencies: `uv sync --all-extras --dev`.
4. Create a new branch for your feature or bugfix.

## Coding Standards

- **Ruff**: We use Ruff for linting and formatting. Run `uv run ruff check .` before submitting.
- **Pytest**: Ensure all tests pass with `uv run pytest`.
- **Architectural Rules**: See `GEMINI.md` for strict architectural mandates (e.g., WAL mode for SQLite, `.total_seconds()` for timedeltas).

## Building the UI

The UI is built with React and Tailwind CSS.
```bash
cd ui
npm install
npm start
```

## Security

Security is critical. All MCP tool calls must pass through the validation layer. Adversarial review is required for any changes to the security modules.
