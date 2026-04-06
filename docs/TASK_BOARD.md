# PvX Build Task Board
Last updated: 2026-04-06
Current phase: ALL PHASES COMPLETE — REVIEW DONE

## Active Tasks
| Task | Owner | Status | Notes |
|---|---|---|---|
| **Phase 0 Foundation** | Gemini | ✅ | Reviewed — clean |
| **Phase 1: Core Engine** | Gemini | ✅ | Reviewed — clean |
| **Phase 2: Context + Resilience** | Gemini | ✅ | Reviewed — compressor uses Qwen-3B ✓ |
| **Phase 3: MCP Layer** | Gemini | ✅ | Stubs correctly left for Claude |
| **Phase 4a: API + Core UI** | Gemini | ✅ | Reviewed — clean |
| **Phase 4b: Advanced UI** | Gemini | ✅ | Reviewed — clean |
| **Phase 5: Distribution + Polish** | Gemini | ✅ | Reviewed — clean |
| `models/claude.py` | Claude | ✅ | Built — subprocess, ANSI strip, rate limit, circuit breaker |
| `_classify_via_cli()` | Claude | ✅ | Built — balanced brace parser, JSON-only prompt, category validation |
| `mcp/server.py` | Claude | ✅ | Built — stdio transport, 5 tools, PvXMCPHandler stubs |
| `mcp/registry.py` | Claude | ✅ | Built — enabled-only tool registration, sync/async dispatch |
| `mcp/security.py` | Claude | ✅ | Built + adversarially reviewed — SQL, path, command validators |
| `mcp-config.json` | Claude | ✅ | Built — `uv run python -m pvx.mcp.server` entry point |
| Security tests (Hypothesis) | Claude | ✅ | 50 tests + 500 property-based examples |

Status codes: ⏳ Pending | 🔄 In Progress | 👁️ In Review | ✅ Done | ❌ Failed

## Review Results
| Check | Result |
|---|---|
| `.total_seconds()` — never `.seconds` | ✅ Pass — queue.py, vram.py correct |
| `Path.is_relative_to()` — never `startswith()` | ✅ Pass — filesystem.py, security.py correct |
| WAL mode on all SQLite connections | ✅ Pass — database.py pragma on every connect |
| `nvmlInit()` only in `__init__()` | ✅ Pass — vram.py correct |
| structlog only — never print() | ✅ Pass — zero print() calls in src/ |
| JSON balanced brace parser | ✅ Pass — classifier.py and proxy.py both use it |
| Compressor uses Qwen-3B (not Claude subprocess) | ✅ Pass — compressor.py uses ollama.chat |
| Tests passing | ✅ 77/77 |

## Completed This Phase
| Task | Owner | Tests Pass | Notes |
|---|---|---|---|
| Full codebase review | Claude | 77/77 | All architectural rules verified |
| mcp/server.py | Claude | ✅ | MCP SDK stdio server, 5 registered tools |
| mcp/registry.py | Claude | ✅ | Config-driven tool registration |
| mcp/security.py | Claude | ✅ | Adversarially reviewed, 50 security tests |
| mcp-config.json | Claude | ✅ | Claude Code MCP config entry point |

## Blueprint Issues Found
| Issue | Found By | Action |
|---|---|---|
| None | Claude | All phases matched spec |
| Known gap: leet-substitution SQL bypass (Dr0p) not caught | Claude | Logged — out of scope for v0.1, document in ISSUES.md |
