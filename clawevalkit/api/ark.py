"""ARK API wrapper — OpenAI-compatible provider for ARK-style platforms."""

from .base import BaseAPI
from ..utils.api import call_llm


class ArkAPI(BaseAPI):
    """ARK Provider — OpenAI-compatible API wrapper."""

    def generate(self, messages: list, max_tokens: int = 4096, **kwargs) -> str:
        return call_llm(messages, self.config, max_tokens=max_tokens,
                        timeout=kwargs.get("timeout", 120))
