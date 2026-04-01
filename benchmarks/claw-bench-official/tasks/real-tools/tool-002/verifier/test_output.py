"""Verifier for tool-002: Dependency Conflict Resolution."""

import json
import re
from pathlib import Path

import pytest

ALL_PACKAGES = [
    "boto3", "celery", "click", "flask", "gunicorn", "jinja2",
    "numpy", "pandas", "pydantic", "pytest", "redis", "requests",
    "sqlalchemy",
]

CONFLICT_PACKAGES = {"requests", "flask", "click", "pydantic", "pandas", "sqlalchemy"}

ONLY_A_PACKAGES = {"celery", "jinja2", "redis"}
ONLY_B_PACKAGES = {"boto3", "pytest", "gunicorn"}


@pytest.fixture
def workspace(request):
    return Path(request.config.getoption("--workspace"))


@pytest.fixture
def resolved_content(workspace):
    path = workspace / "resolved.txt"
    assert path.exists(), "resolved.txt not found"
    return path.read_text()


@pytest.fixture
def resolved_packages(resolved_content):
    pkgs = {}
    for line in resolved_content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z0-9_-]+)(.*)", line)
        if match:
            pkgs[match.group(1).lower()] = match.group(2).strip()
    return pkgs


@pytest.fixture
def conflicts(workspace):
    path = workspace / "conflicts.json"
    assert path.exists(), "conflicts.json not found"
    return json.loads(path.read_text())


# ── Core checks (weight 3) ──────────────────────────────────────────────────


@pytest.mark.weight(3)
def test_resolved_file_exists(workspace):
    assert (workspace / "resolved.txt").exists(), "resolved.txt not found"


@pytest.mark.weight(3)
def test_conflicts_file_exists(workspace):
    assert (workspace / "conflicts.json").exists(), "conflicts.json not found"


@pytest.mark.weight(3)
def test_conflicts_valid_json(workspace):
    path = workspace / "conflicts.json"
    try:
        data = json.loads(path.read_text())
        assert isinstance(data, list), "conflicts.json must be a JSON array"
    except json.JSONDecodeError as e:
        pytest.fail(f"conflicts.json is not valid JSON: {e}")


@pytest.mark.weight(3)
def test_resolved_has_all_packages(resolved_packages):
    for pkg in ALL_PACKAGES:
        assert pkg in resolved_packages, f"Package '{pkg}' missing from resolved.txt"


@pytest.mark.weight(3)
def test_resolved_no_duplicate_packages(resolved_content):
    lines = [l.strip() for l in resolved_content.strip().split("\n") if l.strip() and not l.startswith("#")]
    pkg_names = []
    for line in lines:
        match = re.match(r"^([a-zA-Z0-9_-]+)", line)
        if match:
            pkg_names.append(match.group(1).lower())
    assert len(pkg_names) == len(set(pkg_names)), (
        f"Duplicate packages in resolved.txt: {[p for p in pkg_names if pkg_names.count(p) > 1]}"
    )


@pytest.mark.weight(3)
def test_resolved_is_sorted(resolved_packages):
    pkg_list = list(resolved_packages.keys())
    assert pkg_list == sorted(pkg_list), "Packages in resolved.txt must be sorted alphabetically"


@pytest.mark.weight(3)
def test_conflicts_detect_known_conflicts(conflicts):
    conflict_pkgs = {c["package"].lower() for c in conflicts}
    for pkg in ["requests", "flask", "click"]:
        assert pkg in conflict_pkgs, f"Conflict for '{pkg}' not detected"


@pytest.mark.weight(3)
def test_conflicts_have_required_fields(conflicts):
    required_fields = {"package", "version_a", "version_b", "resolution"}
    for conflict in conflicts:
        for field in required_fields:
            assert field in conflict, f"Conflict entry missing field '{field}': {conflict}"


@pytest.mark.weight(3)
def test_conflicts_resolutions_not_empty(conflicts):
    for conflict in conflicts:
        assert conflict["resolution"].strip(), (
            f"Conflict for '{conflict['package']}' has empty resolution"
        )


@pytest.mark.weight(3)
def test_resolved_packages_have_version_specs(resolved_packages):
    for pkg, spec in resolved_packages.items():
        assert spec, f"Package '{pkg}' in resolved.txt has no version specification"


@pytest.mark.weight(3)
def test_resolved_has_packages_only_in_a(resolved_packages):
    for pkg in ONLY_A_PACKAGES:
        assert pkg in resolved_packages, f"Package '{pkg}' (only in requirements_a) missing from resolved.txt"


@pytest.mark.weight(3)
def test_resolved_has_packages_only_in_b(resolved_packages):
    for pkg in ONLY_B_PACKAGES:
        assert pkg in resolved_packages, f"Package '{pkg}' (only in requirements_b) missing from resolved.txt"


# ── Bonus checks (weight 1) ─────────────────────────────────────────────────


@pytest.mark.weight(1)
def test_conflicts_flask_detected(conflicts):
    flask_conflicts = [c for c in conflicts if c["package"].lower() == "flask"]
    assert len(flask_conflicts) == 1, "Should detect exactly one conflict for flask"
    c = flask_conflicts[0]
    assert ">=2.0" in c["version_a"] or "2.0" in c["version_a"]
    assert "1.1.2" in c["version_b"]


@pytest.mark.weight(1)
def test_conflicts_requests_detected(conflicts):
    req_conflicts = [c for c in conflicts if c["package"].lower() == "requests"]
    assert len(req_conflicts) == 1, "Should detect exactly one conflict for requests"
    c = req_conflicts[0]
    assert "2.28" in c["version_a"]
    assert "2.25" in c["version_b"]


@pytest.mark.weight(1)
def test_resolved_version_specs_valid_format(resolved_packages):
    valid_pattern = re.compile(r'^(==|>=|<=|!=|~=|>|<)[\d]')
    for pkg, spec in resolved_packages.items():
        specs = [s.strip() for s in spec.split(",")]
        for s in specs:
            assert valid_pattern.match(s), (
                f"Invalid version spec for '{pkg}': '{s}'"
            )


@pytest.mark.weight(1)
def test_conflicts_count_reasonable(conflicts):
    assert len(conflicts) >= 3, "Should detect at least 3 conflicts"
    assert len(conflicts) <= 8, "Should detect at most 8 conflicts"


@pytest.mark.weight(1)
def test_resolved_package_names_lowercase(resolved_content):
    for line in resolved_content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z0-9_-]+)", line)
        if match:
            name = match.group(1)
            assert name == name.lower(), f"Package name '{name}' should be lowercase"
