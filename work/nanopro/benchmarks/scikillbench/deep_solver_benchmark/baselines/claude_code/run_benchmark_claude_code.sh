#!/bin/bash

# Claude Code Baseline Benchmark Runner
# Runs multiple benchmark files with complete isolation (like run_benchmark.sh)

# Always run from the claude_code baseline directory
cd "$(dirname "$0")"

RESULTS_DIR="test_results"
LOG_DIR="test_log"
mkdir -p "$RESULTS_DIR"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SAVE_DIR="$RESULTS_DIR/results_${TIMESTAMP}"
mkdir -p "$SAVE_DIR"

LOG_SUBDIR="$LOG_DIR/log_${TIMESTAMP}"
mkdir -p "$LOG_SUBDIR"
LOG_FILE="$LOG_SUBDIR/benchmark_run.log"

# Benchmark files
BENCHMARKS=(
  # Data Management Benchmarks
  "questions_and_answers/data/data_management/pymatgen-db.json"

  # Data Retrieval Benchmarks
  "questions_and_answers/data/data_retrieval/matminer_data_retrieval.json"
  "questions_and_answers/data/data_retrieval/mpcontribs.json"
  "questions_and_answers/data/data_retrieval/materials_project.json"
  "questions_and_answers/data/data_retrieval/datasets_from_paper.json"

  # Data Processing Benchmarks
  "questions_and_answers/data/data_processing/rdkit.json"
  "questions_and_answers/data/data_processing/matminer_data_processing.json"
  "questions_and_answers/data/data_processing/robocrystallographer.json"
  "questions_and_answers/data/data_processing/pymatgen_data_processing.json"

  # Computation Benchmarks
  "questions_and_answers/computation/simulation/xtb.json"
  "questions_and_answers/computation/simulation/ase.json"
  "questions_and_answers/computation/simulation/md.json"
  "questions_and_answers/computation/simulation/orca.json"
  "questions_and_answers/computation/specialized_models_and_toolkits/mlip.json"

  # # Data Analysis Benchmarks
  "questions_and_answers/data/data_analysis/pymatgen_data_analysis.json"
)

PARALLEL_WORKERS="${1:-4}"  # Number of parallel workers per benchmark (default: 4)
ENABLE_TRACING="${2:-false}"  # Enable tracing (default: false, use "true" to enable)

# Create tracing directory if enabled
if [ "$ENABLE_TRACING" = "true" ]; then
  TRACE_DIR="test_tracing/trace_${TIMESTAMP}"
  mkdir -p "$TRACE_DIR"
fi

echo "=========================================="
echo "Claude Code Baseline Benchmark Runner"
echo "=========================================="
echo "Results directory: $SAVE_DIR"
echo "Log file: $LOG_FILE"
echo "Total benchmarks: ${#BENCHMARKS[@]}"
echo "Repetitions per question: 3"
echo "Parallel workers per benchmark: $PARALLEL_WORKERS"
if [ "$ENABLE_TRACING" = "true" ]; then
  echo "Tracing: Enabled ($TRACE_DIR)"
fi
echo "=========================================="
echo ""
echo "📝 All output will be logged to: $LOG_FILE"
echo "💡 You can monitor progress with: tail -f $LOG_FILE"
echo ""

{
  for BENCH in "${BENCHMARKS[@]}"; do
    BENCH_FULL_PATH="../../../benchmark_tasks_and_results/$BENCH"
    BENCH_NAME=$(basename "$BENCH" .json)

    echo ""
    echo "=========================================="
    echo "Running benchmark: $BENCH_NAME"
    echo "File: $BENCH"
    echo "=========================================="

    # Run the benchmark using the Claude Code runner script with parallel workers
    if [ "$ENABLE_TRACING" = "true" ]; then
      python3 run_claude_code_benchmark.py \
        --benchmark "$BENCH_FULL_PATH" \
        --repeat 3 \
        --results-file "$SAVE_DIR/results_${BENCH_NAME}.json" \
        --detail-log-dir "$LOG_SUBDIR" \
        --model "claude-sonnet-4-5" \
        --parallel "$PARALLEL_WORKERS" \
        --enable-tracing \
        --trace-dir "$TRACE_DIR"
    else
      python3 run_claude_code_benchmark.py \
        --benchmark "$BENCH_FULL_PATH" \
        --repeat 3 \
        --results-file "$SAVE_DIR/results_${BENCH_NAME}.json" \
        --detail-log-dir "$LOG_SUBDIR" \
        --model "claude-sonnet-4-5" \
        --parallel "$PARALLEL_WORKERS"
    fi

    if [ $? -eq 0 ]; then
      echo "✅ Benchmark $BENCH_NAME completed successfully"
    else
      echo "❌ Benchmark $BENCH_NAME failed"
    fi
  done

  echo ""
  echo "=========================================="
  echo "All benchmarks completed!"
  echo "=========================================="
  echo "Results saved to: $SAVE_DIR"
  echo "Log saved to: $LOG_FILE"

} >> "$LOG_FILE" 2>&1
