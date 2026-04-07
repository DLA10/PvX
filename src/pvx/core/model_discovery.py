"""
Model Discovery — auto-detects installed Ollama models and their VRAM footprints.

Queries `ollama list` at startup, classifies each model by capability and size,
and estimates VRAM requirements. The results are handed to Claude Code via the
list_available_models() MCP tool so Claude Code and the user can decide routing
collaboratively. PvX does not make routing decisions.
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
    capability: str   # "coder" | "reasoning" | "general"
    tier: str         # "heavy" | "light"
    fits_in_vram: bool
    vram_estimate_mb: int


@dataclass
class DiscoveryResult:
    models: List[DiscoveredModel]
    compression_model: Optional[str]
    ollama_available: bool


def _classify_model(name: str, size_gb: float) -> tuple[str, str]:
    """Return (capability, tier) for a model based on its name and size."""
    n = name.lower()

    is_coder = bool(re.search(r"coder|code|codellama|starcoder|wizard.*code|deepseek-coder", n))
    is_reasoning = bool(re.search(r"deepseek-r\d|qwq|o1|thinker|reasoner|r1", n))

    if is_reasoning:
        capability = "reasoning"
    elif is_coder:
        capability = "coder"
    else:
        capability = "general"

    tier = "heavy" if size_gb >= 5.0 else "light"
    return capability, tier


def _estimate_vram_mb(name: str, size_gb: float) -> int:
    """
    Estimate VRAM from disk size with quantization-aware overhead.

    - Q4 variants: 1.15× (minimal KV cache at default context)
    - Q8 variants: 1.20× (larger weights, more cache pressure)
    - FP16/unknown: 1.35× (conservative)
    - Reasoning models: +1.25× extra KV cache headroom
    """
    n = name.lower()
    if "q4" in n:
        quant_mult = 1.15
    elif "q8" in n:
        quant_mult = 1.20
    elif "q5" in n or "q6" in n:
        quant_mult = 1.25
    else:
        quant_mult = 1.35

    if re.search(r"deepseek-r\d|qwq|r1|thinker", n):
        quant_mult *= 1.25

    return int(size_gb * 1024 * quant_mult)


def discover(vram_total_mb: int = 0) -> DiscoveryResult:
    """
    Query Ollama, classify every installed model by capability and VRAM.

    Parameters
    ----------
    vram_total_mb:
        Total GPU VRAM in MB. Models estimated to exceed this are marked
        fits_in_vram=False. Claude Code uses this to know what can load right now.
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
        capability, tier = _classify_model(name, size_gb)
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
            capability=capability,
            tier=tier,
            fits_in_vram=fits,
            vram_estimate_mb=vram_est,
        ))

    usable = [m for m in discovered if m.fits_in_vram]
    compression_model = _pick_compression_model(usable)

    return DiscoveryResult(
        models=discovered,
        compression_model=compression_model,
        ollama_available=True,
    )


def _pick_compression_model(usable: List[DiscoveredModel]) -> Optional[str]:
    """Pick the smallest coder/general model for context compression."""
    candidates = [m for m in usable if m.capability in ("coder", "general")]
    if not candidates:
        candidates = usable
    return min(candidates, key=lambda m: m.size_gb).name if candidates else None


def log_discovery_summary(result: DiscoveryResult) -> None:
    """Log what was found — Claude Code calls list_available_models() for the full picture."""
    if not result.ollama_available:
        logger.warning("pvx_model_discovery", status="ollama_unavailable")
        return

    if not result.models:
        logger.warning("pvx_model_discovery",
                       status="no_models_installed",
                       hint="Run: ollama pull qwen2.5-coder:3b")
        return

    for m in result.models:
        status = "usable" if m.fits_in_vram else "too_large_for_vram"
        logger.info(
            "pvx_discovered_model",
            model=m.name,
            size_gb=m.size_gb,
            capability=m.capability,
            tier=m.tier,
            vram_estimate_mb=m.vram_estimate_mb,
            status=status,
        )

    usable = [m.name for m in result.models if m.fits_in_vram]
    logger.info("pvx_discovery_complete",
                usable_models=usable,
                compression_model=result.compression_model,
                note="Claude Code calls list_available_models() to see this data and decide routing")
