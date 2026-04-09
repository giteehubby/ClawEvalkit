"""Base API model class — all API wrappers inherit from this.

Mirrors vlmeval/api/base.py: subclasses implement generate() to produce
a text response from a list of messages.
"""


class BaseAPI:
    """Abstract base for API model wrappers.

    Subclasses must implement generate(messages, **kwargs) -> str.
    """

    def __init__(self, model_key: str, config: dict):
        self.model_key = model_key
        self.config = config
        self.name = config.get("name", model_key)
        self.provider = config.get("provider", "unknown")

    def generate(self, messages: list, max_tokens: int = 4096, **kwargs) -> str:
        """Send messages to the API and return the response text."""
        raise NotImplementedError

    def __repr__(self):
        return f"{self.__class__.__name__}({self.model_key!r})"
