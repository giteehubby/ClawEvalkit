"""WildClawBench Safety — 10 个安全对齐任务。

评分方式: NanoBotAgent 执行 + LLM Judge 评分 (0~1)。
数据来源: 本地 benchmarks/wildclawbench/tasks/06_Safety_Alignment/。

依赖:
  - 推理框架: OpenClawPro (提供 NanoBotAgent)
  - 评分逻辑: clawevalkit.grading (提供 run_judge_eval)
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from ..utils.nanobot import import_nanobot_agent
from .base import BaseBenchmark


class WildClawBench(BaseBenchmark):
    DISPLAY_NAME = "WildClawBench"
    TASK_COUNT = 10
    SCORE_RANGE = "0-1"

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """运行 WildClawBench 评测: 加载本地任务 → NanoBotAgent 执行 → Judge 评分。

        流程:
        1. 从本地 benchmarks 目录加载 Safety Alignment 类别的任务 markdown
        2. 使用 NanoBotAgent（来自 OpenClawPro）执行 agent 推理
        3. 使用 Judge Model 对执行轨迹进行评分
        4. 汇总所有任务的评分，返回平均分
        """
        NanoBotAgent = import_nanobot_agent()
        from clawevalkit.grading import run_judge_eval

        tasks = self._load_tasks()
        if sample and sample < len(tasks):
            import random; random.seed(42)
            tasks = random.sample(tasks, sample)

        judge_key = os.getenv("JUDGE_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
        judge_model = os.getenv("JUDGE_MODEL", "anthropic/claude-sonnet-4.6")
        judge_base = os.getenv("JUDGE_BASE_URL", "https://openrouter.ai/api/v1")

        out_dir = self.results_dir / "wildclawbench" / "subset" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []

        for task in tasks:
            tid = task["task_id"]
            result_file = out_dir / f"{tid}.json"
            if result_file.exists():
                try:
                    ex = json.loads(result_file.read_text())
                    if ex.get("status") == "success":
                        results.append(ex); continue
                except Exception: pass

            workspace = Path(f"/tmp/eval_wild_{model_key}/{tid}")
            if workspace.exists(): shutil.rmtree(workspace)
            workspace.mkdir(parents=True, exist_ok=True)

            r = {"task_id": tid, "model_key": model_key, "status": "error", "scores": {}}
            try:
                agent = NanoBotAgent(model=config["model"], api_url=config["api_url"],
                                     api_key=config["api_key"], workspace=workspace, timeout=300)
                result = agent.execute(task["prompt"], session_id=f"eval_wild_{model_key}_{tid}", workspace=workspace)
                if result.transcript:
                    normalized = [e["message"] if isinstance(e, dict) and "message" in e else e for e in result.transcript]
                    score = run_judge_eval(trajectory=normalized, task_id=tid, category="Safety",
                                           task_prompt=task["prompt"], judge_model=judge_model,
                                           api_key=judge_key, base_url=judge_base, model_name=config["name"])
                    r["status"] = "success"
                    r["scores"] = {"overall_score": score.overall_score}
            except Exception as e:
                r["error"] = str(e)[:300]

            result_file.write_text(json.dumps(r, indent=2, ensure_ascii=False))
            shutil.rmtree(workspace, ignore_errors=True)
            results.append(r)

        scores = [r["scores"]["overall_score"] for r in results if r.get("status") == "success"]
        avg = round(sum(scores) / len(scores), 3) if scores else 0
        return {"score": avg, "passed": len(scores), "total": len(tasks), "details": results}

    def collect(self, model_key: str) -> dict | None:
        result_dir = self._find_result_dir("wildclawbench")
        if not result_dir:
            return None
        out_dir = result_dir / "subset" / model_key
        if not out_dir.exists():
            return None
        scores = []
        for f in out_dir.glob("*.json"):
            try:
                r = json.loads(f.read_text())
                s = r.get("scores", {}).get("overall_score") or r.get("judge_scores", {}).get("overall_score")
                if r.get("status") == "success" and s is not None:
                    scores.append(float(s))
            except Exception: pass
        if not scores: return None
        return {"score": round(sum(scores) / len(scores), 3), "passed": len(scores), "total": self.TASK_COUNT}

    def _load_tasks(self):
        """加载 WildClawBench Safety 任务（从 ClawEvalKit 的 benchmarks/ 目录）。"""
        candidates = [
            self.base_dir / "benchmarks" / "wildclawbench" / "tasks" / "06_Safety_Alignment",
            Path(os.getenv("OPENCLAWPRO_DIR", "")) / "benchmarks" / "wildclawbench" / "tasks" / "06_Safety_Alignment",
        ]
        tasks = []
        for wild_dir in candidates:
            if wild_dir.exists():
                for md in sorted(wild_dir.glob("*.md")):
                    tasks.append({"task_id": md.stem, "prompt": md.read_text()})
                break
        return tasks
