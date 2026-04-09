#!/usr/bin/env bash
#=============================================================================
# ClawEvalKit — 并行启动所有模型评测
#=============================================================================
#
# 用法:
#   cd ClawEvalKit && bash examples/run_all.sh
#
# 每个模型在后台并行运行, 日志分别写入 assets/log/eval_{model}.log
# 所有模型跑完后打印汇总表格.
#
# ================================ 并行架构 ================================
#
#   run_all.sh
#     ├── run_seed18.sh        &  (后台, 日志 → eval_seed-1.8.log)
#     ├── run_gemini_flash.sh  &  (后台, 日志 → eval_gemini-2.5-flash.log)
#     ├── run_minimax.sh       &  (后台, 日志 → eval_minimax-m2.7.log)
#     └── wait                    (等待全部完成)
#         └── python3 run.py --summary  (汇总)
#
#=============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

mkdir -p assets/log

echo "============================================"
echo "  ClawEvalKit: Parallel Evaluation"
echo "============================================"
echo ""

PIDS=()

for script in \
    "$SCRIPT_DIR/run_seed18.sh" \
    "$SCRIPT_DIR/run_gemini_flash.sh" \
    "$SCRIPT_DIR/run_minimax.sh" \
; do
    name="$(basename "$script" .sh)"
    if [ -f "$script" ]; then
        echo "  Starting: $name (background)"
        bash "$script" > /dev/null 2>&1 &
        PIDS+=($!)
    fi
done

echo ""
echo "  ${#PIDS[@]} models running in parallel..."
echo "  Logs: assets/log/eval_*.log"
echo ""

# 等待所有后台进程完成
FAIL=0
for pid in "${PIDS[@]}"; do
    wait "$pid" || ((FAIL++))
done

echo "============================================"
echo "  All done. Failures: $FAIL/${#PIDS[@]}"
echo "============================================"
echo ""

python3 run.py --summary
