"""OpenRouter API wrapper — for Claude / Gemini models."""

from .base import BaseAPI
from ..utils.api import call_llm


class OpenRouterAPI(BaseAPI):
    """OpenRouter Provider (Claude Sonnet/Opus, Gemini 3.1 Pro, etc.)."""

    def generate(self, messages: list, max_tokens: int = 4096, **kwargs) -> str:
        return call_llm(messages, self.config, max_tokens=max_tokens,
                        timeout=kwargs.get("timeout", 120))
