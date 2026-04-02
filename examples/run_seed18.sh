#!/usr/bin/env bash
#=============================================================================
# ClawEvalKit — Seed 1.8 × 全部 Benchmark
#=============================================================================
#
# 用法:
#   cd ClawEvalKit && bash examples/run_seed18.sh
#
# 前置条件:
#   1. pip install -e .
#   2. .env 中配置了 ARK_API_KEY
#   3. configs/models/seed.yaml 中有 seed-1.8 定义
#
# ================================ 代码流程 ================================
#
# run.py --model seed-1.8 --force
#   → 对 8 个 benchmark 依次调用 infer_data_job("bench", "seed-1.8")
#   → 每个 benchmark 内部:
#     1) import_nanobot_agent() 加载 NanoBotAgent
#     2) NanoBotAgent(model="ep-20260116160300-kq8ft",
#                     api_url="https://ark-cn-beijing.bytedance.net/api/v3",
#                     api_key=ARK_API_KEY)
#     3) _call_llm() 检测 api_url 非 openrouter/anthropic/azure
#        → litellm 前缀 "openai/ep-20260116160300-kq8ft"
#     4) agent.execute(prompt) → 评分 → save_result()
#   → summarizer 打印汇总表格
#
# ================================ 输出结果 ================================
#
# 已验证 (2026-04-01):
#   Tribe: 100.0 (8/8)
#   其他 benchmark 待跑
#
# 结果文件: outputs/{benchmark}/seed-1.8.json
#
#=============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="seed-1.8"
LOG="assets/log/eval_${MODEL}.log"
mkdir -p assets/log

echo "=== ClawEvalKit: All Benchmarks × ${MODEL} ==="
python3 run.py --model "$MODEL" --force 2>&1 | tee "$LOG"
echo "日志: $LOG"
