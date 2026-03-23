#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys


def _load_report(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary(report: dict, label: str) -> dict:
    agg = report.get("aggregate") or {}
    return {
        "label": label,
        "task_pack": report.get("task_pack"),
        "success_rate": agg.get("success_rate"),
        "passed": agg.get("passed"),
        "task_failed": agg.get("task_failed"),
        "avg_runtime_s": agg.get("avg_runtime_s"),
    }


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: scripts/leaderboard.py <baseline.json> <augmented.json> [out.json]", file=sys.stderr)
        return 2
    baseline = pathlib.Path(sys.argv[1])
    augmented = pathlib.Path(sys.argv[2])
    out = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else None

    base_report = _load_report(baseline)
    aug_report = _load_report(augmented)

    summary = {
        "baseline": _summary(base_report, "baseline"),
        "augmented": _summary(aug_report, "augmented"),
        "delta": {
            "success_rate": None,
            "avg_runtime_s": None,
            "passed": None,
            "task_failed": None,
        },
    }
    for key in ["success_rate", "avg_runtime_s", "passed", "task_failed"]:
        base_val = summary["baseline"].get(key)
        aug_val = summary["augmented"].get(key)
        if base_val is not None and aug_val is not None:
            summary["delta"][key] = round(aug_val - base_val, 3)

    payload = json.dumps(summary, indent=2)
    if out:
        out.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
