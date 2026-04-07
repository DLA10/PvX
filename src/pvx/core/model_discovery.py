"""
Model Discovery — finds installed Ollama models and their VRAM footprints.

PvX's only job here is to answer two questions:
  1. What models are installed?
  2. How much VRAM does each one need?

Claude Code and the user read the model names and decide what to use for what.
PvX does not label or categorise models.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

import ollama
import structlog

logger: structlog.BoundLogger = structlog.get_logger(__name__)


@dataclass
class DiscoveredModel:
    name: str
    size_gb: float
    vram_estimate_mb: int
    fits_in_vram: bool


@dataclass
class DiscoveryResult:
    models: List[DiscoveredModel]
    compression_model: Optional[str]   # smallest model — used for context compression only
    ollama_available: bool


def _estimate_vram_mb(name: str, size_gb: float) -> int:
    """
    Estimate VRAM from disk size with quantization-aware overhead.

    - Q4 variants: 1.15× overhead
    - Q8 variants: 1.20× overhead
    - Q5/Q6 variants: 1.25× overhead
    - FP16/unknown: 1.35× (conservative)
    - deepseek-r1/qwq style models: extra 1.25× for larger KV cache
    """
    n = name.lower()
    if "q4" in n:
        mult = 1.15
    elif "q8" in n:
        mult = 1.20
    elif "q5" in n or "q6" in n:
        mult = 1.25
    else:
        mult = 1.35

    if re.search(r"deepseek-r\d|qwq|r1|thinker", n):
        mult *= 1.25

    return int(size_gb * 1024 * mult)


def discover(vram_total_mb: int = 0) -> DiscoveryResult:
    """
    Query Ollama for installed models and estimate their VRAM requirements.

    Parameters
    ----------
    vram_total_mb:
        Total GPU VRAM in MB. Models that won't fit are marked fits_in_vram=False.
        Claude Code uses this to know what can actually load right now.
    """
    try:
        response = ollama.list()
        raw_models = response.models if hasattr(response, "models") else []
    except Exception as exc:
        logger.warning("model_discovery_ollama_unavailable", error=str(exc))
        return DiscoveryResult(models=[], compression_model=None, ollama_available=False)

    if not raw_models:
        logger.warning("model_discovery_no_models_found",
                       hint="Run `ollama pull <model>` to install a model")
        return DiscoveryResult(models=[], compression_model=None, ollama_available=True)

    discovered: List[DiscoveredModel] = []
    for m in raw_models:
        name = m.model if hasattr(m, "model") else str(m)
        size_bytes = m.size if hasattr(m, "size") else 0
        size_gb = size_bytes / (1024 ** 3)
        vram_est = _estimate_vram_mb(name, size_gb)
        fits = (vram_total_mb == 0) or (vram_est + 512 <= vram_total_mb)

        if not fits:
            logger.warning(
                "model_excluded_insufficient_vram",
                model=name,
                vram_estimate_mb=vram_est,
                vram_available_mb=vram_total_mb,
                shortfall_mb=vram_est + 512 - vram_total_mb,
            )

        discovered.append(DiscoveredModel(
            name=name,
            size_gb=round(size_gb, 1),
            vram_estimate_mb=vram_est,
            fits_in_vram=fits,
        ))

    usable = [m for m in discovered if m.fits_in_vram]
    # Pick smallest model for context compression — purely a size heuristic, not a capability judgment
    compression_model = min(usable, key=lambda m: m.size_gb).name if usable else None

    return DiscoveryResult(
        models=discovered,
        compression_model=compression_model,
        ollama_available=True,
    )


def log_discovery_summary(result: DiscoveryResult) -> None:
    if not result.ollama_available:
        logger.warning("pvx_model_discovery", status="ollama_unavailable")
        return
    if not result.models:
        logger.warning("pvx_model_discovery",
                       status="no_models_installed",
                       hint="Run: ollama pull <model>")
        return

    for m in result.models:
        logger.info(
            "pvx_discovered_model",
            model=m.name,
            size_gb=m.size_gb,
            vram_estimate_mb=m.vram_estimate_mb,
            fits_in_vram=m.fits_in_vram,
        )

    usable = [m.name for m in result.models if m.fits_in_vram]
    logger.info("pvx_discovery_complete",
                usable_models=usable,
                compression_model=result.compression_model)
