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


def _delta(base: dict, aug: dict) -> dict:
    delta = {}
    for key in ["success_rate", "avg_runtime_s", "passed", "task_failed"]:
        base_val = base.get(key)
        aug_val = aug.get(key)
        if base_val is not None and aug_val is not None:
            delta[key] = round(aug_val - base_val, 3)
        else:
            delta[key] = None
    return delta


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: scripts/aggregate_leaderboard.py <root_dir> [out.json]", file=sys.stderr)
        return 2

    root = pathlib.Path(sys.argv[1]).resolve()
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None

    rows = []
    for skill_dir in sorted(root.glob("*")):
        if not skill_dir.is_dir():
            continue
        baseline = skill_dir / "baseline.json"
        augmented = skill_dir / "augmented.json"
        if not baseline.exists() or not augmented.exists():
            continue
        base_report = _load_report(baseline)
        aug_report = _load_report(augmented)

        row = {
            "skill": skill_dir.name,
            "baseline": _summary(base_report, "baseline"),
            "augmented": _summary(aug_report, "augmented"),
        }
        row["delta"] = _delta(row["baseline"], row["augmented"])
        rows.append(row)

    payload = json.dumps(rows, indent=2)
    if out:
        out.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
