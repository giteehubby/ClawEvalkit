#!/usr/bin/env python3
"""
从 failed CSV 中移除已经 pass 或已放弃的 task，覆盖原文件。

用法:
  python error_analysis/filter_failed_tasks.py error_analysis/inputs/control_a_failed.csv \
      --give-up error_analysis/inputs/control_give_up.csv \
      --harness control
"""

import argparse
import csv
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
HARNESS_DIR = BASE_DIR / "outputs" / "harness"
MODEL = "glm-4.7"

BENCH_DIR_MAP = {
    "agentbench": "agentbench",
    "clawbench": "clawbench-official",
    "claweval": "claweval",
}


def check_passed(bench: str, harness: str, task_id: str) -> bool | None:
    """复用 compute_fix_rates.py 的判定逻辑，返回 True/False/None(未跑)"""
    bench_dir = BENCH_DIR_MAP.get(bench)
    if not bench_dir:
        return None
    base = HARNESS_DIR / harness / bench_dir / MODEL

    if bench == "agentbench":
        result_file = base / task_id / "result.json"
    elif bench == "clawbench":
        result_file = base / f"{task_id}.json"
    elif bench == "claweval":
        result_file = base / task_id / "result.json"
    else:
        return None

    if not result_file.exists():
        return None
    try:
        with open(result_file, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if bench == "agentbench":
        return data.get("scores", {}).get("overall_score", 0) >= 90
    return data.get("passed", False) or data.get("score", 0) >= 0.9


def read_csv(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({"bench_id": row["bench_id"], "task_id": row["task_id"]})
    return rows


def write_csv(path: Path, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["bench_id", "task_id"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="从 failed CSV 中移除已 pass / 已放弃的 task")
    parser.add_argument("failed_csv", help="待过滤的 failed CSV 文件路径")
    parser.add_argument("--give-up", required=True, help="已放弃的 task CSV 文件路径")
    parser.add_argument("--harness", default="control", help="检查 pass 时使用的 harness 名称")
    args = parser.parse_args()

    failed_path = Path(args.failed_csv)
    give_up_path = Path(args.give_up)
    harness = args.harness

    # 读取
    failed_rows = read_csv(failed_path)
    give_up_rows = read_csv(give_up_path)

    give_up_set = {(r["bench_id"], r["task_id"]) for r in give_up_rows}

    # 过滤
    kept, removed_pass, removed_giveup = [], [], []
    for row in failed_rows:
        key = (row["bench_id"], row["task_id"])
        if key in give_up_set:
            removed_giveup.append(row)
            continue
        result = check_passed(row["bench_id"], harness, row["task_id"])
        if result is True:
            removed_pass.append(row)
            continue
        kept.append(row)

    # 覆盖原文件
    write_csv(failed_path, kept)

    # 打印摘要
    print(f"原始任务数: {len(failed_rows)}")
    print(f"已 pass 移除: {len(removed_pass)}")
    for r in removed_pass:
        print(f"  [PASS] {r['bench_id']}/{r['task_id']}")
    print(f"已放弃移除: {len(removed_giveup)}")
    for r in removed_giveup:
        print(f"  [GIVE UP] {r['bench_id']}/{r['task_id']}")
    print(f"剩余任务数: {len(kept)}")
    print(f"已覆盖写入: {failed_path}")


if __name__ == "__main__":
    main()

'''
python error_analysis/filter_failed_tasks.py error_analysis/inputs/control_A.csv \
    --give-up error_analysis/inputs/control_give_up.csv \
    --harness control

python error_analysis/filter_failed_tasks.py error_analysis/inputs/collaboration_D.csv \
    --give-up error_analysis/inputs/control_give_up.csv \
    --harness collaboration

python error_analysis/filter_failed_tasks.py error_analysis/inputs/control_D.csv \
    --give-up error_analysis/inputs/control_give_up.csv \
    --harness control

'''