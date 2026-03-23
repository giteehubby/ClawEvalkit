#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="${1:-$TASK_DIR/workspace}"
mkdir -p "$WORKSPACE"
cp "$TASK_DIR/environment/data/old_schema.sql" "$WORKSPACE/old_schema.sql"
cp "$TASK_DIR/environment/data/new_schema.sql" "$WORKSPACE/new_schema.sql"
echo "Workspace ready with old_schema.sql and new_schema.sql"
