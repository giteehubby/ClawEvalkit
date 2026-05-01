"""Base benchmark class — all benchmarks inherit from this.

Mirrors vlmeval/dataset/image_base.py pattern: each benchmark implements
evaluate() to run the full eval pipeline and returns a result dict.

Subclasses must implement:
  - evaluate(model_key, config, sample=0, **kwargs) → dict
  - collect(model_key) → dict | None  (optional, load cached results)
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path


class BaseBenchmark(ABC):
    DISPLAY_NAME = "Unknown"
    TASK_COUNT = 0
    SCORE_RANGE = "0-100"  # or "0-1"

    def __init__(self, base_dir: Path = None, output_dir: Path = None):
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent.parent
        # output_dir: configurable, defaults to ./outputs/ (like VLMEvalKit)
        if output_dir is None:
            self.output_dir = self.base_dir / "outputs"
        else:
            self.output_dir = Path(output_dir) if not isinstance(output_dir, Path) else output_dir
        # Legacy fallback: also check assets/results/ for old data
        self._legacy_results_dir = self.base_dir / "assets" / "results"

    @property
    def results_dir(self) -> Path:
        """Primary results directory (outputs/)."""
        return self.output_dir

    @abstractmethod
    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """Run evaluation. Returns {"score": float, "scored": int, "total": int, ...}."""
        ...

    def collect(self, model_key: str) -> dict | None:
        """Load cached results without re-running. Returns None if no results."""
        return None

    def save_result(self, bench_key: str, model_key: str, result: dict, filename: str = None):
        """Save evaluation result JSON to outputs/{bench_key}/."""
        out_dir = self.results_dir / bench_key
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"{model_key}.json"
        out_path = out_dir / fname
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return out_path

    def _find_result_dir(self, bench_key: str) -> Path | None:
        """Find result directory, checking both outputs/ and legacy assets/results/."""
        primary = self.results_dir / bench_key
        if primary.exists():
            return primary
        legacy = self._legacy_results_dir / bench_key
        if legacy.exists():
            return legacy
        return None

    def _save_task_result(self, bench_key: str, model_key: str, task_id: str, result: dict) -> Path:
        """保存单任务结果到 outputs/{bench_key}/{model_key}/{task_id}/result.json

        Args:
            bench_key: Benchmark identifier (e.g., "zclawbench")
            model_key: Model identifier
            task_id: Task identifier
            result: Result dict to save

        Returns:
            Path to saved result file
        """
        out_dir = self.results_dir / bench_key / model_key / task_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "result.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return out_path

    def _build_and_save_summary(
        self,
        bench_key: str,
        model_key: str,
        all_task_ids: list,
        new_results: list = None,
        compute_summary_fn=None
    ) -> dict:
        """构建并保存汇总结果（增量模式）。

        扫描所有已有的 per-task result.json，与 new_results 合并，
        调用 compute_summary_fn 计算汇总，保存到 outputs/{bench_key}/{model_key}.json

        Args:
            bench_key: Benchmark identifier
            model_key: Model identifier
            all_task_ids: List of all task IDs for this benchmark
            new_results: List of newly computed results (not yet saved to disk)
            compute_summary_fn: Function(results_list) -> summary_dict
                               Called with merged results from cache + new_results

        Returns:
            Summary dict
        """
        results = list(new_results) if new_results else []

        # 收集已有缓存（排除 new_results 中已有的）
        new_task_ids = {r.get("task_id") or r.get("task") for r in results}
        for task_id in all_task_ids:
            if task_id in new_task_ids:
                continue
            result_file = self.results_dir / bench_key / model_key / task_id / "result.json"
            if result_file.exists():
                try:
                    cached = json.loads(result_file.read_text())
                    cached["_from_cache"] = True
                    results.append(cached)
                except Exception:
                    pass

        # Compute summary using benchmark-specific logic
        if compute_summary_fn:
            summary = compute_summary_fn(results)
        else:
            # Default summary
            summary = {
                "model": model_key,
                "total": len(all_task_ids),
                "scored": len(results),
                "pending": len(all_task_ids) - len(results),
                "results": results
            }

        from ..utils.log import log
        log(f"[{bench_key}] 汇总已保存: {summary.get('passed', summary.get('scored', 0))}/{len(all_task_ids)} 完成")

        return summary
