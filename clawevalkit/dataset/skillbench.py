"""SkillBench — 22 个任务，local harness + pytest 验证。

评分方式: NanoBotAgent 直接在 repo 中修改代码 → pytest 验证 (pass/fail)。
使用 nanobot_adapter.py 将 NanoBotAgent 适配为 SkillBench 的 agent 接口。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import BaseBenchmark
from ..utils.log import log


class SkillBench(BaseBenchmark):
    DISPLAY_NAME = "SkillBench"
    TASK_COUNT = 22
    SCORE_RANGE = "0-100%"

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        bench_dir = self.base_dir / "benchmarks" / "skillbench"
        if not bench_dir.exists():
            return {"score": 0, "total": 0, "error": f"skillbench dir not found"}

        log(f"[skillbench] Starting evaluation for {model_key}")

        import os
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = config["api_key"]
        env["OPENAI_API_URL"] = config["api_url"]
        env["SKILLBENCH_AGENT_MODEL"] = config["model"]

        total_pass, total_tasks = 0, 0
        packs = ["coding/swe-lite", "coding/tool-use", "docs/text-lite"]

        for i, pack in enumerate(packs):
            log(f"[skillbench] Running pack {i+1}/{len(packs)}: {pack}")
            report_name = f"{model_key}_{pack.replace('/', '_')}.json"
            cmd = ["python3", "-m", "harness.cli", "run",
                   "--runner", "local", "--pack", f"packs/{pack}",
                   "--mode", "baseline", "--agent-cmd", "python3 -m harness.agents.nanobot_adapter",
                   "--output", f"reports/{report_name}"]
            try:
                result = subprocess.run(cmd, cwd=str(bench_dir), capture_output=True, text=True, timeout=1800, env=env)
                log(f"[skillbench] Pack {pack} completed with returncode={result.returncode}")
            except Exception as e:
                log(f"[skillbench] Pack {pack} failed: {e}")

            report = bench_dir / "reports" / report_name
            if report.exists():
                try:
                    data = json.loads(report.read_text())
                    agg = data.get("baseline", {}).get("aggregate", {})
                    pack_pass = agg.get("passed", 0)
                    pack_total = agg.get("total", 0)
                    total_pass += pack_pass
                    total_tasks += pack_total
                    log(f"[skillbench] Pack {pack}: {pack_pass}/{pack_total} passed")
                except Exception as e:
                    log(f"[skillbench] Failed to parse report: {e}")

        score = round(total_pass / total_tasks * 100, 1) if total_tasks else 0
        log(f"[skillbench] Final score: {score}% ({total_pass}/{total_tasks})")

        result = {"score": score, "passed": total_pass, "total": total_tasks, "pass_rate": f"{total_pass}/{total_tasks}"}
        return result


    def _compute_summary(self, model_key: str, all_task_ids: list, results: list) -> dict:
        """Compute summary for skillbench."""
        passed = sum(1 for r in results if r.get("status") == "passed")
        score = round(passed / len(all_task_ids) * 100, 1) if all_task_ids else 0
        total = len(all_task_ids)
        scored = len(results)
        return {
            "model": model_key,
            "score": score,
            "passed": passed,
            "failed": scored - passed,
            "pending": total - scored,
            "total": total,
            "details": results
        }

    def _load_summary(self, bench_key: str, model_key: str) -> dict:
        """Load saved summary file."""
        result_f = self.results_dir / bench_key / f"{model_key}.json"
        if result_f.exists():
            try:
                data = json.loads(result_f.read_text())
                return {"score": data["score"], "passed": data.get("passed", 0), "total": data["total"]}
            except Exception:
                pass
        return {"score": 0, "passed": 0, "total": 0}

    def collect(self, model_key: str) -> dict | None:
        bench_dir = self.base_dir / "benchmarks" / "skillbench"
        total_pass, total_tasks = 0, 0
        for f in sorted(bench_dir.glob(f"reports/{model_key}_*.json")):
            try:
                data = json.loads(f.read_text())
                agg = data.get("baseline", {}).get("aggregate", {})
                total_pass += agg.get("passed", 0)
                total_tasks += agg.get("total", 0)
            except Exception: pass
        if not total_tasks: return None
        return {"score": round(total_pass / total_tasks * 100, 1), "passed": total_pass, "total": total_tasks}
