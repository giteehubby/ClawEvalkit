#!/usr/bin/env bash
# quickstart.sh — Get up and running with Claw Bench in under 60 seconds.
#
# Usage:
#   curl -fsSL https://clawbench.net/quickstart.sh | bash
#   # or locally:
#   bash scripts/quickstart.sh
set -euo pipefail

cat << 'BANNER'

   ██████╗██╗      █████╗ ██╗    ██╗    ██████╗ ███████╗███╗   ██╗ ██████╗██╗  ██╗
  ██╔════╝██║     ██╔══██╗██║    ██║    ██╔══██╗██╔════╝████╗  ██║██╔════╝██║  ██║
  ██║     ██║     ███████║██║ █╗ ██║    ██████╔╝█████╗  ██╔██╗ ██║██║     ███████║
  ██║     ██║     ██╔══██║██║███╗██║    ██╔══██╗██╔══╝  ██║╚██╗██║██║     ██╔══██║
  ╚██████╗███████╗██║  ██║╚███╔███╔╝    ██████╔╝███████╗██║ ╚████║╚██████╗██║  ██║
   ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝     ╚═════╝ ╚══════╝╚═╝  ╚═══╝ ╚═════╝╚═╝  ╚═╝
  AI Agent Evaluation Benchmark — 210 tasks · 14 domains · L1–L4

BANNER

echo "==> [1/3] Installing claw-bench..."
pip install -e ".[dev]" --quiet 2>/dev/null || pip install claw-bench --quiet
echo "    ✓ Installed"

echo ""
echo "==> [2/3] Health check..."
claw-bench doctor
echo ""

echo "==> [3/3] Ready!"
echo ""

cat << 'USAGE'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Quick Reference
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  # Your AI agent reads the skill file and runs the benchmark:
  Read https://clawbench.net/skill.md and follow the instructions.

  # Browse available tasks
  claw-bench list tasks

  # Validate task integrity
  claw-bench validate

  # Diagnose issues
  claw-bench doctor

  # Submit results to leaderboard
  claw-bench submit ./results/latest

  Docs: https://clawbench.net/skill.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE
