#!/usr/bin/env python3
"""
Suite integrity and anti-gaming measures.

Provides:
1. Seeded task variants (different constants/filenames per run)
2. Canary detection (tasks that catch shortcutting)
3. Authoritative test output verification
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class VariantConfig:
    """Configuration for generating task variants."""
    seed: int
    task_id: str

    def __post_init__(self):
        self.rng = random.Random(f"{self.seed}:{self.task_id}")

    def variant_int(self, base: int, variance: int = 10) -> int:
        """Generate a variant integer around a base value."""
        return base + self.rng.randint(-variance, variance)

    def variant_name(self, base: str, pool: list[str] | None = None) -> str:
        """Generate a variant name from a pool or by mutation."""
        if pool:
            return self.rng.choice(pool)
        # Simple mutation: swap some letters
        chars = list(base)
        if len(chars) > 2:
            i = self.rng.randint(0, len(chars) - 2)
            chars[i], chars[i+1] = chars[i+1], chars[i]
        return ''.join(chars)

    def variant_filename(self, base: str) -> str:
        """Generate a variant filename."""
        prefixes = ["", "my_", "test_", "new_", "v2_"]
        suffixes = ["", "_v2", "_new", "_fixed", "_updated"]
        name, ext = base.rsplit(".", 1) if "." in base else (base, "")
        prefix = self.rng.choice(prefixes)
        suffix = self.rng.choice(suffixes)
        new_name = f"{prefix}{name}{suffix}"
        return f"{new_name}.{ext}" if ext else new_name


def generate_suite_seed() -> int:
    """Generate a random suite seed for this run."""
    return random.randint(100000, 999999)


def compute_variant_hash(seed: int, task_ids: list[str]) -> str:
    """Compute a hash representing this variant configuration."""
    data = json.dumps({"seed": seed, "tasks": sorted(task_ids)}, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


# =============================================================================
# Canary Detection
# =============================================================================

CANARY_PATTERNS = [
    # Pattern: obvious fix that breaks hidden constraint
    {
        "id": "canary-obvious-trap",
        "description": "Fix looks trivial but breaks hidden test",
        "detection": "hidden_test_fails_after_obvious_fix",
    },
    # Pattern: hardcoded values that happen to pass
    {
        "id": "canary-hardcode-detect",
        "description": "Skill hardcodes expected output",
        "detection": "output_matches_without_logic",
    },
    # Pattern: test name leakage
    {
        "id": "canary-test-leakage",
        "description": "Skill reads test file to extract answers",
        "detection": "test_file_access_before_implementation",
    },
]


def detect_shortcutting(traces: list[dict]) -> list[dict]:
    """
    Analyze execution traces to detect potential shortcutting.

    Returns list of detected issues.
    """
    issues = []

    # Check for test file reads before implementation
    test_reads = []
    impl_writes = []
    for i, trace in enumerate(traces):
        tool = trace.get("tool", "")
        args = trace.get("args", {})
        path = args.get("path", "")

        if tool == "read_file" and "test" in path.lower():
            test_reads.append(i)
        if tool == "write_file" and "test" not in path.lower():
            impl_writes.append(i)

    # If tests were read before any implementation was written
    if test_reads and impl_writes and min(test_reads) < min(impl_writes):
        issues.append({
            "type": "test_leakage_suspected",
            "detail": "Test files read before implementation written",
            "severity": "warning",
        })

    # Check for suspiciously fast completion
    if len(traces) <= 2:
        # Only read task + wrote solution = might be hardcoded
        issues.append({
            "type": "minimal_exploration",
            "detail": "Very few tool calls - solution may be hardcoded",
            "severity": "info",
        })

    return issues


# =============================================================================
# Authoritative Test Output
# =============================================================================

@dataclass
class AuthoritativeTestResult:
    """Tamper-evident test result."""
    passed: bool
    output: str
    exit_code: int
    runtime_ms: float
    output_hash: str  # SHA256 of raw output

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "output_preview": self.output[:500] if len(self.output) > 500 else self.output,
            "output_hash": self.output_hash,
            "exit_code": self.exit_code,
            "runtime_ms": self.runtime_ms,
        }

    @classmethod
    def from_test_run(cls, output: str, exit_code: int, runtime_ms: float) -> "AuthoritativeTestResult":
        output_hash = hashlib.sha256(output.encode()).hexdigest()
        passed = exit_code == 0 and "FAILED" not in output.upper() and "ERROR" not in output.upper()
        return cls(
            passed=passed,
            output=output,
            exit_code=exit_code,
            runtime_ms=runtime_ms,
            output_hash=output_hash,
        )


def verify_test_output_integrity(claimed_output: str, claimed_hash: str) -> bool:
    """Verify that test output hasn't been tampered with."""
    actual_hash = hashlib.sha256(claimed_output.encode()).hexdigest()
    return actual_hash == claimed_hash


# =============================================================================
# Run Configuration Digest
# =============================================================================

@dataclass
class RunConfig:
    """Canonical run configuration for reproducibility."""
    suite_id: str
    suite_version: str
    suite_seed: int
    adapter_name: str
    adapter_version: str
    agent_model_id: str
    max_steps: int
    max_tool_calls: int
    max_wall_time_s: float
    temperature: float

    def to_dict(self) -> dict:
        return {
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "suite_seed": self.suite_seed,
            "adapter_name": self.adapter_name,
            "adapter_version": self.adapter_version,
            "agent_model_id": self.agent_model_id,
            "limits": {
                "max_steps": self.max_steps,
                "max_tool_calls": self.max_tool_calls,
                "max_wall_time_s": self.max_wall_time_s,
            },
            "temperature": self.temperature,
        }

    def compute_digest(self) -> str:
        """Compute SHA256 digest of canonical config."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


if __name__ == "__main__":
    # Test variant generation
    config = VariantConfig(seed=12345, task_id="swe-lite-001")
    print(f"Variant int: {config.variant_int(100)}")
    print(f"Variant name: {config.variant_name('calculate')}")
    print(f"Variant file: {config.variant_filename('calc.py')}")

    # Test run config digest
    run_config = RunConfig(
        suite_id="core-bugfix",
        suite_version="1.0.0",
        suite_seed=123456,
        adapter_name="agentic",
        adapter_version="0.2.0",
        agent_model_id="claude-sonnet-4-20250514",
        max_steps=15,
        max_tool_calls=50,
        max_wall_time_s=180.0,
        temperature=0.0,
    )
    print(f"Config digest: {run_config.compute_digest()}")
