#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="${1:-$TASK_DIR/workspace}"
mkdir -p "$WORKSPACE"
cp "$TASK_DIR/environment/data/.env.example" "$WORKSPACE/.env.example"
cp "$TASK_DIR/environment/data/config_spec.json" "$WORKSPACE/config_spec.json"
echo "Workspace ready with .env.example and config_spec.json"
