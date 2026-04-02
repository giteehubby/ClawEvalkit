#!/usr/bin/env bash
#=============================================================================
# ClawEvalKit — MiniMax M2.7 × 全部 Benchmark
#=============================================================================
#
# 用法:
#   cd ClawEvalKit && bash examples/run_minimax.sh
#
# 前置条件:
#   1. pip install -e .
#   2. .env 中配置了 MINIMAX_API_KEY
#   3. configs/models/minimax.yaml 中有 minimax-m2.7 定义
#
# ================================ 代码流程 ================================
#
# run.py --model minimax-m2.7 --force
#   → 对 8 个 benchmark 依次调用 infer_data_job("bench", "minimax-m2.7")
#   → NanoBotAgent(model="MiniMax-M2.7",
#                   api_url="https://api.minimaxi.com/anthropic",
#                   api_key=MINIMAX_API_KEY)
#   → _call_llm() 检测 "anthropic" in api_url
#     → litellm 前缀 "anthropic/MiniMax-M2.7"
#
# ================================ 输出结果 ================================
#
# 已验证 (2026-04-02):
#   Tribe: 100.0 (8/8)
#   其他 benchmark 待跑
#
# 结果文件: outputs/{benchmark}/minimax-m2.7.json
#
#=============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="minimax-m2.7"
LOG="assets/log/eval_${MODEL}.log"
mkdir -p assets/log

echo "=== ClawEvalKit: All Benchmarks × ${MODEL} ==="
python3 run.py --model "$MODEL" --force 2>&1 | tee "$LOG"
echo "日志: $LOG"
