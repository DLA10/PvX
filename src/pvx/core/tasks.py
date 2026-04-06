from dataclasses import dataclass
from datetime import datetime
from typing import List, Literal, Optional

@dataclass
class Task:
    id: str
    model: str
    prompt: str
    category: str
    status: Literal["pending", "running", "done", "failed", "blocked",
                    "timeout", "preempted", "zombie"]
    priority: int
    depends_on: List[str]
    requires_vram: bool
    requires_system_idle: bool
    retry_count: int
    max_retries: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    output: Optional[str] = None
    tokens_generated_so_far: int = 0
    partial_output: Optional[str] = None
    resume_prompt: Optional[str] = None
    resumed_from_partial: bool = False
    error: Optional[str] = None
    preempted_at: Optional[datetime] = None
    context_was_compressed: bool = False
