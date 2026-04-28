#!/usr/bin/env python3
"""
从 fix_rates.json 提取 not_run_tasks，生成 run.py 可用的 CSV 任务列表。

Usage:
  python error_analysis/extract_not_run.py --harness control --class A
  python error_analysis/extract_not_run.py --harness control,memory --class A,B
  python error_analysis/extract_not_run.py --harness all --class all
"""
import argparse
import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIX_RATES_PATH = PROJECT_ROOT / "error_analysis" / "outputs" / "fix_rates.json"
OUTPUT_DIR = PROJECT_ROOT / "error_analysis" / "inputs"

ALL_HARNESSES = ["control", "memory", "collaboration", "procedure"]
ALL_CLASSES = ["A", "B", "C", "D", "E", "F"]


def parse_list(value: str, all_options: list[str]) -> list[str]:
    """解析逗号分隔的参数，支持 'all' 关键字"""
    if value.lower() == "all":
        return all_options
    return [v.strip() for v in value.split(",")]


def main():
    parser = argparse.ArgumentParser(description="提取 not_run_tasks 生成 CSV 任务列表")
    parser.add_argument("--harness", required=True, help="harness 名 (逗号分隔或 'all')")
    parser.add_argument("--class", dest="cls", required=True, help="类别 (逗号分隔或 'all')")
    args = parser.parse_args()

    harnesses = parse_list(args.harness, ALL_HARNESSES)
    classes = parse_list(args.cls, ALL_CLASSES)

    data = json.loads(FIX_RATES_PATH.read_text(encoding="utf-8"))
    categories = data["overall"]["categories"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for harness in harnesses:
        for cls in classes:
            cat_data = categories.get(cls)
            if not cat_data:
                print(f"[跳过] 类别 {cls} 不存在")
                continue
            harness_data = cat_data["by_harness"].get(harness)
            if not harness_data:
                print(f"[跳过] {harness}×{cls} 不存在")
                continue

            tasks = harness_data["not_run_tasks"]
            if not tasks:
                print(f"[空] {harness}×{cls}: 0 个任务")
                continue

            output_path = OUTPUT_DIR / f"{harness}_{cls}.csv"
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["bench_id", "task_id"])
                for task in tasks:
                    if ":" in task:
                        bench_id, task_id = task.split(":", 1)
                    else:
                        bench_id, task_id = "", task
                    writer.writerow([bench_id, task_id])

            print(f"[生成] {output_path.relative_to(PROJECT_ROOT)}: {len(tasks)} 个任务")


if __name__ == "__main__":
    main()


# python error_analysis/extract_not_run.py --harness control --class A
# python error_analysis/extract_not_run.py --harness control --class D