#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

python3 << PYEOF
import json
import re
from collections import defaultdict

def parse_requirements(filepath):
    """Parse a requirements file into a dict of {package: version_spec}."""
    pkgs = {}
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r'^([a-zA-Z0-9_-]+)(.*)', line)
            if match:
                name = match.group(1).lower()
                spec = match.group(2).strip()
                pkgs[name] = spec
    return pkgs

reqs_a = parse_requirements("$WORKSPACE/requirements_a.txt")
reqs_b = parse_requirements("$WORKSPACE/requirements_b.txt")

all_packages = sorted(set(list(reqs_a.keys()) + list(reqs_b.keys())))

conflicts = []
resolved = {}

for pkg in all_packages:
    spec_a = reqs_a.get(pkg)
    spec_b = reqs_b.get(pkg)

    if spec_a and spec_b:
        if spec_a == spec_b:
            resolved[pkg] = spec_a
        else:
            conflicts.append({
                "package": pkg,
                "version_a": spec_a,
                "version_b": spec_b,
                "resolution": ""
            })
            if "==" in spec_b:
                resolved[pkg] = spec_b
                conflicts[-1]["resolution"] = spec_b
            elif "==" in spec_a:
                resolved[pkg] = spec_a
                conflicts[-1]["resolution"] = spec_a
            elif "<" in spec_b and ">=" in spec_a:
                resolved[pkg] = spec_a
                conflicts[-1]["resolution"] = spec_a
            elif "<" in spec_a and ">=" in spec_b:
                resolved[pkg] = spec_b
                conflicts[-1]["resolution"] = spec_b
            else:
                resolved[pkg] = spec_b
                conflicts[-1]["resolution"] = spec_b
    elif spec_a:
        resolved[pkg] = spec_a
    else:
        resolved[pkg] = spec_b

with open("$WORKSPACE/resolved.txt", "w") as f:
    for pkg in sorted(resolved.keys()):
        f.write(f"{pkg}{resolved[pkg]}\n")

with open("$WORKSPACE/conflicts.json", "w") as f:
    json.dump(conflicts, f, indent=2)

print(f"Resolved {len(all_packages)} packages, found {len(conflicts)} conflicts")
PYEOF
echo "Created resolved.txt and conflicts.json in $WORKSPACE"
