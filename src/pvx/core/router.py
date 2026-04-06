from pvx.core.tasks import Task
from pvx.core.vram import VRAMManager
from pvx.core.config import AppConfig
import structlog

logger = structlog.get_logger()

class TaskRouter:
    """
    Routing is configuration-driven.
    """
    def __init__(self, config: AppConfig, vram_manager: VRAMManager):
        self.config = config
        self.vram_manager = vram_manager

    def route(self, task: Task) -> str:
        # Get primary model based on config rules
        primary = self.config.routing.rules.get(task.category, "claude")

        # Check VRAM availability for local models only
        if self._is_local_model(primary):
            if not self.vram_manager.can_load(primary):
                fallbacks = self.config.routing.fallback_chain.get(primary, [])
                for fallback in fallbacks:
                    actual = "claude" if fallback == "claude" else fallback
                    if fallback == "claude" or self.vram_manager.can_load(fallback):
                        logger.info("task_routed", 
                            primary_model=primary, 
                            actual_model=actual, 
                            reason="VRAM_UNAVAILABLE"
                        )
                        return actual

        return primary

    def _is_local_model(self, model_name: str) -> bool:
        return model_name != "claude"
