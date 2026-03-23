#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

python3 << PYEOF
import json
import bisect

workspace = "$WORKSPACE"

with open(f"{workspace}/input.json") as f:
    data = json.load(f)

arr = data["array"]
n = len(arr)

tails = []
tail_indices = []
predecessors = [-1] * n

for i, val in enumerate(arr):
    pos = bisect.bisect_left(tails, val)
    if pos == len(tails):
        tails.append(val)
        tail_indices.append(i)
    else:
        tails[pos] = val
        tail_indices[pos] = i
    if pos > 0:
        predecessors[i] = tail_indices[pos - 1]

lis_length = len(tails)
subsequence = []
idx = tail_indices[lis_length - 1]
while idx != -1:
    subsequence.append(arr[idx])
    idx = predecessors[idx]
subsequence.reverse()

solution = {
    "length": lis_length,
    "subsequence": subsequence,
}

with open(f"{workspace}/solution.json", "w") as f:
    json.dump(solution, f, indent=2)

algorithm_code = '''import json
import bisect
import sys
import os

ws = os.path.dirname(os.path.abspath(__file__)) if not sys.argv[1:] else sys.argv[1]

with open(os.path.join(ws, "input.json")) as f:
    data = json.load(f)

arr = data["array"]
n = len(arr)

tails = []
tail_indices = []
predecessors = [-1] * n

for i, val in enumerate(arr):
    pos = bisect.bisect_left(tails, val)
    if pos == len(tails):
        tails.append(val)
        tail_indices.append(i)
    else:
        tails[pos] = val
        tail_indices[pos] = i
    if pos > 0:
        predecessors[i] = tail_indices[pos - 1]

lis_length = len(tails)
subsequence = []
idx = tail_indices[lis_length - 1]
while idx != -1:
    subsequence.append(arr[idx])
    idx = predecessors[idx]
subsequence.reverse()

result = {"length": lis_length, "subsequence": subsequence}

with open(os.path.join(ws, "solution.json"), "w") as f:
    json.dump(result, f, indent=2)

print(f"LIS length: {lis_length}")
print(f"Subsequence: {subsequence}")
'''

with open(f"{workspace}/algorithm.py", "w") as f:
    f.write(algorithm_code)

print(f"LIS length: {lis_length}")
print(f"Subsequence: {subsequence}")
PYEOF
