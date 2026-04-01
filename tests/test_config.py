"""Test config loading from YAML files."""
from clawevalkit.config import MODELS, load_configs, list_models, get_model_config


def test_models_loaded():
    assert len(MODELS) >= 3


def test_load_configs():
    models = load_configs()
    assert "claude-sonnet" in models
    assert "claude-opus" in models
    assert "gemini-3.1-pro" in models


def test_model_has_required_fields():
    for key, cfg in MODELS.items():
        assert "name" in cfg, f"{key} missing 'name'"
        assert "api_url" in cfg, f"{key} missing 'api_url'"
        assert "model" in cfg, f"{key} missing 'model'"
        assert "provider" in cfg, f"{key} missing 'provider'"


def test_list_models():
    models = list_models()
    assert len(models) >= 3
    keys = [m[0] for m in models]
    assert "claude-sonnet" in keys


def test_get_model_config():
    cfg = get_model_config("claude-sonnet")
    assert cfg["provider"] == "openrouter"
    assert "api_url" in cfg
