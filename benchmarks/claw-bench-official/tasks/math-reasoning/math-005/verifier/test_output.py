"""Verifier for math-005: Algorithm Design — Longest Increasing Subsequence."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

INPUT_ARRAY = [4, 3, 7, 2, 6, 1, 11, 5, 10, 15, 9, 14, 8, 18, 13, 17, 12, 20, 16, 19]
EXPECTED_LIS_LENGTH = 6


@pytest.fixture
def workspace(request):
    return Path(request.config.getoption("--workspace"))


@pytest.fixture
def solution(workspace):
    path = workspace / "solution.json"
    assert path.exists(), "solution.json not found in workspace"
    return json.loads(path.read_text())


@pytest.fixture
def algorithm_path(workspace):
    return workspace / "algorithm.py"


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
def test_has_length(solution):
    assert "length" in solution, "Missing 'length' key in solution.json"


@pytest.mark.weight(3)
def test_has_subsequence(solution):
    assert "subsequence" in solution, "Missing 'subsequence' key in solution.json"


@pytest.mark.weight(3)
def test_algorithm_file_exists(workspace):
    assert (workspace / "algorithm.py").exists(), "algorithm.py not found"


@pytest.mark.weight(3)
def test_length_is_integer(solution):
    assert isinstance(solution["length"], int), f"length must be an integer, got {type(solution['length'])}"


@pytest.mark.weight(3)
def test_length_correct(solution):
    actual = solution["length"]
    assert actual == EXPECTED_LIS_LENGTH, (
        f"LIS length: expected {EXPECTED_LIS_LENGTH}, got {actual}"
    )


@pytest.mark.weight(3)
def test_subsequence_is_list(solution):
    assert isinstance(solution["subsequence"], list), "subsequence must be a list"


@pytest.mark.weight(3)
def test_subsequence_length_matches(solution):
    assert len(solution["subsequence"]) == solution["length"], (
        f"subsequence has {len(solution['subsequence'])} elements but length says {solution['length']}"
    )


@pytest.mark.weight(3)
def test_subsequence_is_increasing(solution):
    seq = solution["subsequence"]
    for i in range(len(seq) - 1):
        assert seq[i] < seq[i + 1], (
            f"Subsequence not strictly increasing at index {i}: {seq[i]} >= {seq[i+1]}"
        )


@pytest.mark.weight(3)
def test_subsequence_elements_in_input(solution):
    arr = INPUT_ARRAY[:]
    for val in solution["subsequence"]:
        assert val in arr, f"Subsequence element {val} not found in input array"


@pytest.mark.weight(3)
def test_subsequence_indices_valid(solution):
    """Verify the subsequence appears in order in the input array."""
    seq = solution["subsequence"]
    idx = 0
    for val in seq:
        found = False
        while idx < len(INPUT_ARRAY):
            if INPUT_ARRAY[idx] == val:
                found = True
                idx += 1
                break
            idx += 1
        assert found, f"Cannot find {val} in input array after previous match"


@pytest.mark.weight(3)
def test_subsequence_non_empty(solution):
    assert len(solution["subsequence"]) > 0, "subsequence must not be empty"


@pytest.mark.weight(3)
def test_algorithm_py_runs(workspace, algorithm_path):
    if not algorithm_path.exists():
        pytest.skip("algorithm.py not found")
    ws_abs = str(workspace.resolve())
    algo_abs = str(algorithm_path.resolve())
    result = subprocess.run(
        [sys.executable, algo_abs, ws_abs],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"algorithm.py failed with exit code {result.returncode}.\n"
        f"stderr: {result.stderr[:500]}"
    )


@pytest.mark.weight(3)
def test_algorithm_py_output_correct(workspace, algorithm_path):
    if not algorithm_path.exists():
        pytest.skip("algorithm.py not found")
    ws_abs = str(workspace.resolve())
    algo_abs = str(algorithm_path.resolve())
    sol_path = workspace / "solution.json"
    backup = None
    if sol_path.exists():
        backup = sol_path.read_text()

    subprocess.run(
        [sys.executable, algo_abs, ws_abs],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert sol_path.exists(), "algorithm.py did not produce solution.json"
    algo_result = json.loads(sol_path.read_text())
    assert algo_result["length"] == EXPECTED_LIS_LENGTH, (
        f"algorithm.py produced length {algo_result['length']}, expected {EXPECTED_LIS_LENGTH}"
    )

    if backup is not None:
        sol_path.write_text(backup)


# ── Bonus checks (weight 1) ─────────────────────────────────────────────────


@pytest.mark.weight(1)
def test_algorithm_py_has_function(algorithm_path):
    if not algorithm_path.exists():
        pytest.skip("algorithm.py not found")
    code = algorithm_path.read_text()
    has_bisect = "bisect" in code
    has_dp = "dp" in code.lower() or "dynamic" in code.lower()
    has_loop = "for " in code
    assert has_loop, "algorithm.py should contain iteration logic"
    assert has_bisect or has_dp or ("tails" in code), (
        "algorithm.py should use an efficient approach (DP or binary search)"
    )


@pytest.mark.weight(1)
def test_algorithm_not_brute_force(algorithm_path):
    if not algorithm_path.exists():
        pytest.skip("algorithm.py not found")
    code = algorithm_path.read_text()
    has_itertools = "itertools" in code and ("combinations" in code or "permutations" in code)
    has_powerset = "powerset" in code or "2**" in code or "power_set" in code
    assert not has_itertools and not has_powerset, (
        "algorithm.py appears to use brute-force enumeration"
    )


@pytest.mark.weight(1)
def test_algorithm_py_reads_input(algorithm_path):
    if not algorithm_path.exists():
        pytest.skip("algorithm.py not found")
    code = algorithm_path.read_text()
    assert "input.json" in code, "algorithm.py should read from input.json"


@pytest.mark.weight(1)
def test_algorithm_py_writes_output(algorithm_path):
    if not algorithm_path.exists():
        pytest.skip("algorithm.py not found")
    code = algorithm_path.read_text()
    assert "solution.json" in code, "algorithm.py should write to solution.json"


@pytest.mark.weight(1)
def test_algorithm_py_no_hardcoded_answer(algorithm_path):
    if not algorithm_path.exists():
        pytest.skip("algorithm.py not found")
    code = algorithm_path.read_text()
    has_hardcoded = f'"length": {EXPECTED_LIS_LENGTH}' in code or f"'length': {EXPECTED_LIS_LENGTH}" in code
    has_array_literal = str(INPUT_ARRAY) in code
    assert not (has_hardcoded and has_array_literal), (
        "algorithm.py should compute the answer, not hardcode it"
    )


@pytest.mark.weight(1)
def test_input_array_preserved(workspace):
    path = workspace / "input.json"
    assert path.exists(), "input.json should still exist"
    data = json.loads(path.read_text())
    assert data["array"] == INPUT_ARRAY, "input.json was modified"


@pytest.mark.weight(1)
def test_algorithm_reasonable_complexity(algorithm_path):
    """Check that algorithm doesn't have obvious exponential patterns."""
    if not algorithm_path.exists():
        pytest.skip("algorithm.py not found")
    code = algorithm_path.read_text()
    has_recursion_without_memo = (
        "def " in code
        and code.count("def ") > 0
        and "memo" not in code.lower()
        and "cache" not in code.lower()
        and "lru_cache" not in code
        and "functools" not in code
    )
    has_dp_or_bisect = (
        "bisect" in code
        or "dp" in code.lower()
        or "tails" in code
        or "for " in code
    )
    if has_recursion_without_memo and not has_dp_or_bisect:
        pytest.fail("Algorithm appears to use unoptimized recursion")
