"""Verifier for math-002: Knapsack Optimization."""

import json
from pathlib import Path

import pytest

OPTIMAL_VALUE = 42
OPTIMAL_WEIGHT = 15
CAPACITY = 15
VALID_ITEMS = {
    "compass": {"weight": 1, "value": 2},
    "water": {"weight": 2, "value": 6},
    "sandwich": {"weight": 3, "value": 9},
    "glucose": {"weight": 2, "value": 5},
    "banana": {"weight": 1, "value": 3},
    "laptop": {"weight": 5, "value": 14},
    "camera": {"weight": 4, "value": 10},
    "book": {"weight": 3, "value": 7},
}
OPTIMAL_ITEMS = {"water", "sandwich", "banana", "laptop", "camera"}


@pytest.fixture
def workspace(request):
    return Path(request.config.getoption("--workspace"))


@pytest.fixture
def solution(workspace):
    path = workspace / "solution.json"
    assert path.exists(), "solution.json not found in workspace"
    return json.loads(path.read_text())


# ── Core checks (weight 3) ──────────────────────────────────────────────────


@pytest.mark.weight(3)
def test_solution_file_exists(workspace):
    assert (workspace / "solution.json").exists(), "solution.json not found"


@pytest.mark.weight(3)
def test_valid_json(workspace):
    path = workspace / "solution.json"
    try:
        json.loads(path.read_text())
    except (json.JSONDecodeError, Exception) as e:
        pytest.fail(f"solution.json is not valid JSON: {e}")


@pytest.mark.weight(3)
def test_has_selected_items(solution):
    assert "selected_items" in solution, "Missing 'selected_items' key"


@pytest.mark.weight(3)
def test_has_total_value(solution):
    assert "total_value" in solution, "Missing 'total_value' key"


@pytest.mark.weight(3)
def test_has_total_weight(solution):
    assert "total_weight" in solution, "Missing 'total_weight' key"


@pytest.mark.weight(3)
def test_has_algorithm(solution):
    assert "algorithm" in solution, "Missing 'algorithm' key"


@pytest.mark.weight(3)
def test_selected_items_is_list(solution):
    assert isinstance(solution["selected_items"], list), "selected_items must be a list"


@pytest.mark.weight(3)
def test_selected_items_exist_in_input(solution):
    for item in solution["selected_items"]:
        assert item in VALID_ITEMS, f"Item '{item}' not found in input items"


@pytest.mark.weight(3)
def test_no_duplicate_items(solution):
    items = solution["selected_items"]
    assert len(items) == len(set(items)), "selected_items contains duplicates"


@pytest.mark.weight(3)
def test_total_weight_within_capacity(solution):
    assert solution["total_weight"] <= CAPACITY, (
        f"Total weight {solution['total_weight']} exceeds capacity {CAPACITY}"
    )


@pytest.mark.weight(3)
def test_total_weight_matches_selected(solution):
    computed = sum(VALID_ITEMS[name]["weight"] for name in solution["selected_items"])
    assert computed == solution["total_weight"], (
        f"Reported total_weight {solution['total_weight']} doesn't match computed {computed}"
    )


@pytest.mark.weight(3)
def test_total_value_matches_selected(solution):
    computed = sum(VALID_ITEMS[name]["value"] for name in solution["selected_items"])
    assert computed == solution["total_value"], (
        f"Reported total_value {solution['total_value']} doesn't match computed {computed}"
    )


@pytest.mark.weight(3)
def test_total_value_is_optimal(solution):
    assert abs(solution["total_value"] - OPTIMAL_VALUE) <= 1, (
        f"Total value {solution['total_value']} is not optimal (expected {OPTIMAL_VALUE})"
    )


# ── Bonus checks (weight 1) ─────────────────────────────────────────────────


@pytest.mark.weight(1)
def test_algorithm_is_string(solution):
    assert isinstance(solution["algorithm"], str), "algorithm must be a string"


@pytest.mark.weight(1)
def test_algorithm_non_empty(solution):
    assert len(solution["algorithm"].strip()) > 0, "algorithm description must not be empty"


@pytest.mark.weight(1)
def test_total_weight_is_number(solution):
    assert isinstance(solution["total_weight"], (int, float)), "total_weight must be a number"


@pytest.mark.weight(1)
def test_total_value_is_number(solution):
    assert isinstance(solution["total_value"], (int, float)), "total_value must be a number"
