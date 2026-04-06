import ollama
import time
from typing import List, Optional
from pvx.models.base import BaseModelInterface, Message, GenerationResult

class OllamaModel(BaseModelInterface):
    def __init__(self, model_name: str, task_queue=None, current_task_id: Optional[str] = None):
        self.model_name = model_name
        self.task_queue = task_queue
        self.current_task_id = current_task_id

    def generate(self, prompt: str, history: List[Message],
                 tools: Optional[List[dict]] = None,
                 task_id: Optional[str] = None) -> GenerationResult:
        full_content = ""
        tokens_used = 0
        start_time = time.time()
        
        messages = [{"role": m.role, "content": m.content} for m in history]
        messages.append({"role": "user", "content": prompt})

        try:
            stream = ollama.chat(
                model=self.model_name,
                messages=messages,
                tools=tools,
                stream=True,
                options={"num_predict": 8192, "num_ctx": 16384, "temperature": 0.2}
            )

            for chunk in stream:
                token = chunk.message.content or ""
                full_content += token

                if task_id and self.task_queue:
                    self.task_queue.register_streaming_token(task_id, token)

                if chunk.done and hasattr(chunk, 'eval_count'):
                    tokens_used = chunk.eval_count

            duration_ms = int((time.time() - start_time) * 1000)
            
            return GenerationResult(
                content=full_content,
                tokens_used=tokens_used,
                model=self.model_name,
                duration_ms=duration_ms,
                tool_calls=None, # Parsed separately in MCP proxy as per blueprint
            )
        except Exception as e:
            return GenerationResult(
                content="",
                tokens_used=0,
                model=self.model_name,
                duration_ms=int((time.time() - start_time) * 1000),
                error=str(e)
            )

    def is_available(self) -> bool:
        try:
            # Check if ollama server is responsive
            ollama.list()
            return True
        except Exception:
            return False

    def name(self) -> str:
        return self.model_name
