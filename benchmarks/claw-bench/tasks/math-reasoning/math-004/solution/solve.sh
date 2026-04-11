#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

python3 << PYEOF
import json

with open("$WORKSPACE/problem.json") as f:
    data = json.load(f)

from scipy.optimize import linprog

products = data["products"]
limits = data["resource_limits"]
resource_names = list(limits.keys())

c = [-products["A"]["profit_per_unit"],
     -products["B"]["profit_per_unit"],
     -products["C"]["profit_per_unit"]]

A_ub = []
b_ub = []
for rname in resource_names:
    row = [
        products["A"]["resources"][rname],
        products["B"]["resources"][rname],
        products["C"]["resources"][rname],
    ]
    A_ub.append(row)
    b_ub.append(limits[rname])

bounds = [(0, None), (0, None), (0, None)]

result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

qa, qb, qc = result.x
total_profit = -result.fun

binding = []
for i, rname in enumerate(resource_names):
    usage = A_ub[i][0] * qa + A_ub[i][1] * qb + A_ub[i][2] * qc
    if abs(usage - b_ub[i]) < 1e-6:
        binding.append(rname)

solution = {
    "product_A": round(qa, 4),
    "product_B": round(qb, 4),
    "product_C": round(qc, 4),
    "total_profit": round(total_profit, 4),
    "binding_constraints": sorted(binding),
}

with open("$WORKSPACE/solution.json", "w") as f:
    json.dump(solution, f, indent=2)

print(json.dumps(solution, indent=2))
PYEOF
