"""
Model Discovery — auto-detects installed Ollama models and builds routing rules.

Instead of hardcoding model names in config, PvX queries `ollama list` at
startup, classifies each model by its name and size, assigns it to task
categories, and logs a clear summary so the user knows exactly what will run
what.

Classification is name-pattern based — the industry conventions are consistent
enough that this works reliably:
  *coder* / *code*        → code generation tasks
  *deepseek-r1* / *qwq*  → reasoning / chain-of-thought tasks
  *deepseek-coder*        → code (deepseek-coder is a coder model)
  *gemma* / *llama* /
  *mistral* / *phi*       → general purpose
  size tier: ≤4GB → lightweight tasks, >4GB → heavier tasks
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import ollama
import structlog

logger: structlog.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Task category groups — maps a tier+type to the list of routing categories
# ---------------------------------------------------------------------------

# Heavy coder model (≥5GB) → complex code tasks
HEAVY_CODER_CATEGORIES = [
    "complex_code", "ml_pipeline", "oop_design", "code_review",
    "algorithm_design", "system_design",
]

# Light coder model (<5GB) → simple code tasks
LIGHT_CODER_CATEGORIES = [
    "boilerplate", "simple_refactor", "formatting", "docstrings",
]

# Reasoning model → logic / math tasks
REASONING_CATEGORIES = [
    "math_proof", "chain_of_thought", "debugging_logic",
]

# General model → fills categories not covered by specialists.
# Only applied when no coder/reasoning model is assigned to that category.
GENERAL_CATEGORIES = [
    "boilerplate", "simple_refactor", "formatting", "docstrings",
    "complex_code", "algorithm_design",
]

# Always Claude regardless of local models
CLAUDE_ONLY_CATEGORIES = [
    "large_context", "codebase_analysis", "architecture", "final_review",
]


@dataclass
class DiscoveredModel:
    name: str
    size_gb: float
    capability: str          # "coder" | "reasoning" | "general"
    tier: str                # "heavy" | "light"
    fits_in_vram: bool
    vram_estimate_mb: int
    assigned_categories: List[str] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    models: List[DiscoveredModel]
    routing_rules: Dict[str, str]   # category → model_name
    fallback_chain: Dict[str, List[str]]
    compression_model: Optional[str]
    ollama_available: bool


def _classify_model(name: str, size_gb: float) -> tuple[str, str]:
    """Return (capability, tier) for a model."""
    n = name.lower()

    # Capability
    is_coder = bool(re.search(r"coder|code|codellama|starcoder|wizard.*code|deepseek-coder", n))
    is_reasoning = bool(re.search(r"deepseek-r\d|qwq|o1|thinker|reasoner|r1", n))

    if is_reasoning:
        capability = "reasoning"
    elif is_coder:
        capability = "coder"
    else:
        capability = "general"

    # Tier by disk size (proxy for VRAM requirements)
    tier = "heavy" if size_gb >= 5.0 else "light"

    return capability, tier


def _estimate_vram_mb(name: str, size_gb: float) -> int:
    """
    Estimate VRAM from disk size with quantization-aware overhead.

    Quantized models need disk_size × overhead in VRAM:
    - Q4 variants: 1.15× (minimal KV cache at default context)
    - Q8 variants: 1.20× (larger weights, more cache pressure)
    - FP16/unknown: 1.35× (conservative — may need full precision)

    Reasoning models (deepseek-r1, qwq) need extra KV cache headroom: +1.25×
    """
    n = name.lower()

    # Quantization multiplier from name
    if "q4" in n:
        quant_mult = 1.15
    elif "q8" in n:
        quant_mult = 1.20
    elif "q5" in n or "q6" in n:
        quant_mult = 1.25
    else:
        quant_mult = 1.35  # FP16 or unknown — be conservative

    # Reasoning models need larger KV cache
    if re.search(r"deepseek-r\d|qwq|r1|thinker", n):
        quant_mult *= 1.25

    return int(size_gb * 1024 * quant_mult)


def discover(vram_total_mb: int = 0) -> DiscoveryResult:
    """
    Query Ollama, classify every installed model, build routing rules.

    Parameters
    ----------
    vram_total_mb:
        Total GPU VRAM in MB. Models estimated to exceed this are marked
        fits_in_vram=False and excluded from routing (Claude is used instead).
    """
    try:
        response = ollama.list()
        raw_models = response.models if hasattr(response, "models") else []
    except Exception as exc:
        logger.warning("model_discovery_ollama_unavailable", error=str(exc))
        return DiscoveryResult(
            models=[], routing_rules=_claude_only_rules(),
            fallback_chain={"claude": []},
            compression_model=None,
            ollama_available=False,
        )

    if not raw_models:
        logger.warning("model_discovery_no_models_found",
                       hint="Run `ollama pull <model>` to install a model")
        return DiscoveryResult(
            models=[], routing_rules=_claude_only_rules(),
            fallback_chain={"claude": []},
            compression_model=None,
            ollama_available=True,
        )

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

    # Filter to only models that fit in VRAM
    usable = [m for m in discovered if m.fits_in_vram]

    if not usable:
        logger.warning("model_discovery_no_models_fit_vram",
                       total_vram_mb=vram_total_mb,
                       models_found=[m.name for m in discovered])
        return DiscoveryResult(
            models=discovered, routing_rules=_claude_only_rules(),
            fallback_chain={"claude": []},
            compression_model=None,
            ollama_available=True,
        )

    routing_rules, fallback_chain = _build_routing(usable)
    compression_model = _pick_compression_model(usable)

    # Attach assigned categories back to each model for the summary log
    for model in usable:
        model.assigned_categories = [
            cat for cat, name in routing_rules.items() if name == model.name
        ]

    return DiscoveryResult(
        models=discovered,
        routing_rules=routing_rules,
        fallback_chain=fallback_chain,
        compression_model=compression_model,
        ollama_available=True,
    )


def _build_routing(usable: List[DiscoveredModel]) -> tuple[Dict[str, str], Dict[str, List[str]]]:
    """Assign models to categories. Returns (routing_rules, fallback_chain)."""
    rules: Dict[str, str] = {}

    # Separate by capability and tier
    heavy_coders  = [m for m in usable if m.capability == "coder"     and m.tier == "heavy"]
    light_coders  = [m for m in usable if m.capability == "coder"     and m.tier == "light"]
    reasoners     = [m for m in usable if m.capability == "reasoning"]
    generals      = [m for m in usable if m.capability == "general"]

    # Pick best representative per role (largest that fits)
    heavy_coder = max(heavy_coders, key=lambda m: m.size_gb) if heavy_coders else None
    light_coder = max(light_coders, key=lambda m: m.size_gb) if light_coders else None
    reasoner    = max(reasoners,    key=lambda m: m.size_gb) if reasoners    else None
    general     = max(generals,     key=lambda m: m.size_gb) if generals     else None

    # If no light coder, use heavy coder for light tasks too (and vice versa)
    effective_heavy  = heavy_coder or light_coder or reasoner or general
    effective_light  = light_coder or heavy_coder or general
    effective_reason = reasoner or heavy_coder or general
    effective_general = general or light_coder or heavy_coder or reasoner

    # Assign specialist categories first
    for cat in HEAVY_CODER_CATEGORIES:
        rules[cat] = effective_heavy.name if effective_heavy else "claude"

    for cat in LIGHT_CODER_CATEGORIES:
        rules[cat] = effective_light.name if effective_light else "claude"

    for cat in REASONING_CATEGORIES:
        rules[cat] = effective_reason.name if effective_reason else "claude"

    # General model fills any category not already assigned by a specialist.
    # This ensures models like gemma4 (general) get routing assignments when
    # no coder/reasoner model covers those categories.
    for cat in GENERAL_CATEGORIES:
        if cat not in rules:
            rules[cat] = effective_general.name if effective_general else "claude"

    for cat in CLAUDE_ONLY_CATEGORIES:
        rules[cat] = "claude"

    # Build fallback chains
    fallback: Dict[str, List[str]] = {"claude": []}
    for m in usable:
        # Each model falls back to claude
        fallback[m.name] = ["claude"]

    return rules, fallback


def _pick_compression_model(usable: List[DiscoveredModel]) -> Optional[str]:
    """Pick the smallest coder/general model for context compression."""
    candidates = [m for m in usable if m.capability in ("coder", "general")]
    if not candidates:
        candidates = usable
    return min(candidates, key=lambda m: m.size_gb).name if candidates else None


def _claude_only_rules() -> Dict[str, str]:
    all_cats = (HEAVY_CODER_CATEGORIES + LIGHT_CODER_CATEGORIES +
                REASONING_CATEGORIES + GENERAL_CATEGORIES + CLAUDE_ONLY_CATEGORIES)
    return {cat: "claude" for cat in dict.fromkeys(all_cats)}


def log_discovery_summary(result: DiscoveryResult) -> None:
    """Print a structured human-readable summary of what was found."""
    if not result.ollama_available:
        logger.warning("pvx_model_discovery",
                       status="ollama_unavailable",
                       routing="claude_only")
        return

    if not result.models:
        logger.warning("pvx_model_discovery",
                       status="no_models_installed",
                       routing="claude_only",
                       hint="Run: ollama pull qwen2.5-coder:3b")
        return

    for m in result.models:
        status = "✅ usable" if m.fits_in_vram else "⚠️  too large for VRAM"
        logger.info(
            "pvx_discovered_model",
            model=m.name,
            size_gb=m.size_gb,
            capability=m.capability,
            tier=m.tier,
            vram_estimate_mb=m.vram_estimate_mb,
            status=status,
            assigned_to=m.assigned_categories if m.fits_in_vram else [],
        )

    # Summary by role
    usable_names = [m.name for m in result.models if m.fits_in_vram]
    if usable_names:
        logger.info("pvx_routing_plan",
                    usable_models=usable_names,
                    compression_model=result.compression_model,
                    claude_handles=CLAUDE_ONLY_CATEGORIES)
    else:
        logger.warning("pvx_routing_plan",
                       status="no_local_models_fit",
                       routing="all_tasks_go_to_claude")
