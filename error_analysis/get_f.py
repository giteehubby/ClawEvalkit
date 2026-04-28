#!/usr/bin/env python3
"""从 failure_categories_by_group.json 提取 F 类错误，保存为 CSV"""

import json
import csv
from pathlib import Path

def main():
    json_path = Path(__file__).parent / "outputs" / "failure_categories_by_group.json"
    csv_path = Path(__file__).parent / "inputs" / "F.csv"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    f_tasks = data.get("by_category", {}).get("F", [])

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["bench_id", "task_id"])
        for item in f_tasks:
            writer.writerow([item["bench"], item["task_id"]])

    print(f"已提取 {len(f_tasks)} 个 F 类任务到 {csv_path}")

if __name__ == "__main__":
    main()


'''
python error_analysis/get_f.py
'''