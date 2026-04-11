#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

python3 << PYEOF
import csv
import json
import math

groups = {"A": [], "B": []}
with open("$WORKSPACE/dataset.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        groups[row["group"]].append(float(row["value"]))

def mean(xs):
    return sum(xs) / len(xs)

def std_sample(xs):
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

a, b = groups["A"], groups["B"]
mean_a, mean_b = mean(a), mean(b)
std_a, std_b = std_sample(a), std_sample(b)
n_a, n_b = len(a), len(b)

se = math.sqrt(std_a**2 / n_a + std_b**2 / n_b)
t_stat = (mean_a - mean_b) / se

nu_num = (std_a**2 / n_a + std_b**2 / n_b) ** 2
nu_den = (std_a**2 / n_a) ** 2 / (n_a - 1) + (std_b**2 / n_b) ** 2 / (n_b - 1)
df = nu_num / nu_den

from scipy import stats as scipy_stats
p_value = 2 * scipy_stats.t.sf(abs(t_stat), df)

conclusion = "significant" if p_value < 0.05 else "not_significant"

analysis = {
    "mean_a": round(mean_a, 4),
    "mean_b": round(mean_b, 4),
    "std_a": round(std_a, 4),
    "std_b": round(std_b, 4),
    "t_statistic": round(t_stat, 4),
    "p_value": round(p_value, 10),
    "conclusion": conclusion,
}

with open("$WORKSPACE/analysis.json", "w") as f:
    json.dump(analysis, f, indent=2)

print(json.dumps(analysis, indent=2))
PYEOF
