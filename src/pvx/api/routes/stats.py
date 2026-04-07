from fastapi import APIRouter
import structlog

router = APIRouter(prefix="/api/stats", tags=["stats"])
logger = structlog.get_logger()

# GPT-4o blended pricing (input+output average): $0.005 / 1K tokens → $0.000005/token
_GPT4O_USD_PER_TOKEN = 0.000005


@router.get("/session")
async def session_stats() -> dict:
    from pvx.main import app_state

    if app_state is None:
        return {
            "tokens_per_model": {},
            "tasks_per_model": {},
            "total_tokens": 0,
            "gpt4o_equivalent_usd": 0.0,
            "savings_pct": 100.0,
            "compressions": 0,
            "affinity_batch_status": "IDLE",
        }

    # Token counts from completed tasks
    tokens_per_model: dict = dict(app_state.session_token_counts)

    # Task counts per model from in-memory task list
    tasks_per_model: dict = {}
    for t in app_state.queue.pending_tasks:
        if t.model:
            tasks_per_model[t.model] = tasks_per_model.get(t.model, 0) + 1

    total_tokens = sum(tokens_per_model.values())
    gpt4o_usd = round(total_tokens * _GPT4O_USD_PER_TOKEN, 4)

    # Affinity batch status text
    q = app_state.queue
    current_model = app_state.current_ollama_model
    if current_model:
        elapsed = (
            (__import__("datetime").datetime.now() - q.batch_start).total_seconds()
        )
        status = (
            f"Batching {q.current_batch_size} {current_model} tasks "
            f"({int(elapsed)}s elapsed)"
        )
    else:
        pending_count = sum(
            1 for t in q.pending_tasks if t.status == "pending"
        )
        status = f"IDLE — {pending_count} task(s) queued" if pending_count else "IDLE"

    return {
        "tokens_per_model": tokens_per_model,
        "tasks_per_model": tasks_per_model,
        "total_tokens": total_tokens,
        "gpt4o_equivalent_usd": gpt4o_usd,
        "savings_pct": 100.0 if total_tokens == 0 else round(
            (1 - 0 / max(gpt4o_usd, 0.0001)) * 100, 1
        ),
        "compressions": app_state.session_compressions,
        "affinity_batch_status": status,
    }
