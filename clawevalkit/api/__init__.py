"""API model registry — maps provider names to API wrapper classes.

Usage:
    from clawevalkit.api import get_model
    model = get_model("claude-sonnet")
    response = model.generate([{"role": "user", "content": "Hello"}])
"""
from .base import BaseAPI
from .ark import ArkAPI
from .openai_proxy import OpenAIProxyAPI
from .openrouter import OpenRouterAPI

# provider → class mapping
PROVIDERS = {
    "ark": ArkAPI,
    "gpt_proxy": OpenAIProxyAPI,
    "openai": OpenAIProxyAPI,
    "openrouter": OpenRouterAPI,
}


def get_model(model_key: str) -> BaseAPI:
    """Instantiate an API model wrapper from the config registry.

    Reads model config from clawevalkit.config.MODELS, resolves the API key,
    and returns a provider-specific BaseAPI instance.
    """
    from ..config import get_model_config

    config = get_model_config(model_key)
    provider = config.get("provider", "openai")
    cls = PROVIDERS.get(provider, OpenAIProxyAPI)
    return cls(model_key, config)
