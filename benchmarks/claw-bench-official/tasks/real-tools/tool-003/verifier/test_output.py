"""Verifier for tool-003: Environment Configuration."""

import json
import re
from pathlib import Path

import pytest
import yaml

ENV_VARS = [
    "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
    "APP_SECRET_KEY", "APP_DEBUG", "APP_PORT", "API_KEY", "REDIS_URL",
]

PLACEHOLDERS = [
    "<your_", "changeme", "placeholder", "<true_or_false>",
    "<your_db_host>", "<your_db_port>", "<your_db_name>",
    "<your_db_user>", "<your_api_key>", "<your_redis_url>",
    "<your_app_port>",
]


@pytest.fixture
def workspace(request):
    return Path(request.config.getoption("--workspace"))


@pytest.fixture
def env_content(workspace):
    path = workspace / ".env"
    assert path.exists(), ".env not found"
    return path.read_text()


@pytest.fixture
def env_vars(env_content):
    variables = {}
    for line in env_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            variables[key.strip()] = value.strip()
    return variables


@pytest.fixture
def compose_content(workspace):
    path = workspace / "docker-compose.yml"
    if not path.exists():
        path = workspace / "docker-compose.yaml"
    assert path.exists(), "docker-compose.yml not found"
    return path.read_text()


@pytest.fixture
def compose_data(compose_content):
    return yaml.safe_load(compose_content)


# ── Core checks (weight 3) ──────────────────────────────────────────────────


@pytest.mark.weight(3)
def test_env_file_exists(workspace):
    assert (workspace / ".env").exists(), ".env file not found"


@pytest.mark.weight(3)
def test_compose_file_exists(workspace):
    exists = (workspace / "docker-compose.yml").exists() or (workspace / "docker-compose.yaml").exists()
    assert exists, "docker-compose.yml not found"


@pytest.mark.weight(3)
def test_env_has_all_variables(env_vars):
    for var in ENV_VARS:
        assert var in env_vars, f"Variable '{var}' missing from .env"


@pytest.mark.weight(3)
def test_env_no_placeholder_values(env_vars):
    for var, value in env_vars.items():
        for placeholder in PLACEHOLDERS:
            assert placeholder not in value.lower(), (
                f"Variable '{var}' still has placeholder value: '{value}'"
            )


@pytest.mark.weight(3)
def test_env_values_not_empty(env_vars):
    for var in ENV_VARS:
        if var in env_vars:
            assert env_vars[var], f"Variable '{var}' has empty value"


@pytest.mark.weight(3)
def test_compose_valid_yaml(compose_content):
    try:
        data = yaml.safe_load(compose_content)
        assert isinstance(data, dict), "docker-compose.yml must be a YAML mapping"
    except yaml.YAMLError as e:
        pytest.fail(f"docker-compose.yml is not valid YAML: {e}")


@pytest.mark.weight(3)
def test_compose_has_services(compose_data):
    assert "services" in compose_data, "docker-compose.yml must have 'services' key"
    assert len(compose_data["services"]) >= 1, "Must define at least one service"


@pytest.mark.weight(3)
def test_compose_service_has_environment(compose_data):
    services = compose_data.get("services", {})
    has_env = False
    for svc_name, svc_config in services.items():
        if "environment" in svc_config or "env_file" in svc_config:
            has_env = True
            break
    assert has_env, "At least one service must reference environment variables"


@pytest.mark.weight(3)
def test_compose_references_env_vars(compose_content):
    referenced = []
    for var in ENV_VARS:
        if f"${{{var}}}" in compose_content or var in compose_content:
            referenced.append(var)
    assert len(referenced) >= 5, (
        f"docker-compose.yml should reference at least 5 env vars, found {len(referenced)}: {referenced}"
    )


@pytest.mark.weight(3)
def test_env_db_port_is_numeric(env_vars):
    if "DB_PORT" in env_vars:
        assert env_vars["DB_PORT"].isdigit(), f"DB_PORT must be numeric, got '{env_vars['DB_PORT']}'"


@pytest.mark.weight(3)
def test_env_app_port_is_numeric(env_vars):
    if "APP_PORT" in env_vars:
        assert env_vars["APP_PORT"].isdigit(), f"APP_PORT must be numeric, got '{env_vars['APP_PORT']}'"


# ── Bonus checks (weight 1) ─────────────────────────────────────────────────


@pytest.mark.weight(1)
def test_env_debug_is_boolean(env_vars):
    if "APP_DEBUG" in env_vars:
        assert env_vars["APP_DEBUG"].lower() in ("true", "false", "0", "1"), (
            f"APP_DEBUG should be a boolean value, got '{env_vars['APP_DEBUG']}'"
        )


@pytest.mark.weight(1)
def test_env_redis_url_format(env_vars):
    if "REDIS_URL" in env_vars:
        assert env_vars["REDIS_URL"].startswith("redis://"), (
            f"REDIS_URL should start with 'redis://', got '{env_vars['REDIS_URL']}'"
        )


@pytest.mark.weight(1)
def test_compose_has_image_or_build(compose_data):
    services = compose_data.get("services", {})
    for svc_name, svc_config in services.items():
        has_image = "image" in svc_config
        has_build = "build" in svc_config
        assert has_image or has_build, f"Service '{svc_name}' should have 'image' or 'build'"


@pytest.mark.weight(1)
def test_compose_has_ports(compose_data):
    services = compose_data.get("services", {})
    has_ports = any("ports" in svc for svc in services.values())
    assert has_ports, "At least one service should expose ports"


@pytest.mark.weight(1)
def test_env_password_not_trivial(env_vars):
    if "DB_PASSWORD" in env_vars:
        pwd = env_vars["DB_PASSWORD"]
        assert len(pwd) >= 6, f"DB_PASSWORD should be at least 6 chars, got {len(pwd)}"
        assert pwd.lower() not in ("password", "123456", "admin"), (
            "DB_PASSWORD should not be a trivial value"
        )
