"""Verifier for tool-004: Build Script (Makefile)."""

import re
from pathlib import Path

import pytest

REQUIRED_TARGETS = ["install", "test", "lint", "build", "clean", "docs", "all"]


@pytest.fixture
def workspace(request):
    return Path(request.config.getoption("--workspace"))


@pytest.fixture
def makefile_path(workspace):
    return workspace / "Makefile"


@pytest.fixture
def makefile_content(makefile_path):
    assert makefile_path.exists(), "Makefile not found in workspace"
    return makefile_path.read_text()


@pytest.fixture
def makefile_targets(makefile_content):
    """Extract target names from Makefile."""
    targets = set()
    for line in makefile_content.split("\n"):
        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):", line)
        if match:
            target = match.group(1)
            if target not in (".PHONY", ".DEFAULT", ".SUFFIXES"):
                targets.add(target)
    return targets


def get_target_recipe(makefile_content, target_name):
    """Extract recipe lines for a specific target."""
    lines = makefile_content.split("\n")
    recipe = []
    in_target = False
    for line in lines:
        if re.match(rf"^{re.escape(target_name)}\s*:", line):
            in_target = True
            continue
        elif in_target:
            if line.startswith("\t") or line.startswith("    "):
                recipe.append(line.strip())
            elif line.strip() and not line.startswith("#") and not line.startswith("\t"):
                break
    return recipe


# ── Core checks (weight 3) ──────────────────────────────────────────────────


@pytest.mark.weight(3)
def test_makefile_exists(workspace):
    assert (workspace / "Makefile").exists(), "Makefile not found"


@pytest.mark.weight(3)
def test_has_install_target(makefile_targets):
    assert "install" in makefile_targets, "Missing 'install' target"


@pytest.mark.weight(3)
def test_has_test_target(makefile_targets):
    assert "test" in makefile_targets, "Missing 'test' target"


@pytest.mark.weight(3)
def test_has_lint_target(makefile_targets):
    assert "lint" in makefile_targets, "Missing 'lint' target"


@pytest.mark.weight(3)
def test_has_build_target(makefile_targets):
    assert "build" in makefile_targets, "Missing 'build' target"


@pytest.mark.weight(3)
def test_has_clean_target(makefile_targets):
    assert "clean" in makefile_targets, "Missing 'clean' target"


@pytest.mark.weight(3)
def test_has_docs_target(makefile_targets):
    assert "docs" in makefile_targets, "Missing 'docs' target"


@pytest.mark.weight(3)
def test_has_all_target(makefile_targets):
    assert "all" in makefile_targets, "Missing 'all' target"


@pytest.mark.weight(3)
def test_uses_tabs_for_indentation(makefile_content):
    lines = makefile_content.split("\n")
    has_tab_indent = False
    spaces_only_indent = False
    for line in lines:
        if line.startswith("\t"):
            has_tab_indent = True
        elif re.match(r"^    \S", line):
            prev_line_idx = lines.index(line) - 1
            if prev_line_idx >= 0:
                prev = lines[prev_line_idx]
                if re.match(r"^[a-zA-Z_].*:", prev):
                    spaces_only_indent = True
    assert has_tab_indent, "Makefile recipes must use tab indentation"


@pytest.mark.weight(3)
def test_install_uses_pip(makefile_content):
    recipe = get_target_recipe(makefile_content, "install")
    recipe_text = " ".join(recipe)
    assert "pip" in recipe_text, "install target should use pip"


@pytest.mark.weight(3)
def test_test_uses_pytest(makefile_content):
    recipe = get_target_recipe(makefile_content, "test")
    recipe_text = " ".join(recipe)
    assert "pytest" in recipe_text, "test target should use pytest"


@pytest.mark.weight(3)
def test_clean_removes_pycache(makefile_content):
    recipe = get_target_recipe(makefile_content, "clean")
    recipe_text = " ".join(recipe)
    assert "__pycache__" in recipe_text, "clean target should remove __pycache__"


@pytest.mark.weight(3)
def test_all_has_dependencies(makefile_content):
    for line in makefile_content.split("\n"):
        match = re.match(r"^all\s*:(.*)", line)
        if match:
            deps = match.group(1).strip()
            assert "install" in deps or "test" in deps or "lint" in deps, (
                f"'all' target should depend on install/test/lint, got: '{deps}'"
            )
            return
    pytest.fail("'all' target not found")


@pytest.mark.weight(3)
def test_has_phony_declaration(makefile_content):
    assert ".PHONY" in makefile_content, "Makefile should declare .PHONY targets"


# ── Bonus checks (weight 1) ─────────────────────────────────────────────────


@pytest.mark.weight(1)
def test_all_depends_on_install_and_test(makefile_content):
    for line in makefile_content.split("\n"):
        match = re.match(r"^all\s*:(.*)", line)
        if match:
            deps = match.group(1).strip()
            has_install = "install" in deps
            has_test = "test" in deps
            has_lint = "lint" in deps
            assert has_install and has_test and has_lint, (
                f"'all' should depend on install, test, and lint. Got: '{deps}'"
            )
            return


@pytest.mark.weight(1)
def test_clean_removes_dist(makefile_content):
    recipe = get_target_recipe(makefile_content, "clean")
    recipe_text = " ".join(recipe)
    assert "dist" in recipe_text, "clean target should remove dist/"


@pytest.mark.weight(1)
def test_clean_removes_build_dir(makefile_content):
    recipe = get_target_recipe(makefile_content, "clean")
    recipe_text = " ".join(recipe)
    assert "build" in recipe_text, "clean target should remove build/"


@pytest.mark.weight(1)
def test_makefile_has_comments(makefile_content):
    comment_lines = [l for l in makefile_content.split("\n") if l.strip().startswith("#")]
    assert len(comment_lines) >= 3, "Makefile should have at least 3 comment lines"


@pytest.mark.weight(1)
def test_lint_uses_linter_tool(makefile_content):
    recipe = get_target_recipe(makefile_content, "lint")
    recipe_text = " ".join(recipe)
    has_linter = any(t in recipe_text for t in ["flake8", "pylint", "ruff", "mypy", "black"])
    assert has_linter, "lint target should use a Python linting tool"
