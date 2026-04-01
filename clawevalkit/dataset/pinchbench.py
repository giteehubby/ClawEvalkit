"""PinchBench — 23 个任务，规则评分 (file/content/wordcount)。

评分方式: benchmark.py subprocess 规则评分 (0~100)。
部分模型有官方已跑出的分数，直接使用。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import BaseBenchmark

OFFICIAL_SCORES = {
    "claude-sonnet": 86.9,
    "claude-opus": 86.3,
    "gemini-2.5-pro": 61.4,
    "gpt-4o": 64.7,
}


class PinchBench(BaseBenchmark):
    DISPLAY_NAME = "PinchBench"
    TASK_COUNT = 23
    SCORE_RANGE = "0-100"

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        if model_key in OFFICIAL_SCORES:
            return {"score": OFFICIAL_SCORES[model_key], "passed": 0, "total": 23, "source": "official"}

        pinch_repo = self.base_dir / "benchmarks" / "pinchbench"
        if not pinch_repo.exists():
            return {"score": 0, "total": 0, "error": f"pinchbench repo not found: {pinch_repo}"}

        pinch_id = f"{config['provider']}/{config['model']}"
        out_dir = self.results_dir / "pinchbench" / model_key / "raw"
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = ["uv", "run", "scripts/benchmark.py", "--model", pinch_id,
               "--output-dir", str(out_dir), "--no-upload", "--suite", "all"]
        try:
            proc = subprocess.run(cmd, cwd=str(pinch_repo), capture_output=True, text=True, timeout=3600)
        except Exception as e:
            return {"score": 0, "total": 0, "error": str(e)[:300]}

        # 找最新结果文件
        for f in sorted(out_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text())
                score = self._parse_score(data)
                if score is not None:
                    result = {"score": score, "total": 23, "raw_file": str(f)}
                    self.save_result("pinchbench", model_key, result, "result.json")
                    return result
            except Exception: pass

        return {"score": 0, "total": 0, "error": "no result file found"}

    # 旧目录名 → 新 model key 映射
    LEGACY_KEYS = {
        "gemini-3.1-pro": "gemini-3-pro-preview-new",
    }

    def collect(self, model_key: str) -> dict | None:
        if model_key in OFFICIAL_SCORES:
            return {"score": OFFICIAL_SCORES[model_key], "total": 23, "source": "official"}
        result_dir = self._find_result_dir("pinchbench")
        if not result_dir:
            return None
        for key in [model_key, self.LEGACY_KEYS.get(model_key, "")]:
            if not key:
                continue
            result_f = result_dir / key / "result.json"
            if result_f.exists():
                try:
                    data = json.loads(result_f.read_text())
                    score = self._parse_score(data) if "tasks" in data else data.get("score")
                    if score is not None:
                        return {"score": score, "total": 23}
                except Exception:
                    pass
        return None

    def _parse_score(self, data: dict) -> float | None:
        if "tasks" not in data: return data.get("score")
        means = [float(t["grading"]["mean"]) for t in data["tasks"]
                 if "grading" in t and "mean" in t["grading"]]
        return round(sum(means) / len(means) * 100, 1) if means else None
