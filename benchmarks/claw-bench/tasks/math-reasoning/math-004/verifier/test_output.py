"""Verifier for math-004: Resource Allocation (Linear Programming)."""

import json
from pathlib import Path

import pytest

EXPECTED_A = 10.0
EXPECTED_B = 20.0
EXPECTED_C = 15.0
EXPECTED_PROFIT = 485.0
EXPECTED_BINDING = {"labor", "material", "machine_time"}
QUANTITY_TOLERANCE = 0.5
PROFIT_TOLERANCE = 1.0

RESOURCE_COEFFICIENTS = {
    "labor": {"A": 2, "B": 3, "C": 4},
    "material": {"A": 4, "B": 2, "C": 2},
    "machine_time": {"A": 1, "B": 2, "C": 3},
}
RESOURCE_LIMITS = {"labor": 140, "material": 110, "machine_time": 95}
PROFITS = {"A": 9, "B": 10, "C": 13}


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
def test_has_product_a(solution):
    assert "product_A" in solution, "Missing 'product_A' key"


@pytest.mark.weight(3)
def test_has_product_b(solution):
    assert "product_B" in solution, "Missing 'product_B' key"


@pytest.mark.weight(3)
def test_has_product_c(solution):
    assert "product_C" in solution, "Missing 'product_C' key"


@pytest.mark.weight(3)
def test_has_total_profit(solution):
    assert "total_profit" in solution, "Missing 'total_profit' key"


@pytest.mark.weight(3)
def test_has_binding_constraints(solution):
    assert "binding_constraints" in solution, "Missing 'binding_constraints' key"


@pytest.mark.weight(3)
def test_product_a_non_negative(solution):
    assert solution["product_A"] >= -0.001, f"product_A must be non-negative, got {solution['product_A']}"


@pytest.mark.weight(3)
def test_product_b_non_negative(solution):
    assert solution["product_B"] >= -0.001, f"product_B must be non-negative, got {solution['product_B']}"


@pytest.mark.weight(3)
def test_product_c_non_negative(solution):
    assert solution["product_C"] >= -0.001, f"product_C must be non-negative, got {solution['product_C']}"


@pytest.mark.weight(3)
def test_labor_constraint_satisfied(solution):
    qa = solution["product_A"]
    qb = solution["product_B"]
    qc = solution["product_C"]
    usage = RESOURCE_COEFFICIENTS["labor"]["A"] * qa + \
            RESOURCE_COEFFICIENTS["labor"]["B"] * qb + \
            RESOURCE_COEFFICIENTS["labor"]["C"] * qc
    assert usage <= RESOURCE_LIMITS["labor"] + 0.01, (
        f"Labor constraint violated: {usage:.2f} > {RESOURCE_LIMITS['labor']}"
    )


@pytest.mark.weight(3)
def test_material_constraint_satisfied(solution):
    qa = solution["product_A"]
    qb = solution["product_B"]
    qc = solution["product_C"]
    usage = RESOURCE_COEFFICIENTS["material"]["A"] * qa + \
            RESOURCE_COEFFICIENTS["material"]["B"] * qb + \
            RESOURCE_COEFFICIENTS["material"]["C"] * qc
    assert usage <= RESOURCE_LIMITS["material"] + 0.01, (
        f"Material constraint violated: {usage:.2f} > {RESOURCE_LIMITS['material']}"
    )


@pytest.mark.weight(3)
def test_machine_constraint_satisfied(solution):
    qa = solution["product_A"]
    qb = solution["product_B"]
    qc = solution["product_C"]
    usage = RESOURCE_COEFFICIENTS["machine_time"]["A"] * qa + \
            RESOURCE_COEFFICIENTS["machine_time"]["B"] * qb + \
            RESOURCE_COEFFICIENTS["machine_time"]["C"] * qc
    assert usage <= RESOURCE_LIMITS["machine_time"] + 0.01, (
        f"Machine time constraint violated: {usage:.2f} > {RESOURCE_LIMITS['machine_time']}"
    )


@pytest.mark.weight(3)
def test_profit_calculation_correct(solution):
    qa = solution["product_A"]
    qb = solution["product_B"]
    qc = solution["product_C"]
    computed = PROFITS["A"] * qa + PROFITS["B"] * qb + PROFITS["C"] * qc
    reported = solution["total_profit"]
    assert abs(computed - reported) < 1.0, (
        f"Reported profit {reported} doesn't match computed {computed:.2f}"
    )


@pytest.mark.weight(3)
def test_total_profit_optimal(solution):
    actual = solution["total_profit"]
    assert abs(actual - EXPECTED_PROFIT) < PROFIT_TOLERANCE, (
        f"Total profit {actual} is not optimal (expected {EXPECTED_PROFIT})"
    )


@pytest.mark.weight(3)
def test_binding_constraints_correct(solution):
    reported = set(solution["binding_constraints"])
    assert reported == EXPECTED_BINDING, (
        f"Binding constraints {reported} don't match expected {EXPECTED_BINDING}"
    )


# ── Bonus checks (weight 1) ─────────────────────────────────────────────────


@pytest.mark.weight(1)
def test_binding_constraints_is_list(solution):
    assert isinstance(solution["binding_constraints"], list), "binding_constraints must be a list"


@pytest.mark.weight(1)
def test_quantities_are_numbers(solution):
    for key in ["product_A", "product_B", "product_C"]:
        assert isinstance(solution[key], (int, float)), f"{key} must be a number"


@pytest.mark.weight(1)
def test_total_profit_is_number(solution):
    assert isinstance(solution["total_profit"], (int, float)), "total_profit must be a number"


@pytest.mark.weight(1)
def test_all_resource_names_valid(solution):
    valid = {"labor", "material", "machine_time"}
    for c in solution["binding_constraints"]:
        assert c in valid, f"Unknown constraint name: '{c}'"
