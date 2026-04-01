# Task: Git Operations Script

You are given a JSON file describing git operations to perform on a repository.

## Input Files

- `workspace/repo_instructions.json` — JSON file listing 3 git operations to perform

## Goal

Create a bash script that performs the specified git operations in order.

## Requirements

1. Read the operations from `workspace/repo_instructions.json`.
2. Create `workspace/git_commands.sh` — a valid bash script that contains the correct git commands.
3. The script must:
   - Start with a proper shebang line (`#!/bin/bash` or `#!/usr/bin/env bash`)
   - Use `set -euo pipefail` for safety
   - Contain the correct git command for each operation in order:
     - **Create branch**: use `git checkout -b <name>` or `git switch -c <name>`
     - **Commit**: use `git commit -m "<message>"` (you may add `git add .` before it)
     - **Create tag**: use `git tag <tag_name>`
   - Include helpful comments explaining each step

## Notes

- The script does not need to actually execute — it only needs to contain the correct commands.
- Make sure the commands are in the correct order as specified in the instructions.
- The script should be well-structured and readable.
