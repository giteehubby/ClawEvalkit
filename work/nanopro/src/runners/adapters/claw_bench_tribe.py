"""
TRIBE claw-bench adapter.

Reuses the original shell benchmark by injecting a local clawdbot-compatible
shim into PATH and parsing the benchmark's JSON summary.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from src.harness.agent.base import BaseAgent

logger = logging.getLogger("adapter.claw_bench_tribe")


class ClawBenchTribeAdapter:
    """Adapter for TRIBE-INC claw-bench."""

    DEFAULT_SMOKE_TESTS = [
        "01_basic_chat",
        "02_tool_use_response",
        "03_web_fetch_json",
        "07_instruction_following",
        "22_multi_turn_context",
        "24_code_generation",
        "33_json_output",
    ]

    def __init__(
        self,
        agent: BaseAgent,
        benchmark_dir: Path,
        output_dir: Path | None = None,
    ):
        self.agent = agent
        self.benchmark_dir = benchmark_dir
        self.output_dir = output_dir or Path("results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        writable_root = Path(__file__).resolve().parents[5]
        self.temp_root_base = writable_root / ".tmp_claw_bench_tribe"
        self.temp_root_base.mkdir(parents=True, exist_ok=True)
        self.tasks: list[str] = []

    def load_tasks(self) -> None:
        self.tasks = sorted(p.stem for p in (self.benchmark_dir / "tests").glob("*.sh"))
        logger.info("Loaded %d claw-bench-tribe tests", len(self.tasks))

    def run(
        self,
        task_ids: list[str] | None = None,
        runs_per_task: int = 1,
        smoke: bool = False,
    ) -> dict[str, Any]:
        if runs_per_task != 1:
            logger.warning("claw-bench-tribe adapter ignores runs_per_task=%s and runs once", runs_per_task)

        selected = task_ids or (self.DEFAULT_SMOKE_TESTS if smoke else self.tasks)
        if not selected:
            raise ValueError("No claw-bench-tribe tests selected")

        logger.info("Running claw-bench-tribe with %d tests", len(selected))
        result = self._run_original_benchmark(selected)
        output_path = self.output_dir / f"claw_bench_tribe_{int(time.time() * 1000):013d}.json"
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Results saved to: %s", output_path)
        return result

    def _run_original_benchmark(self, selected_tests: list[str]) -> dict[str, Any]:
        run_id = f"{int(time.time() * 1000):013d}"
        temp_root = self.temp_root_base / run_id
        run_dir = temp_root / "benchmark"
        workspace_dir = temp_root / "workspace"
        session_dir = temp_root / "sessions"

        try:
            shutil.copytree(self.benchmark_dir, run_dir)
            self._normalize_shell_line_endings(run_dir)
            self._filter_tests(run_dir / "tests", selected_tests)

            env = os.environ.copy()
            env["PATH"] = str((self.benchmark_dir.parent.parent / "scripts" / "shims").resolve()) + os.pathsep + env.get("PATH", "")
            env["OPENAI_BASE_URL"] = getattr(self.agent, "api_url", "") or env.get("OPENAI_BASE_URL", "")
            env["OPENAI_API_KEY"] = getattr(self.agent, "api_key", "") or env.get("OPENAI_API_KEY", "")
            env["MODEL"] = getattr(self.agent, "model", "") or env.get("MODEL", "")
            env["CLAW_TIMEOUT"] = str(getattr(self.agent, "timeout", 120))
            env["CLAWDBOT_SHIM_WORKSPACE"] = str(workspace_dir)
            env["CLAWDBOT_SHIM_SESSION_STORE"] = str(session_dir)
            env["CLAWDBOT_PYTHON"] = sys.executable

            proc = subprocess.run(
                ["bash", "run.sh", "--local", "--json"],
                cwd=str(run_dir),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(300, len(selected_tests) * 45),
                check=False,
            )

            summary = self._extract_json_summary(proc.stdout)
            return self._normalize_result(summary, selected_tests, proc)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    @staticmethod
    def _filter_tests(tests_dir: Path, selected_tests: list[str]) -> None:
        selected = {test if test.endswith(".sh") else f"{test}.sh" for test in selected_tests}
        for test_file in tests_dir.glob("*.sh"):
            if test_file.name not in selected:
                test_file.unlink()

    @staticmethod
    def _normalize_shell_line_endings(root: Path) -> None:
        for shell_file in root.rglob("*.sh"):
            raw = shell_file.read_bytes()
            normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            if normalized != raw:
                shell_file.write_bytes(normalized)

    @staticmethod
    def _extract_json_summary(stdout: str) -> dict[str, Any]:
        lines = stdout.splitlines()
        for idx, line in enumerate(lines):
            if line.lstrip().startswith("{"):
                candidate = "\n".join(lines[idx:])
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"Failed to parse claw-bench-tribe JSON summary from output:\n{stdout[-2000:]}")

    @staticmethod
    def _normalize_result(summary: dict[str, Any], selected_tests: list[str], proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        tests = summary.get("tests", [])
        results_block = summary.get("results", {})
        total = int(results_block.get("total", len(tests)))
        passed = int(results_block.get("passed", 0))
        failed = int(results_block.get("failed", max(0, total - passed)))
        critical = int(results_block.get("critical", 0))
        overall_score = (passed / total * 100.0) if total else 0.0

        task_scores = {}
        for item in tests:
            name = item.get("name", "unknown")
            status = item.get("status", "fail")
            score = 100.0 if status == "pass" else 0.0
            task_scores[name] = {
                "task_name": name,
                "mean": score,
                "std": 0.0,
                "status": status,
                "message": item.get("message", ""),
                "duration_ms": item.get("duration_ms", 0),
            }

        return {
            "benchmark": "claw-bench-tribe",
            "timestamp": time.time(),
            "overall_score": round(overall_score, 2),
            "total_tasks": total,
            "passed_tasks": passed,
            "failed_tasks": failed,
            "critical_failures": critical,
            "task_scores": task_scores,
        }
