#!/bin/bash
# =============================================================================
# Build all ClawEvalKit Docker images
# =============================================================================
# Usage: ./docker/build.sh [tag]
#   tag: Image tag suffix (default: v1)
#
# This script builds:
#   - clawbase-nanobot:<tag>    : Base image for all NanoBotAgent benchmarks
#   - claw-eval-agent:latest     : ClawEval sandbox server (from benchmarks/claw-eval)
#
# Example:
#   ./docker/build.sh             # Build with default tag v1
#   ./docker/build.sh latest      # Build with tag latest
# =============================================================================

set -e

TAG="${1:-v1}"
BASE_IMAGE="clawbase-nanobot:${TAG}"

echo "============================================"
echo "Building ClawEvalKit Docker Images"
echo "Base image tag: ${TAG}"
echo "============================================"

# Build base image
echo ""
echo "[1/4] Building base image: ${BASE_IMAGE}"
docker build -f docker/Dockerfile.base -t "${BASE_IMAGE}" .
echo "Base image built successfully"

# Build pinchbench image
echo ""
echo "[2/4] Building pinchbench image: ${BASE_IMAGE}"
docker build -f docker/pinchbench/Dockerfile -t "${BASE_IMAGE}" .
echo "pinchbench image built successfully"

# Build agentbench image
echo ""
echo "[3/4] Building agentbench image: ${BASE_IMAGE}"
docker build -f docker/agentbench/Dockerfile -t "${BASE_IMAGE}" .
echo "agentbench image built successfully"

# Build clawbench image
echo ""
echo "[4/4] Building clawbench image: ${BASE_IMAGE}"
docker build -f docker/clawbench/Dockerfile -t "${BASE_IMAGE}" .
echo "clawbench image built successfully"

echo ""
echo "============================================"
echo "All NanoBotAgent images built: ${BASE_IMAGE}"
echo ""
echo "To build claweval image:"
echo "  docker build -f benchmarks/claw-eval/Dockerfile.agent -t claw-eval-agent:latest ."
echo "============================================"
