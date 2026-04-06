from datetime import datetime
from typing import Optional, List, Dict
from pvx.core.tasks import Task
from pvx.core.vram import VRAMManager
from pvx.core.events import event_bus
from pvx.core.config import AppConfig

class TaskQueueEngine:
    def __init__(self, vram_manager: VRAMManager, config: AppConfig):
        self.current_batch_size: int = 0
        self.batch_start: datetime = datetime.now()
        self.affinity_reset: bool = False
        self._streaming_buffers: Dict[str, str] = {}  # task_id → partial output
        
        self.vram_manager = vram_manager
        self.config = config
        
        self.AFFINITY_BATCH_MAX_TASKS = config.queue.affinity_batch_max_tasks
        self.AFFINITY_BATCH_MAX_SECONDS = config.queue.affinity_batch_max_seconds
        self.STARVATION_TIMEOUT_SECONDS = config.queue.starvation_timeout_seconds
        self.PARTIAL_SAVE_MIN_TOKENS = config.queue.partial_save_min_tokens
        
        self.pending_tasks: List[Task] = []

    def reset_affinity_batch(self):
        self.current_batch_size = 0
        self.batch_start = datetime.now()
        self.affinity_reset = True

    def register_streaming_token(self, task_id: str, token: str):
        """Called by Ollama streaming callback on each token."""
        if task_id not in self._streaming_buffers:
            self._streaming_buffers[task_id] = ""
        self._streaming_buffers[task_id] += token

    def get_current_output(self, task: Task) -> str:
        """Returns partial output accumulated so far for a running task."""
        return self._streaming_buffers.get(task.id, "")

    def get_pending_with_deps_resolved(self) -> List[Task]:
        """Return pending tasks whose dependencies are all done.
        Tasks with no dependencies are immediately eligible.
        Tasks with dependencies are eligible only when every dep ID is 'done'.
        Tasks whose dependency failed are marked blocked (fail_cascade).
        """
        done_ids = {t.id for t in self.pending_tasks if t.status == "done"}
        failed_ids = {t.id for t in self.pending_tasks if t.status in ("failed", "timeout")}
        eligible = []
        for t in self.pending_tasks:
            if t.status != "pending":
                continue
            if not t.depends_on:
                eligible.append(t)
                continue
            # Fail cascade: if any dependency failed, block this task
            if any(dep in failed_ids for dep in t.depends_on):
                t.status = "blocked"
                event_bus.emit("DEPENDENCY_FAILED_CASCADE", {
                    "task_id": t.id,
                    "blocked_by": [dep for dep in t.depends_on if dep in failed_ids]
                })
                continue
            # All dependencies done → eligible
            if all(dep in done_ids for dep in t.depends_on):
                eligible.append(t)
        return eligible

    def get_next_task(self) -> Optional[Task]:
        pending = self.get_pending_with_deps_resolved()
        if not pending:
            return None
            
        now = datetime.now()

        # Step 0: Starvation guard
        starved = [
            t for t in pending
            if (now - t.created_at).total_seconds() > self.STARVATION_TIMEOUT_SECONDS
        ]
        if starved:
            winner = min(starved, key=lambda t: t.created_at)
            event_bus.emit("STARVATION_BYPASS", {
                "task_id": winner.id,
                "waited_seconds": (now - winner.created_at).total_seconds(),
                "bypassed_model": self.vram_manager.get_loaded_model()
            })
            return winner

        # Step 1: Critical tasks always go first
        critical = [t for t in pending if t.priority == 5]
        if critical:
            return max(critical, key=lambda t: t.priority)

        # Step 2: Check affinity batch limits
        batch_size_exceeded = self.current_batch_size >= self.AFFINITY_BATCH_MAX_TASKS
        batch_time_exceeded = (now - self.batch_start).total_seconds() >= self.AFFINITY_BATCH_MAX_SECONDS
        
        if batch_size_exceeded or batch_time_exceeded:
            self.reset_affinity_batch()

        # Step 3: Model affinity
        current_model = self.vram_manager.get_loaded_model()
        if current_model and not self.affinity_reset:
            affinity_tasks = [t for t in pending if t.model == current_model]
            if affinity_tasks:
                self.current_batch_size += 1
                return max(affinity_tasks, key=lambda t: (t.priority, -t.created_at.timestamp()))

        # Step 4: No affinity match — pick highest priority available
        # Reset affinity flag so next task selection can use affinity again
        self.affinity_reset = False
        return max(pending, key=lambda t: (t.priority, -t.created_at.timestamp()))

    def should_preempt(self, incoming: Task, running: Task) -> bool:
        if incoming.priority == 5 and running.priority <= 3:
            return True
        if incoming.priority == 4 and running.priority == 1:
            return True
        return False

    def handle_preemption(self, incoming: Task, running: Task):
        tokens_generated = running.tokens_generated_so_far
        
        if tokens_generated < self.PARTIAL_SAVE_MIN_TOKENS:
            running.partial_output = None
            running.status = "preempted"
            running.preempted_at = datetime.now()
        else:
            running.partial_output = self.get_current_output(running)
            running.status = "preempted"
            running.preempted_at = datetime.now()
            running.resume_prompt = (
                "[PARTIAL OUTPUT FROM PREVIOUS ATTEMPT — CONTINUE FROM HERE]\n"
                f"{running.partial_output}\n"
                "[END PARTIAL — CONTINUE THE IMPLEMENTATION]"
            )
            
        event_bus.emit("TASK_PREEMPTED", {
            "task_id": running.id,
            "tokens_generated": tokens_generated,
            "partial_saved": running.partial_output is not None,
            "preempted_by": incoming.id
        })
