"""ClawBench Official — 250 个任务，ReAct Agent + Pytest 验证。

评分方式: pytest 规则评分 (0~100)。
需要 claw-bench-official 仓库中的 claw_bench 包。
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

from .base import BaseBenchmark


class ClawBenchOfficial(BaseBenchmark):
    DISPLAY_NAME = "ClawBench Official"
    TASK_COUNT = 250
    SCORE_RANGE = "0-100"

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """通过 subprocess 调用 claw_bench 包进行评测。"""
        bench_dir = self.base_dir / "benchmarks" / "claw-bench-official"
        if not bench_dir.exists():
            return {"score": 0, "passed": 0, "total": 0, "error": f"bench dir not found: {bench_dir}"}

        sample_n = sample or 250
        result_dir = self.results_dir / "clawbench-official"
        result_dir.mkdir(parents=True, exist_ok=True)

        # 内联 Python 脚本调用 claw_bench
        script = f"""
import json, random, sys
from pathlib import Path
from claw_bench.adapters.openclaw import OpenClawAdapter
from claw_bench.core.task_loader import load_all_tasks
from claw_bench.core.runner import run_single_task

tasks, dirs = load_all_tasks(Path('tasks'))
sample_n = min({sample_n}, len(tasks))
indices = random.sample(range(len(tasks)), sample_n) if sample_n < len(tasks) else list(range(len(tasks)))

adapter = OpenClawAdapter()
adapter.setup({{'model': '{config["model"]}', 'timeout': 300}})

results = []
for i, idx in enumerate(indices):
    task = tasks[idx]
    td = dirs[task.id]
    try:
        r = run_single_task(task, td, adapter, timeout=300)
        print(f'  [{{i+1}}/{{sample_n}}] {{task.id}}: {{"PASS" if r.passed else "FAIL"}} score={{r.score:.2f}}', flush=True)
        results.append({{'id': task.id, 'passed': r.passed, 'score': r.score}})
    except Exception as e:
        print(f'  [{{i+1}}/{{sample_n}}] {{task.id}}: ERROR {{e}}', flush=True)
        results.append({{'id': task.id, 'passed': False, 'score': 0.0}})

avg = sum(r['score'] for r in results) / max(len(results), 1) * 100
passed = sum(1 for r in results if r['passed'])
print(json.dumps({{'score': round(avg, 1), 'passed': passed, 'total': len(results), 'results': results}}))
"""
        import os
        env = os.environ.copy()
        env["OPENAI_COMPAT_BASE_URL"] = config["api_url"]
        env["OPENAI_COMPAT_API_KEY"] = config["api_key"]

        try:
            proc = subprocess.run(
                ["python3", "-c", script],
                cwd=str(bench_dir), capture_output=True, text=True, timeout=7200, env=env,
            )
            # 提取最后一行 JSON
            for line in reversed(proc.stdout.strip().splitlines()):
                try:
                    data = json.loads(line)
                    self.save_result("clawbench-official", model_key, data, f"{model_key}_sample{sample_n}.json")
                    return data
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            return {"score": 0, "passed": 0, "total": 0, "error": str(e)[:300]}

        return {"score": 0, "passed": 0, "total": 0, "error": "no output"}

    def collect(self, model_key: str) -> dict | None:
        result_dir = self._find_result_dir("clawbench-official")
        if not result_dir:
            return None
        for f in sorted(result_dir.glob(f"{model_key}*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                return {"score": data["avg_score"] if "avg_score" in data else data.get("score", 0),
                        "passed": data.get("passed", 0), "total": data.get("total", 0)}
            except Exception:
                pass
        return None
