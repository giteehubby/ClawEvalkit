#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker build -t skillbench/base:0.1.0 -f "$ROOT_DIR/docker/Dockerfile.base" "$ROOT_DIR"
