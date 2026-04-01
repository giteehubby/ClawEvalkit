"""AgentBench-OpenClaw — 40 个任务，L0 规则 (60%) + L1 指标 (40%)。

评分方式: nanobot CLI 执行 → 检查输出文件 → 规则评分 (0~100)。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .base import BaseBenchmark


class AgentBench(BaseBenchmark):
    DISPLAY_NAME = "AgentBench"
    TASK_COUNT = 40
    SCORE_RANGE = "0-100"

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        import yaml
        tasks_dir = self.base_dir / "benchmarks" / "agentbench-openclaw" / "tasks"
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        tasks = self._load_tasks(tasks_dir)
        if sample and sample < len(tasks):
            import random; random.seed(42)
            tasks = random.sample(tasks, sample)

        out_dir = self.results_dir / "agentbench" / model_key
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

            cfg = yaml.safe_load(Path(task["yaml_path"]).read_text())
            workspace = Path(f"/tmp/eval_agent_{model_key}/{tid}")
            if workspace.exists(): shutil.rmtree(workspace)
            workspace.mkdir(parents=True, exist_ok=True)

            # 准备输入文件
            task_dir = Path(task["yaml_path"]).parent
            for inp in cfg.get("input_files", []):
                src = task_dir / inp
                if src.exists():
                    dst = workspace / inp
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)

            r = {"task_id": tid, "model_key": model_key, "status": "error", "scores": {}}
            try:
                config_path = self._write_config(model_key, config, workspace)
                user_msg = cfg.get("user_message", "")
                cmd = ["nanobot", "agent", "-c", str(config_path), "-w", str(workspace),
                       "-s", f"eval_{model_key}_{tid}", "-m", user_msg]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(workspace))

                expected = cfg.get("expected_outputs", [])
                if expected:
                    passed = sum(1 for e in expected if e.get("pattern") and (workspace / e["pattern"]).exists())
                    l0 = (passed / len(expected)) * 100
                else:
                    l0 = 0
                r["status"] = "success"
                r["scores"] = {"l0_score": l0, "overall_score": l0}
            except Exception as e:
                r["error"] = str(e)[:300]

            result_file.write_text(json.dumps(r, indent=2, ensure_ascii=False))
            shutil.rmtree(workspace, ignore_errors=True)
            results.append(r)

        scores = [r["scores"]["overall_score"] for r in results if r.get("status") == "success"]
        avg = round(sum(scores) / len(scores), 1) if scores else 0
        return {"score": avg, "passed": len(scores), "total": len(tasks), "details": results}

    def collect(self, model_key: str) -> dict | None:
        result_dir = self._find_result_dir("agentbench")
        if not result_dir:
            return None
        # 先查汇总文件
        for key_variant in [model_key, self._legacy_key(model_key)]:
            d = result_dir / key_variant
            if not d.exists():
                continue
            full = d / "results.json"
            if full.exists():
                try:
                    data = json.loads(full.read_text())
                    if "overall_score" in data:
                        return {"score": round(float(data["overall_score"]), 1), "total": 40}
                except Exception: pass
            # per-task
            scores = []
            for f in d.glob("*.json"):
                if f.name == "results.json": continue
                try:
                    r = json.loads(f.read_text())
                    if r.get("status") == "success":
                        scores.append(r["scores"].get("overall_score", 0))
                except Exception: pass
            if scores:
                return {"score": round(sum(scores) / len(scores), 1), "total": len(scores)}
        return None

    def _legacy_key(self, key):
        m = {"claude-sonnet": "claude-sonnet-4.6",
             "claude-opus": "claude-opus-4.6", "gemini-3.1-pro": "gemini-3-pro-preview-new"}
        return m.get(key, key)

    def _load_tasks(self, tasks_dir):
        import yaml
        tasks = []
        for cat_dir in sorted(tasks_dir.iterdir()):
            if not cat_dir.is_dir(): continue
            for task_dir in sorted(cat_dir.iterdir()):
                yaml_f = task_dir / "task.yaml"
                if yaml_f.exists():
                    tasks.append({"task_id": task_dir.name, "category": cat_dir.name, "yaml_path": str(yaml_f)})
        return tasks

    def _write_config(self, model_key, config, workspace):
        ark_key = os.getenv("OPENROUTER_API_KEY", "")
        or_key = os.getenv("OPENROUTER_API_KEY", "")
        if config["provider"] == "openrouter":
            cfg = {"providers": {"openrouter": {"apiKey": or_key}},
                   "agents": {"defaults": {"model": config["model"], "workspace": str(workspace), "maxToolIterations": 25}}}
        elif config["provider"] == "ark":
            cfg = {"providers": {"custom": {"apiKey": ark_key, "apiBase": config["api_url"]}},
                   "agents": {"defaults": {"model": config["model"], "workspace": str(workspace), "maxToolIterations": 25}}}
        else:
            cfg = {"providers": {"custom": {"apiKey": config["api_key"], "apiBase": config["api_url"]}},
                   "agents": {"defaults": {"model": config["model"], "workspace": str(workspace), "maxToolIterations": 25}}}
        p = workspace / ".nanobot_config.json"
        p.write_text(json.dumps(cfg, indent=2))
        return p
