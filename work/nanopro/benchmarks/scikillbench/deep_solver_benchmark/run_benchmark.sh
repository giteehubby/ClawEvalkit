#!/bin/bash

# Always run from the deep_solver_benchmark directory
cd "$(dirname "$0")"

# Get project root (parent of deep_solver_benchmark)
PROJECT_ROOT="$(dirname "$(pwd)")"
BENCHMARK_DATA="$PROJECT_ROOT/benchmark_tasks_and_results"

RESULTS_DIR="$BENCHMARK_DATA/test_results"
LOG_DIR="$BENCHMARK_DATA/test_log"
mkdir -p "$RESULTS_DIR"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SAVE_DIR="$RESULTS_DIR/results_${TIMESTAMP}"
mkdir -p "$SAVE_DIR"

LOG_FILE="$LOG_DIR/test_workflow_${TIMESTAMP}.log"

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

  # Data Analysis Benchmarks
  "questions_and_answers/data/data_analysis/pymatgen_data_analysis.json"
)

for BENCH in "${BENCHMARKS[@]}"; do
  BENCH_NAME=$(basename "$BENCH" .json)
  echo "Running benchmark: $BENCH_NAME"
  python -u test_workflow.py \
    --benchmark "$BENCHMARK_DATA/$BENCH" \
    --repeat 3 \
    --results-file "$SAVE_DIR/results_${BENCH_NAME}.json"
done > "$LOG_FILE" 2>&1

echo "All runs finished. Results are in $SAVE_DIR, log in $LOG_FILE"
