from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict
from pydantic import BaseModel

class Message(BaseModel):
    role: str
    content: str

class GenerationResult(BaseModel):
    content: str
    tokens_used: int
    model: str
    duration_ms: int
    tool_calls: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None

class BaseModelInterface(ABC):
    @abstractmethod
    def generate(self, prompt: str, history: List[Message],
                 tools: Optional[List[dict]] = None,
                 task_id: Optional[str] = None) -> GenerationResult:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def name(self) -> str:
        pass
