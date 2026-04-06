import pynvml
import subprocess
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from enum import Enum
import structlog
from pvx.core.events import event_bus

logger = structlog.get_logger()

@dataclass
class VRAMState:
    total_mb: int
    used_mb: int
    free_mb: int
    gpu_utilisation_pct: int
    running_pids: List[int]

class State(Enum):
    IDLE      = "idle"
    LOADED    = "loaded"
    RUNNING   = "running"
    EXTERNAL  = "external"
    PRESSURE  = "pressure"
    ZOMBIE    = "zombie"

class VRAMManager:
    ZOMBIE_TIMEOUT_SECONDS = 60
    ZOMBIE_UTILISATION_THRESHOLD = 2
    SAFETY_BUFFER_MB = 512

    MODEL_VRAM_MB = {
        "qwen2.5-coder:14b":  8700,
        "deepseek-r1:7b":     4500,
        "qwen2.5-coder:3b":   2000,
    }

    def __init__(self):
        self.state = State.IDLE
        self.loaded_model: Optional[str] = None
        try:
            pynvml.nvmlInit()
            self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._nvml_available = True
        except pynvml.NVMLError:
            self._nvml_available = False

    def shutdown(self):
        if self._nvml_available:
            pynvml.nvmlShutdown()

    def poll(self) -> VRAMState:
        if self._nvml_available:
            return self._poll_pynvml()
        return self._poll_nvidia_smi()

    def _poll_pynvml(self) -> VRAMState:
        mem = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
        procs = pynvml.nvmlDeviceGetComputeRunningProcesses(self._nvml_handle)

        return VRAMState(
            total_mb=mem.total // 1024 // 1024,
            used_mb=mem.used // 1024 // 1024,
            free_mb=mem.free // 1024 // 1024,
            gpu_utilisation_pct=util.gpu,
            running_pids=[p.pid for p in procs],
        )

    def _poll_nvidia_smi(self) -> VRAMState:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True
            )
            total, used, free, util = map(int, result.stdout.strip().split(', '))
            return VRAMState(
                total_mb=total,
                used_mb=used,
                free_mb=free,
                gpu_utilisation_pct=util,
                running_pids=[],
            )
        except Exception:
            return VRAMState(0, 0, 0, 0, [])

    def can_load(self, model: str) -> bool:
        state = self.poll()
        required = self.MODEL_VRAM_MB.get(model, 0)
        return state.free_mb >= required + self.SAFETY_BUFFER_MB

    def get_loaded_model(self) -> Optional[str]:
        return self.loaded_model

    def load_model(self, model: str):
        self.loaded_model = model
        self.state = State.LOADED

    def start_generation(self):
        self.state = State.RUNNING

    def end_generation(self):
        self.state = State.LOADED

    def detect_zombie(self, running_task, state: VRAMState) -> bool:
        if running_task.status != "running":
            return False
        if state.gpu_utilisation_pct > self.ZOMBIE_UTILISATION_THRESHOLD:
            return False
        if not running_task.started_at:
            return False
        elapsed = (datetime.now() - running_task.started_at).total_seconds()
        return elapsed > self.ZOMBIE_TIMEOUT_SECONDS

    def handle_zombie(self, task) -> None:
        elapsed = (datetime.now() - task.started_at).total_seconds() if task.started_at else 0
        logger.warning("zombie_detected",
                       task_id=task.id,
                       model=task.model,
                       running_since_seconds=elapsed,
                       action="kill_and_retry",
                       retry_count=task.retry_count)
        event_bus.emit("ZOMBIE_DETECTED", {
            "task_id": task.id,
            "model": task.model,
            "running_since_seconds": elapsed,
            "retry_count": task.retry_count,
        }, task_id=task.id)
        self.kill_ollama_process()
        task.status = "timeout"
        task.error = "ZOMBIE_DETECTED: GPU idle > 60s while task RUNNING"
        self.state = State.ZOMBIE

        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = "pending"
            task.started_at = None
        else:
            task.status = "failed"

    def kill_ollama_process(self):
        subprocess.run(["pkill", "-f", "ollama"], check=False)
        self.state = State.IDLE
        self.loaded_model = None

    def detect_external(self, state: VRAMState) -> bool:
        ollama_pids = self.get_ollama_pids()
        external_pids = [p for p in state.running_pids if p not in ollama_pids]
        if external_pids:
            self.state = State.EXTERNAL
        return len(external_pids) > 0

    def get_ollama_pids(self) -> List[int]:
        try:
            result = subprocess.run(["pgrep", "-f", "ollama"], capture_output=True, text=True)
            if result.returncode == 0:
                return [int(pid) for pid in result.stdout.strip().split('\n') if pid]
        except Exception:
            pass
        return []
