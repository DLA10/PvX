import pynvml
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional
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
    # Hardcoded defaults — used only when config is None (e.g. in tests)
    _DEFAULT_ZOMBIE_TIMEOUT_SECONDS: int = 60
    _DEFAULT_ZOMBIE_UTILISATION_THRESHOLD: int = 2
    _DEFAULT_SAFETY_BUFFER_MB: int = 512

    _DEFAULT_MODEL_VRAM_MB: dict[str, int] = {
        "qwen2.5-coder:14b": 8700,
        "deepseek-r1:7b":    4500,
        "qwen2.5-coder:3b":  2000,
    }

    def __init__(self, config=None) -> None:
        # Instance-level VRAM table — populated dynamically via update_model_vram()
        self.MODEL_VRAM_MB: dict[str, int] = dict(self._DEFAULT_MODEL_VRAM_MB)

        # Read tunables from config when provided; fall back to class defaults
        if config is not None:
            self.SAFETY_BUFFER_MB: int = config.vram.safety_buffer_mb
            self.ZOMBIE_TIMEOUT_SECONDS: int = config.vram.zombie_timeout_seconds
            self.ZOMBIE_UTILISATION_THRESHOLD: int = (
                config.vram.zombie_utilisation_threshold_pct
            )
        else:
            self.SAFETY_BUFFER_MB = self._DEFAULT_SAFETY_BUFFER_MB
            self.ZOMBIE_TIMEOUT_SECONDS = self._DEFAULT_ZOMBIE_TIMEOUT_SECONDS
            self.ZOMBIE_UTILISATION_THRESHOLD = self._DEFAULT_ZOMBIE_UTILISATION_THRESHOLD

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

    def update_model_vram(self, model_name: str, vram_mb: int) -> None:
        """Register or update the expected VRAM footprint for a model."""
        self.MODEL_VRAM_MB[model_name] = vram_mb
        logger.debug("vram_model_registered", model=model_name, vram_mb=vram_mb)

    def can_load(self, model: str) -> bool:
        # Deny unknown models — a 0-MB requirement would always pass, hiding bugs
        if model not in self.MODEL_VRAM_MB:
            logger.warning("vram_unknown_model", model=model)
            return False

        state = self.poll()
        required = self.MODEL_VRAM_MB[model]

        # Check PRESSURE state: free VRAM below safety buffer even without this model
        if state.free_mb < self.SAFETY_BUFFER_MB:
            if self.state not in (State.ZOMBIE, State.EXTERNAL):
                self.state = State.PRESSURE
            event_bus.emit("VRAM_PRESSURE", {
                "free_mb": state.free_mb,
                "safety_buffer_mb": self.SAFETY_BUFFER_MB,
            })
            logger.warning("vram_pressure",
                           free_mb=state.free_mb,
                           safety_buffer_mb=self.SAFETY_BUFFER_MB)
        return state.free_mb >= required + self.SAFETY_BUFFER_MB

    def get_loaded_model(self) -> Optional[str]:
        return self.loaded_model

    def get_actually_loaded_models(self) -> Dict[str, int]:
        """
        Query Ollama's /api/ps for ground truth on what is actually loaded.

        Returns {model_name: vram_used_mb}. Falls back to empty dict if Ollama
        is unavailable — callers must handle the empty case gracefully.
        """
        try:
            import httpx
            r = httpx.get("http://localhost:11434/api/ps", timeout=3.0)
            data = r.json()
            return {
                m["name"]: m.get("size_vram", 0) // 1024 // 1024
                for m in data.get("models", [])
            }
        except Exception as exc:
            logger.debug("ollama_ps_unavailable", error=str(exc))
            return {}

    def load_model(self, model: str):
        self.loaded_model = model
        self.state = State.LOADED

    def start_generation(self):
        self.state = State.RUNNING

    def end_generation(self):
        self.state = State.LOADED

    def unload_model(self, model_name: str) -> None:
        """
        Evict a model from VRAM via the Ollama keep_alive API.

        This keeps the Ollama server running — only the model weights are
        released. Use this for all normal model switching and idle eviction.
        DO NOT call kill_ollama_process() for this purpose.
        """
        try:
            import ollama as _ollama
            _ollama.generate(model=model_name, prompt="", keep_alive=0)
            logger.info("ollama_model_unloaded", model=model_name)
        except Exception as exc:
            logger.warning("ollama_unload_api_failed", model=model_name, error=str(exc))
        finally:
            if self.loaded_model == model_name:
                self.loaded_model = None
                self.state = State.IDLE

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

        # Try graceful unload first; only resort to pkill if API is unresponsive
        if task.model:
            self.unload_model(task.model)
        loaded = self.get_actually_loaded_models()
        if loaded:  # Ollama API is up, graceful unload worked
            logger.info("zombie_resolved_via_api", model=task.model)
        else:
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

    def kill_ollama_process(self) -> None:
        """
        Emergency kill for true zombie scenarios where the Ollama API is unresponsive.

        DO NOT call this for normal model unloading — use unload_model() instead.
        pkill terminates the entire Ollama daemon, disrupting all clients and
        requiring a manual or systemd restart before Ollama is usable again.
        """
        logger.warning("emergency_ollama_kill",
                        reason="api_unresponsive_or_confirmed_zombie")
        # Target 'ollama serve' specifically to avoid killing unrelated processes
        subprocess.run(["pkill", "-f", "ollama serve"], check=False)
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
