#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
import subprocess


def main() -> int:
    if len(sys.argv) < 5:
        print("Usage: scripts/robustness_eval.py <pack> <mode> <predictions_dir> <perturbation> [out.json]", file=sys.stderr)
        return 2
    pack = sys.argv[1]
    mode = sys.argv[2]
    predictions_dir = sys.argv[3]
    perturbation = sys.argv[4]
    out = pathlib.Path(sys.argv[5]) if len(sys.argv) > 5 else None

    import os
    env = os.environ.copy()
    env["SKILLBENCH_PERTURBATION"] = perturbation

    cmd = [
        sys.executable,
        "-m",
        "harness.cli",
        "eval",
        "--pack",
        pack,
        "--mode",
        mode,
        "--predictions",
        predictions_dir,
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode

    report_path = pathlib.Path("reports/latest.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    agg = report.get("aggregate") or {}
    robustness = {
        "perturbation": perturbation,
        "success_rate": agg.get("success_rate"),
        "passed": agg.get("passed"),
        "task_failed": agg.get("task_failed"),
    }
    payload = json.dumps(robustness, indent=2)
    if out:
        out.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
