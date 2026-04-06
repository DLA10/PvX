import ollama
from typing import List
from pvx.models.base import Message
from pvx.core.tokens import token_counter
from pvx.core.vram import VRAMManager
from pvx.core.events import event_bus
from pvx.core.config import AppConfig

class ContextCompressor:
    """
    Summarizes history locally using Qwen-3B when context limits are reached.
    """

    MIN_COMPRESS_TOKENS = 8_000

    SUMMARY_PROMPT = """
    You are summarising a conversation history for context compression.
    Produce a dense, factual summary preserving:
    - All decisions made
    - All code written (reference filenames, not full code)
    - All errors encountered and their resolutions
    - Current state of the task
    - What remains to be done

    Be concise. Omit pleasantries. Preserve technical detail.
    Target: under 2000 tokens.

    History:
    {history}
    """

    def __init__(self, vram_manager: VRAMManager, config: AppConfig):
        self.vram_manager = vram_manager
        self.config = config
        self.compression_model = config.context.compression_model
        self.threshold_pct = config.context.compression_threshold_pct / 100.0

        # Build context limits from config — not hardcoded
        self._context_limits: dict = {"claude": 200_000}
        for m in config.models.local:
            self._context_limits[m.name] = m.context_tokens

    def maybe_compress(self, model: str, history: List[Message]) -> List[Message]:
        limit = self._context_limits.get(model, 32_000)
        threshold = int(limit * self.threshold_pct)
        history_tokens = token_counter.count_messages(history)

        # Don't compress unless we're both above percentage threshold AND minimum floor
        if history_tokens <= threshold or history_tokens < self.MIN_COMPRESS_TOKENS:
            return history

        # Local compression - Qwen-3B by default (free)
        if not self.vram_manager.can_load(self.compression_model):
            event_bus.emit("CONTEXT_COMPRESSION_SKIPPED", {
                "model": model,
                "history_tokens": history_tokens,
                "reason": "VRAM_INSUFFICIENT_FOR_COMPRESSOR"
            })
            return history

        formatted_history = "\n".join([f"{m.role}: {m.content}" for m in history])
        
        try:
            response = ollama.chat(
                model=self.compression_model,
                messages=[{"role": "user", "content": self.SUMMARY_PROMPT.format(history=formatted_history)}],
                stream=False
            )
            summary = response.message.content

            compressed = [
                Message(role="system", content=f"[CONTEXT SUMMARY]\n{summary}"),
                *history[-self.config.context.compression_keep_last_messages:]
            ]

            event_bus.emit("CONTEXT_COMPRESSED", {
                "model": model,
                "original_tokens": history_tokens,
                "compressed_tokens": token_counter.count_messages(compressed),
                "reduction_pct": round((1 - len(compressed)/len(history)) * 100, 1) if len(history) > 0 else 0
            })

            return compressed
            
        except Exception as e:
            event_bus.emit("CONTEXT_COMPRESSION_FAILED", {"error": str(e)})
            return history
