# Task: Dependency Conflict Resolution

You are given two Python requirements files that have overlapping dependencies with conflicting version constraints.

## Input Files

- `workspace/requirements_a.txt` — First set of Python package requirements
- `workspace/requirements_b.txt` — Second set of Python package requirements

## Goal

Merge both requirements files, detect version conflicts, resolve them, and produce clean output files.

## Requirements

1. Read both `workspace/requirements_a.txt` and `workspace/requirements_b.txt`.
2. Identify all packages across both files.
3. Detect version conflicts (where the same package has incompatible version constraints).
4. Create `workspace/resolved.txt`:
   - Contains all unique packages with resolved version constraints
   - One package per line in standard pip format (e.g., `package==1.2.3` or `package>=1.0,<2.0`)
   - No duplicate packages
   - Sorted alphabetically by package name
5. Create `workspace/conflicts.json`:
   - A JSON array of detected conflicts
   - Each conflict object must have:
     - `package` — the package name (lowercase)
     - `version_a` — the version spec from requirements_a.txt
     - `version_b` — the version spec from requirements_b.txt
     - `resolution` — the resolved version spec chosen

## Conflict Resolution Strategy

- When constraints are incompatible, prefer the more specific/pinned version
- If one side pins exactly (==), prefer the pinned version if it doesn't violate a hard upper bound
- When truly incompatible, pick the higher version constraint
- All package names should be normalized to lowercase
