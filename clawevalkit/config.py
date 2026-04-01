"""Configuration loader — loads model configs from YAML files and env vars.

Replaces the hardcoded MODELS dict in utils/env.py with YAML-based config
(OpenCompass style), while keeping VLMEvalKit's simple dict-based registry.

Usage:
    from clawevalkit.config import MODELS, load_env, get_model_config, list_models

Config files are loaded from configs/models/*.yaml by default.
Each YAML file defines one or more models with fields:
    name, api_url, api_key_env, model, provider
"""
import os
from pathlib import Path

import yaml


def _find_project_root() -> Path:
    """Find the project root (directory containing run.py or configs/)."""
    # Try from this file's location
    pkg_dir = Path(__file__).resolve().parent  # clawevalkit/
    root = pkg_dir.parent
    if (root / "configs").exists() or (root / "run.py").exists():
        return root
    # Fallback: current working directory
    cwd = Path.cwd()
    if (cwd / "configs").exists():
        return cwd
    return root


def load_configs(config_dir: str | Path = None) -> dict:
    """Load all model configs from YAML files in config_dir/models/.

    Scans configs/models/*.yaml, merges all entries into a single dict.
    Files starting with '_' (e.g., _template.yaml) are skipped.
    Returns: {model_key: {name, api_url, api_key_env, model, provider}}
    """
    if config_dir is None:
        config_dir = _find_project_root() / "configs"
    else:
        config_dir = Path(config_dir)

    models_dir = config_dir / "models"
    if not models_dir.exists():
        return {}

    merged = {}
    for yaml_file in sorted(models_dir.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # Each top-level key is a model_key
                for key, cfg in data.items():
                    if isinstance(cfg, dict) and "model" in cfg:
                        merged[key] = cfg
        except Exception:
            pass
    return merged


def load_env(env_file: str = None) -> str | None:
    """Load API keys from a .env file into os.environ.

    Search order: explicit path > .env in project root > parent directories.
    Only sets vars that are not already in the environment.
    """
    candidates = []
    if env_file:
        candidates.append(Path(env_file))

    root = _find_project_root()
    candidates.append(root / ".env")

    for p in candidates:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v
            return str(p)
    return None


def get_model_config(model_key: str) -> dict:
    """Return full API config for a model, with api_key resolved from env var."""
    if model_key not in MODELS:
        raise ValueError(f"Unknown model: {model_key}. Available: {list(MODELS.keys())}")
    cfg = dict(MODELS[model_key])
    cfg["api_key"] = os.getenv(cfg.pop("api_key_env", ""), "")
    return cfg


def list_models() -> list:
    """Return [(key, name, provider)] for all registered models."""
    return [(k, v["name"], v["provider"]) for k, v in MODELS.items()]


# ─── Auto-load on import ───
MODELS = load_configs()
