"""Verifier for math-001: Financial Calculations."""

import json
from pathlib import Path

import pytest

EXPECTED = {
    "problem_1": 11576.25,
    "problem_2": 350.00,
    "problem_3": 17500.00,
    "problem_4": 1199.10,
    "problem_5": 3333.33,
}

PROBLEM_KEYS = [f"problem_{i}" for i in range(1, 6)]


@pytest.fixture
def workspace(request):
    return Path(request.config.getoption("--workspace"))


@pytest.fixture
def answers(workspace):
    path = workspace / "answers.json"
    assert path.exists(), "answers.json not found in workspace"
    return json.loads(path.read_text())


# ── Core checks (weight 3) ──────────────────────────────────────────────────


@pytest.mark.weight(3)
def test_answers_file_exists(workspace):
    assert (workspace / "answers.json").exists(), "answers.json not found"


@pytest.mark.weight(3)
def test_answers_valid_json(workspace):
    path = workspace / "answers.json"
    try:
        json.loads(path.read_text())
    except (json.JSONDecodeError, Exception) as e:
        pytest.fail(f"answers.json is not valid JSON: {e}")


@pytest.mark.weight(3)
def test_answers_has_all_problems(answers):
    for key in PROBLEM_KEYS:
        assert key in answers, f"Missing key '{key}' in answers.json"


@pytest.mark.weight(3)
def test_each_answer_has_answer_field(answers):
    for key in PROBLEM_KEYS:
        assert "answer" in answers[key], f"{key} missing 'answer' field"


@pytest.mark.weight(3)
def test_each_answer_has_explanation_field(answers):
    for key in PROBLEM_KEYS:
        assert "explanation" in answers[key], f"{key} missing 'explanation' field"


@pytest.mark.weight(3)
def test_problem_1_compound_interest(answers):
    actual = answers["problem_1"]["answer"]
    expected = EXPECTED["problem_1"]
    assert abs(actual - expected) < 0.01, (
        f"Problem 1 (compound interest): expected {expected}, got {actual}"
    )


@pytest.mark.weight(3)
def test_problem_2_markup(answers):
    actual = answers["problem_2"]["answer"]
    expected = EXPECTED["problem_2"]
    assert abs(actual - expected) < 0.01, (
        f"Problem 2 (markup): expected {expected}, got {actual}"
    )


@pytest.mark.weight(3)
def test_problem_3_tax(answers):
    actual = answers["problem_3"]["answer"]
    expected = EXPECTED["problem_3"]
    assert abs(actual - expected) < 0.01, (
        f"Problem 3 (tax): expected {expected}, got {actual}"
    )


@pytest.mark.weight(3)
def test_problem_4_loan_payment(answers):
    actual = answers["problem_4"]["answer"]
    expected = EXPECTED["problem_4"]
    assert abs(actual - expected) < 0.02, (
        f"Problem 4 (loan payment): expected {expected}, got {actual}"
    )


@pytest.mark.weight(3)
def test_problem_5_break_even(answers):
    actual = answers["problem_5"]["answer"]
    expected = EXPECTED["problem_5"]
    assert abs(actual - expected) < 0.01, (
        f"Problem 5 (break-even): expected {expected}, got {actual}"
    )


@pytest.mark.weight(3)
def test_answers_are_numbers(answers):
    for key in PROBLEM_KEYS:
        val = answers[key]["answer"]
        assert isinstance(val, (int, float)), f"{key}: answer must be a number, got {type(val)}"


# ── Bonus checks (weight 1) ─────────────────────────────────────────────────


@pytest.mark.weight(1)
def test_explanations_are_strings(answers):
    for key in PROBLEM_KEYS:
        val = answers[key]["explanation"]
        assert isinstance(val, str), f"{key}: explanation must be a string"


@pytest.mark.weight(1)
def test_explanations_non_empty(answers):
    for key in PROBLEM_KEYS:
        val = answers[key]["explanation"]
        assert len(val.strip()) > 0, f"{key}: explanation must not be empty"


@pytest.mark.weight(1)
def test_explanations_minimum_length(answers):
    for key in PROBLEM_KEYS:
        val = answers[key]["explanation"]
        assert len(val.strip()) >= 20, (
            f"{key}: explanation should be at least 20 chars, got {len(val.strip())}"
        )


@pytest.mark.weight(1)
def test_no_extra_top_level_keys(answers):
    extra = set(answers.keys()) - set(PROBLEM_KEYS)
    assert not extra, f"Unexpected keys in answers.json: {extra}"
