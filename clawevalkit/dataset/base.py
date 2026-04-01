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
        self.output_dir = output_dir or self.base_dir / "outputs"
        # Legacy fallback: also check assets/results/ for old data
        self._legacy_results_dir = self.base_dir / "assets" / "results"

    @property
    def results_dir(self) -> Path:
        """Primary results directory (outputs/)."""
        return self.output_dir

    @abstractmethod
    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """Run evaluation. Returns {"score": float, "passed": int, "total": int, ...}."""
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
