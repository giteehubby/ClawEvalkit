#!/usr/bin/env bash
#=============================================================================
# ClawEvalKit — Gemini 2.5 Flash × 全部 Benchmark
#=============================================================================
#
# 用法:
#   cd ClawEvalKit && bash examples/run_gemini_flash.sh
#
# 前置条件:
#   1. pip install -e .
#   2. .env 中配置了 OPENROUTER_API_KEY
#   3. configs/models/openrouter.yaml 中有 gemini-2.5-flash 定义
#
# ================================ 代码流程 ================================
#
# run.py --model gemini-2.5-flash --force
#   → 对 8 个 benchmark 依次调用 infer_data_job("bench", "gemini-2.5-flash")
#   → NanoBotAgent(model="google/gemini-2.5-flash",
#                   api_url="https://openrouter.ai/api/v1",
#                   api_key=OPENROUTER_API_KEY)
#   → _call_llm() 检测 "openrouter" in api_url
#     → litellm 前缀 "openrouter/google/gemini-2.5-flash"
#
# ================================ 输出结果 ================================
#
# 已验证 (2026-04-02):
#   Tribe: 100.0 (8/8)
#   其他 benchmark 待跑
#
# 结果文件: outputs/{benchmark}/gemini-2.5-flash.json
#
#=============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="gemini-2.5-flash"
LOG="assets/log/eval_${MODEL}.log"
mkdir -p assets/log

echo "=== ClawEvalKit: All Benchmarks × ${MODEL} ==="
python3 run.py --model "$MODEL" --force 2>&1 | tee "$LOG"
echo "日志: $LOG"
