"""从 fix_rates.json 提取指定类别+Harness的 unfixed_tasks，保存为 CSV"""

import argparse
import csv
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FIX_RATES_PATH = SCRIPT_DIR / "outputs" / "fix_rates.json"
OUTPUT_DIR = SCRIPT_DIR / "inputs"


def main():
    parser = argparse.ArgumentParser(description="提取 unfixed_tasks 为 CSV")
    parser.add_argument("category", help="错误类别字母，如 A/B/C/D/E/F")
    parser.add_argument("harness", help="harness 名称，如 control/memory/collaboration/procedure")
    args = parser.parse_args()

    category = args.category.upper()
    harness = args.harness.lower()

    with open(FIX_RATES_PATH) as f:
        data = json.load(f)

    categories = data["overall"]["categories"]
    if category not in categories:
        print(f"错误：类别 {category} 不存在，可选：{list(categories.keys())}")
        return

    by_harness = categories[category]["by_harness"]
    if harness not in by_harness:
        print(f"错误：harness '{harness}' 不存在，可选：{list(by_harness.keys())}")
        return

    unfixed = by_harness[harness]["unfixed_tasks"]
    if not unfixed:
        print(f"类别 {category} + harness {harness} 没有 unfixed_tasks")
        return

    # 解析 bench_id:task_id
    rows = []
    for entry in unfixed:
        parts = entry.split(":", 1)
        if len(parts) == 2:
            rows.append(parts)
        else:
            print(f"警告：跳过格式异常的条目 '{entry}'")

    # 输出路径：{harness}_{category}.csv，如 control_A.csv
    output_path = OUTPUT_DIR / f"{harness}_{category}.csv"
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["bench_id", "task_id"])
        writer.writerows(rows)

    print(f"已保存 {len(rows)} 条记录到 {output_path}")


if __name__ == "__main__":
    main()

# python error_analysis/extract_unfixed_task.py A control
# python error_analysis/extract_unfixed_task.py B control
# python error_analysis/extract_unfixed_task.py D control