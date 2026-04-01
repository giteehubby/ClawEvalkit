"""Verifier for math-003: Statistical Analysis."""

import json
from pathlib import Path

import pytest

EXPECTED_MEAN_A = 48.0
EXPECTED_MEAN_B = 59.84
EXPECTED_STD_A = 3.1358
EXPECTED_STD_B = 2.9535
EXPECTED_T_STAT = -13.7427
EXPECTED_P_VALUE = 3.15e-18
EXPECTED_CONCLUSION = "significant"

STAT_TOLERANCE = 0.05
T_TOLERANCE = 0.5
P_VALUE_THRESHOLD = 0.001


@pytest.fixture
def workspace(request):
    return Path(request.config.getoption("--workspace"))


@pytest.fixture
def analysis(workspace):
    path = workspace / "analysis.json"
    assert path.exists(), "analysis.json not found in workspace"
    return json.loads(path.read_text())


# ── Core checks (weight 3) ──────────────────────────────────────────────────


@pytest.mark.weight(3)
def test_analysis_file_exists(workspace):
    assert (workspace / "analysis.json").exists(), "analysis.json not found"


@pytest.mark.weight(3)
def test_valid_json(workspace):
    path = workspace / "analysis.json"
    try:
        json.loads(path.read_text())
    except (json.JSONDecodeError, Exception) as e:
        pytest.fail(f"analysis.json is not valid JSON: {e}")


@pytest.mark.weight(3)
def test_has_mean_a(analysis):
    assert "mean_a" in analysis, "Missing 'mean_a' key"


@pytest.mark.weight(3)
def test_has_mean_b(analysis):
    assert "mean_b" in analysis, "Missing 'mean_b' key"


@pytest.mark.weight(3)
def test_has_std_a(analysis):
    assert "std_a" in analysis, "Missing 'std_a' key"


@pytest.mark.weight(3)
def test_has_std_b(analysis):
    assert "std_b" in analysis, "Missing 'std_b' key"


@pytest.mark.weight(3)
def test_has_t_statistic(analysis):
    assert "t_statistic" in analysis, "Missing 't_statistic' key"


@pytest.mark.weight(3)
def test_has_p_value(analysis):
    assert "p_value" in analysis, "Missing 'p_value' key"


@pytest.mark.weight(3)
def test_has_conclusion(analysis):
    assert "conclusion" in analysis, "Missing 'conclusion' key"


@pytest.mark.weight(3)
def test_mean_a_correct(analysis):
    actual = analysis["mean_a"]
    assert abs(actual - EXPECTED_MEAN_A) < STAT_TOLERANCE, (
        f"mean_a: expected ~{EXPECTED_MEAN_A}, got {actual}"
    )


@pytest.mark.weight(3)
def test_mean_b_correct(analysis):
    actual = analysis["mean_b"]
    assert abs(actual - EXPECTED_MEAN_B) < STAT_TOLERANCE, (
        f"mean_b: expected ~{EXPECTED_MEAN_B}, got {actual}"
    )


@pytest.mark.weight(3)
def test_std_a_correct(analysis):
    actual = analysis["std_a"]
    assert abs(actual - EXPECTED_STD_A) < STAT_TOLERANCE, (
        f"std_a: expected ~{EXPECTED_STD_A}, got {actual}"
    )


@pytest.mark.weight(3)
def test_std_b_correct(analysis):
    actual = analysis["std_b"]
    assert abs(actual - EXPECTED_STD_B) < STAT_TOLERANCE, (
        f"std_b: expected ~{EXPECTED_STD_B}, got {actual}"
    )


@pytest.mark.weight(3)
def test_t_statistic_correct(analysis):
    actual = analysis["t_statistic"]
    assert abs(actual - EXPECTED_T_STAT) < T_TOLERANCE, (
        f"t_statistic: expected ~{EXPECTED_T_STAT}, got {actual}"
    )


@pytest.mark.weight(3)
def test_p_value_correct(analysis):
    actual = analysis["p_value"]
    assert actual < P_VALUE_THRESHOLD, (
        f"p_value should be very small (< {P_VALUE_THRESHOLD}), got {actual}"
    )


@pytest.mark.weight(3)
def test_conclusion_correct(analysis):
    actual = analysis["conclusion"]
    assert actual == EXPECTED_CONCLUSION, (
        f"conclusion: expected '{EXPECTED_CONCLUSION}', got '{actual}'"
    )
