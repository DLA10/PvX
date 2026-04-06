import tiktoken
from typing import List
from pvx.models.base import Message

class TokenCounter:
    """
    Token counting using tiktoken.
    Estimates are conservative to leave headroom.
    """
    def __init__(self, model_name: str = "gpt-4"): # Default encoding
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))

    def count_messages(self, messages: List[Message]) -> int:
        tokens = 0
        for msg in messages:
            tokens += 4 # Overhead for role
            tokens += self.count_tokens(msg.content)
        tokens += 2 # Final assistant prefix
        return int(tokens * 1.05) # 5% safety buffer for local model variations

token_counter = TokenCounter()
