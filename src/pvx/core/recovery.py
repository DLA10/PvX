import asyncio
from typing import Callable, Any
from pvx.core.circuit_breaker import CircuitBreaker
from pvx.core.events import event_bus
import structlog

logger = structlog.get_logger()

class RetryHandler:
    """
    Handles retries with exponential backoff and circuit breaker logic.
    """
    def __init__(self, circuit_breaker: CircuitBreaker, 
                 max_retries: int = 3, 
                 base_delay: float = 1.0, 
                 max_delay: float = 30.0):
        self.circuit_breaker = circuit_breaker
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        retries = 0
        while retries <= self.max_retries:
            if not self.circuit_breaker.is_allowed():
                event_bus.emit("CIRCUIT_BREAKER_OPEN", {"func": func.__name__})
                await asyncio.sleep(self.base_delay)
                retries += 1
                continue

            try:
                result = await func(*args, **kwargs)
                self.circuit_breaker.record_success()
                return result
            except Exception as e:
                retries += 1
                self.circuit_breaker.record_failure()
                
                if retries > self.max_retries:
                    logger.error("retry_failed_max_reached", error=str(e), retries=retries)
                    raise e
                
                delay = min(self.base_delay * (2 ** (retries - 1)), self.max_delay)
                logger.warning("retrying_with_backoff", error=str(e), delay=delay, attempt=retries)
                await asyncio.sleep(delay)

def detect_rate_limit(stderr: str) -> bool:
    """Detect rate limits via stderr pattern matching."""
    rate_limit_patterns = [
        "rate_limit_error",
        "Too many requests",
        "overloaded_error",
        "529",
    ]
    return any(pat in stderr for pat in rate_limit_patterns)
