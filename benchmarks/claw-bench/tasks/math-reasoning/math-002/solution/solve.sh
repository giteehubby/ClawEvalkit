#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

python3 << PYEOF
import json

with open("$WORKSPACE/items.json") as f:
    data = json.load(f)

items = data["items"]
capacity = data["capacity"]
n = len(items)

dp = [[0] * (capacity + 1) for _ in range(n + 1)]
for i in range(1, n + 1):
    w = items[i - 1]["weight"]
    v = items[i - 1]["value"]
    for c in range(capacity + 1):
        dp[i][c] = dp[i - 1][c]
        if w <= c and dp[i - 1][c - w] + v > dp[i][c]:
            dp[i][c] = dp[i - 1][c - w] + v

selected = []
c = capacity
for i in range(n, 0, -1):
    if dp[i][c] != dp[i - 1][c]:
        selected.append(items[i - 1]["name"])
        c -= items[i - 1]["weight"]

selected.reverse()
item_map = {it["name"]: it for it in items}
total_w = sum(item_map[name]["weight"] for name in selected)
total_v = sum(item_map[name]["value"] for name in selected)

solution = {
    "selected_items": selected,
    "total_value": total_v,
    "total_weight": total_w,
    "algorithm": "dynamic programming with backtracking to recover selected items",
}

with open("$WORKSPACE/solution.json", "w") as f:
    json.dump(solution, f, indent=2)

print(f"Selected {len(selected)} items: {selected}")
print(f"Total value: {total_v}, Total weight: {total_w}")
PYEOF
