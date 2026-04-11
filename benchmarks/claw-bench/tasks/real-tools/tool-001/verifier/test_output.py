"""Verifier for tool-001: Git Operations Script."""

import json
import re
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def workspace(request):
    return Path(request.config.getoption("--workspace"))


@pytest.fixture
def script_path(workspace):
    return workspace / "git_commands.sh"


@pytest.fixture
def script_content(script_path):
    assert script_path.exists(), "git_commands.sh not found in workspace"
    return script_path.read_text()


@pytest.fixture
def instructions(workspace):
    path = workspace / "repo_instructions.json"
    assert path.exists(), "repo_instructions.json not found"
    return json.loads(path.read_text())


# ── Core checks (weight 3) ──────────────────────────────────────────────────


@pytest.mark.weight(3)
def test_script_file_exists(workspace):
    assert (workspace / "git_commands.sh").exists(), "git_commands.sh not found"


@pytest.mark.weight(3)
def test_script_has_shebang(script_content):
    first_line = script_content.strip().split("\n")[0]
    assert first_line.startswith("#!"), "Script must start with a shebang line"
    assert "bash" in first_line.lower() or "sh" in first_line.lower(), (
        "Shebang must reference bash or sh"
    )


@pytest.mark.weight(3)
def test_script_has_branch_creation(script_content):
    has_checkout = "git checkout -b feature-login" in script_content
    has_switch = "git switch -c feature-login" in script_content
    assert has_checkout or has_switch, (
        "Script must contain 'git checkout -b feature-login' or 'git switch -c feature-login'"
    )


@pytest.mark.weight(3)
def test_script_has_commit(script_content):
    assert "git commit" in script_content, "Script must contain a git commit command"


@pytest.mark.weight(3)
def test_script_commit_has_message_flag(script_content):
    assert re.search(r"git\s+commit\s+-m", script_content), (
        "git commit must use -m flag for message"
    )


@pytest.mark.weight(3)
def test_script_commit_message_content(script_content):
    assert "Add login page" in script_content, (
        "Commit message must contain 'Add login page'"
    )


@pytest.mark.weight(3)
def test_script_has_tag(script_content):
    assert "git tag v1.0.0" in script_content or "git tag 'v1.0.0'" in script_content, (
        "Script must contain 'git tag v1.0.0'"
    )


@pytest.mark.weight(3)
def test_operations_in_correct_order(script_content):
    branch_pos = -1
    commit_pos = -1
    tag_pos = -1

    for i, line in enumerate(script_content.split("\n")):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "checkout -b feature-login" in stripped or "switch -c feature-login" in stripped:
            branch_pos = i
        if re.search(r"git\s+commit\s+-m", stripped):
            commit_pos = i
        if "git tag v1.0.0" in stripped:
            tag_pos = i

    assert branch_pos >= 0, "Branch creation command not found"
    assert commit_pos >= 0, "Commit command not found"
    assert tag_pos >= 0, "Tag command not found"
    assert branch_pos < commit_pos < tag_pos, (
        f"Operations must be in order: branch({branch_pos}) < commit({commit_pos}) < tag({tag_pos})"
    )


@pytest.mark.weight(3)
def test_script_no_bash_syntax_errors(script_path):
    result = subprocess.run(
        ["bash", "-n", str(script_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Bash syntax error: {result.stderr}"


@pytest.mark.weight(3)
def test_script_has_set_flags(script_content):
    has_set_e = "set -e" in script_content or "set -euo" in script_content
    assert has_set_e, "Script should use 'set -e' or 'set -euo pipefail' for safety"


# ── Bonus checks (weight 1) ─────────────────────────────────────────────────


@pytest.mark.weight(1)
def test_script_has_comments(script_content):
    lines = script_content.strip().split("\n")
    comment_lines = [l for l in lines[1:] if l.strip().startswith("#")]
    assert len(comment_lines) >= 2, (
        "Script should have at least 2 comment lines explaining operations"
    )


@pytest.mark.weight(1)
def test_script_has_git_add_before_commit(script_content):
    lines = [l.strip() for l in script_content.split("\n") if not l.strip().startswith("#")]
    add_pos = -1
    commit_pos = -1
    for i, line in enumerate(lines):
        if re.search(r"git\s+add", line):
            add_pos = i
        if re.search(r"git\s+commit", line):
            commit_pos = i
    if add_pos >= 0 and commit_pos >= 0:
        assert add_pos < commit_pos, "git add should come before git commit"
    else:
        pass


@pytest.mark.weight(1)
def test_script_uses_pipefail(script_content):
    assert "pipefail" in script_content, "Script should use 'set -euo pipefail'"


@pytest.mark.weight(1)
def test_script_not_empty(script_content):
    lines = [l for l in script_content.strip().split("\n") if l.strip() and not l.strip().startswith("#")]
    assert len(lines) >= 3, "Script should have at least 3 non-comment lines"


@pytest.mark.weight(1)
def test_script_no_dangerous_commands(script_content):
    dangerous = ["rm -rf /", "git push --force", ":(){ :|:& };:"]
    for cmd in dangerous:
        assert cmd not in script_content, f"Script contains dangerous command: {cmd}"
