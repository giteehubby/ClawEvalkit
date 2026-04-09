"""OpenAI Proxy API wrapper — for GPT / Gemini models via internal proxy."""

from .base import BaseAPI
from ..utils.api import call_llm


class OpenAIProxyAPI(BaseAPI):
    """GPT Proxy Provider (GPT-4.1, GPT-4o, GPT-5.2, Gemini 2.5 Pro, etc.)."""

    def generate(self, messages: list, max_tokens: int = 4096, **kwargs) -> str:
        return call_llm(messages, self.config, max_tokens=max_tokens,
                        timeout=kwargs.get("timeout", 120))
