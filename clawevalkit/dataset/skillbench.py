"""SkillBench — 22 个任务，local harness + pytest 验证。

评分方式: Agent 生成 diff patch → apply → pytest 验证 (pass/fail)。
需要 ark_adapter.py 将 ARK API 适配为 SkillBench 的 agent 接口。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import BaseBenchmark


class SkillBench(BaseBenchmark):
    DISPLAY_NAME = "SkillBench"
    TASK_COUNT = 22
    SCORE_RANGE = "0-100%"

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        bench_dir = self.base_dir / "benchmarks" / "skillbench"
        if not bench_dir.exists():
            return {"score": 0, "total": 0, "error": f"skillbench dir not found"}

        import os
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = config["api_key"]
        env["OPENAI_API_URL"] = config["api_url"]
        env["SKILLBENCH_AGENT_MODEL"] = config["model"]

        total_pass, total_tasks = 0, 0
        packs = ["coding/swe-lite", "coding/tool-use", "docs/text-lite"]

        for pack in packs:
            report_name = f"{model_key}_{pack.replace('/', '_')}.json"
            cmd = ["python3", "-m", "harness.cli", "run",
                   "--runner", "local", "--pack", f"packs/{pack}",
                   "--mode", "baseline", "--agent-cmd", "python3 -m harness.agents.ark_adapter",
                   "--output", f"reports/{report_name}"]
            try:
                subprocess.run(cmd, cwd=str(bench_dir), capture_output=True, text=True, timeout=1800, env=env)
            except Exception:
                pass

            report = bench_dir / "reports" / report_name
            if report.exists():
                try:
                    data = json.loads(report.read_text())
                    agg = data.get("baseline", {}).get("aggregate", {})
                    total_pass += agg.get("passed", 0)
                    total_tasks += agg.get("total", 0)
                except Exception:
                    pass

        score = round(total_pass / total_tasks * 100, 1) if total_tasks else 0
        return {"score": score, "passed": total_pass, "total": total_tasks, "pass_rate": f"{total_pass}/{total_tasks}"}

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
