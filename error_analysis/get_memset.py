"""
从 C 类错误和 memory benchmark 提取 task，保存为 CSV
"""
import json
import csv
from pathlib import Path

# 输入路径
failure_json = Path("error_analysis/outputs/failure_categories_by_group.json")
memory_dir = Path("benchmarks/claw-bench/tasks/memory")
output_csv = Path("error_analysis/inputs/memset.csv")

# 1. 提取 C 类错误的 task_id
with open(failure_json, "r") as f:
    data = json.load(f)

c_tasks = data.get("by_category", {}).get("C", [])
print(f"C 类错误数量: {len(c_tasks)}")

# 2. 获取 memory 下的所有 task (子目录名即 task_id)
memory_tasks = []
for f in sorted(memory_dir.glob("*")):
    if f.is_dir() and not f.name.startswith("."):
        memory_tasks.append({"bench": "clawbench", "task_id": f.name})

print(f"Memory 任务数量: {len(memory_tasks)}")

# 3. 合并并去重 (按 bench, task_id)
seen = set()
merged = []
for t in c_tasks + memory_tasks:
    key = (t["bench"], t["task_id"])
    if key not in seen:
        seen.add(key)
        merged.append(t)

print(f"合并后总数: {len(merged)}")

# 4. 保存为 CSV
output_csv.parent.mkdir(parents=True, exist_ok=True)
with open(output_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["bench_id", "task_id"])
    writer.writeheader()
    for t in merged:
        writer.writerow({"bench_id": t["bench"], "task_id": t["task_id"]})

print(f"已保存至 {output_csv}")


'''
python error_analysis/get_memset.py && cat error_analysis/inputs/memset.csv
'''