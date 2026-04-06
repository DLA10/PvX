import pynvml
import subprocess
from dataclasses import dataclass
from typing import List

@dataclass
class VRAMState:
    total_mb: int
    used_mb: int
    free_mb: int
    gpu_utilisation_pct: int
    running_pids: List[int]

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
                running_pids=[], # Harder to get via simple nvidia-smi
            )
        except Exception:
            return VRAMState(0, 0, 0, 0, [])

    def can_load(self, model: str) -> bool:
        state = self.poll()
        required = self.MODEL_VRAM_MB.get(model, 0)
        return state.free_mb >= required + self.SAFETY_BUFFER_MB
