"""Verifier for tool-005: CI/CD Pipeline Design."""

import re
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def workspace(request):
    return Path(request.config.getoption("--workspace"))


@pytest.fixture
def workflow_path(workspace):
    candidates = [
        workspace / ".github" / "workflows" / "ci.yml",
        workspace / ".github" / "workflows" / "ci.yaml",
        workspace / ".github" / "workflows" / "main.yml",
        workspace / ".github" / "workflows" / "main.yaml",
        workspace / ".github" / "workflows" / "pipeline.yml",
        workspace / ".github" / "workflows" / "pipeline.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    wf_dir = workspace / ".github" / "workflows"
    if wf_dir.exists():
        yml_files = list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))
        if yml_files:
            return yml_files[0]
    pytest.fail("No workflow YAML file found in .github/workflows/")


@pytest.fixture
def workflow_content(workflow_path):
    return workflow_path.read_text()


@pytest.fixture
def workflow_data(workflow_content):
    try:
        return yaml.safe_load(workflow_content)
    except yaml.YAMLError as e:
        pytest.fail(f"Workflow YAML is invalid: {e}")


@pytest.fixture
def all_steps(workflow_data):
    """Collect all step contents across all jobs."""
    steps = []
    jobs = workflow_data.get("jobs", {})
    for job_name, job_config in jobs.items():
        for step in job_config.get("steps", []):
            steps.append(step)
    return steps


@pytest.fixture
def all_steps_text(workflow_content):
    """Raw text for broad pattern matching."""
    return workflow_content


# ── Core checks (weight 3) ──────────────────────────────────────────────────


@pytest.mark.weight(3)
def test_workflow_file_exists(workflow_path):
    assert workflow_path.exists(), "Workflow YAML file not found"


@pytest.mark.weight(3)
def test_workflow_valid_yaml(workflow_content):
    try:
        data = yaml.safe_load(workflow_content)
        assert isinstance(data, dict), "Workflow must be a YAML mapping"
    except yaml.YAMLError as e:
        pytest.fail(f"Invalid YAML: {e}")


@pytest.mark.weight(3)
def test_has_on_push_trigger(workflow_data):
    on_config = workflow_data.get("on") or workflow_data.get(True)
    assert on_config is not None, "Workflow must have 'on' trigger config"
    if isinstance(on_config, dict):
        assert "push" in on_config, "Workflow must trigger on push"
    elif isinstance(on_config, list):
        assert "push" in on_config, "Workflow must trigger on push"


@pytest.mark.weight(3)
def test_has_on_pull_request_trigger(workflow_data):
    on_config = workflow_data.get("on") or workflow_data.get(True)
    assert on_config is not None, "Workflow must have 'on' trigger config"
    if isinstance(on_config, dict):
        assert "pull_request" in on_config, "Workflow must trigger on pull_request"
    elif isinstance(on_config, list):
        assert "pull_request" in on_config, "Workflow must trigger on pull_request"


@pytest.mark.weight(3)
def test_push_triggers_on_main(workflow_data):
    on_config = workflow_data.get("on") or workflow_data.get(True)
    if isinstance(on_config, dict) and isinstance(on_config.get("push"), dict):
        branches = on_config["push"].get("branches", [])
        assert "main" in branches, f"Push should trigger on 'main' branch, got: {branches}"


@pytest.mark.weight(3)
def test_has_jobs(workflow_data):
    assert "jobs" in workflow_data, "Workflow must have 'jobs' section"
    assert len(workflow_data["jobs"]) >= 1, "Must have at least 1 job"


@pytest.mark.weight(3)
def test_has_checkout_step(all_steps_text):
    assert "actions/checkout" in all_steps_text, "Must use actions/checkout"


@pytest.mark.weight(3)
def test_has_setup_python_step(all_steps_text):
    assert "actions/setup-python" in all_steps_text, "Must use actions/setup-python"


@pytest.mark.weight(3)
def test_has_install_dependencies_step(all_steps_text):
    assert "pip install" in all_steps_text, "Must have a step to install dependencies"


@pytest.mark.weight(3)
def test_has_test_step(all_steps_text):
    assert "pytest" in all_steps_text, "Must have a step that runs pytest"


@pytest.mark.weight(3)
def test_has_lint_step(all_steps_text):
    has_linter = any(tool in all_steps_text for tool in ["flake8", "ruff", "pylint", "black"])
    assert has_linter, "Must have a linting step"


@pytest.mark.weight(3)
def test_has_docker_build(all_steps_text):
    assert "docker" in all_steps_text.lower(), "Must reference Docker in the pipeline"


@pytest.mark.weight(3)
def test_deploy_only_on_main(workflow_data):
    jobs = workflow_data.get("jobs", {})
    deploy_jobs = {k: v for k, v in jobs.items() if "deploy" in k.lower()}
    if not deploy_jobs:
        for k, v in jobs.items():
            if_cond = str(v.get("if", ""))
            if "main" in if_cond and ("deploy" in k.lower() or "deploy" in str(v.get("name", "")).lower()):
                deploy_jobs[k] = v
    if deploy_jobs:
        for name, config in deploy_jobs.items():
            if_cond = str(config.get("if", ""))
            assert "main" in if_cond, (
                f"Deploy job '{name}' must only run on main branch (if condition: '{if_cond}')"
            )
    else:
        all_text = str(workflow_data)
        assert "main" in all_text, "Pipeline must reference main branch for deployment gating"


@pytest.mark.weight(3)
def test_uses_proper_action_versions(all_steps_text):
    action_refs = re.findall(r"uses:\s*([^\s]+)", all_steps_text)
    for ref in action_refs:
        assert "@" in ref, f"Action '{ref}' should pin a version (e.g., @v4)"


@pytest.mark.weight(3)
def test_has_environment_variables(workflow_data):
    has_env = "env" in workflow_data
    jobs = workflow_data.get("jobs", {})
    job_env = any("env" in job for job in jobs.values())
    step_env = False
    for job in jobs.values():
        for step in job.get("steps", []):
            if "env" in step:
                step_env = True
                break
    assert has_env or job_env or step_env, "Workflow should define environment variables"


# ── Bonus checks (weight 1) ─────────────────────────────────────────────────


@pytest.mark.weight(1)
def test_has_matrix_strategy(workflow_data):
    jobs = workflow_data.get("jobs", {})
    has_matrix = any(
        "matrix" in str(job.get("strategy", {}))
        for job in jobs.values()
    )
    assert has_matrix, "Bonus: should use matrix strategy for multi-version testing"


@pytest.mark.weight(1)
def test_has_caching(all_steps_text):
    assert "cache" in all_steps_text.lower(), "Bonus: should cache pip dependencies"


@pytest.mark.weight(1)
def test_deploy_needs_test(workflow_data):
    jobs = workflow_data.get("jobs", {})
    for name, config in jobs.items():
        if "deploy" in name.lower():
            needs = config.get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            assert len(needs) >= 1, f"Deploy job should depend on other jobs (needs: {needs})"
            return
    pass


@pytest.mark.weight(1)
def test_has_secrets_reference(all_steps_text):
    assert "secrets." in all_steps_text, "Should reference GitHub secrets"


@pytest.mark.weight(1)
def test_has_meaningful_job_names(workflow_data):
    jobs = workflow_data.get("jobs", {})
    for name, config in jobs.items():
        job_name = config.get("name", name)
        assert len(job_name) >= 3, f"Job '{name}' should have a meaningful name"


@pytest.mark.weight(1)
def test_workflow_has_name(workflow_data):
    assert "name" in workflow_data, "Workflow should have a top-level 'name' field"


@pytest.mark.weight(1)
def test_has_aws_credentials_step(all_steps_text):
    assert "aws" in all_steps_text.lower(), "Should reference AWS for deployment"
