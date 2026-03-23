# Claude Code Baseline for Materials Science and Chemistry Benchmark

This directory contains the Claude Code agent baseline implementation for automated benchmark evaluation with complete isolation.

## Prerequisites

This baseline uses large binary files managed by Git LFS. Before cloning, install Git LFS:

```bash
# Install Git LFS (one-time setup)
git lfs install

# Then clone the repository
git clone <this-repo-url>
```

Without Git LFS, you will not be able to download the large files required for Docker build.

## Features

- **Complete Isolation**: Agent runs in ephemeral Docker containers with tmpfs (no persistent storage)
- **Security**: Agent cannot access benchmark answers or previous results
- **Parallel Execution**: Supports running multiple questions concurrently
- **Integrated Logging**: All agent outputs are consolidated into detailed log files
- **Optional Tracing**: Detailed execution traces showing all messages, tool calls, and errors for debugging

## Setup

### 1. Build the Docker Image

```bash
docker compose build
```

This will build the complete Docker environment with all required dependencies:
- Python packages (pymatgen, ASE, RDKit, etc.)
- Node.js and Claude Code CLI
- Computational tools: XTB, LAMMPS (both CLI and Python API), enumlib, ORCA

**Note:** Two Dockerfiles are provided:
- `Dockerfile` - Complete environment with all tools (used by default)
- `Dockerfile.only_python_package` - Python packages only, without XTB/LAMMPS/enumlib

### 1.1 ORCA Setup (Required for Quantum Chemistry Benchmarks)

ORCA is a quantum chemistry software package (20GB) required for certain benchmarks. Due to its large size, it's not included in the git repository.

**Setup Instructions:**

1. **Obtain ORCA 6.1.0**: Download from [ORCA website](https://www.faccts.de/orca/) or copy from your existing installation:
   ```bash
   # If you have ORCA already installed elsewhere:
   cp -r /path/to/your/orca_6_1_0 ./orca_6_1_0
   ```

2. **Place in the correct location**: The directory structure should be:
   ```
   deep_solver_benchmark/baselines/claude_code/
   ├── orca_6_1_0/          ← ORCA software directory
   │   ├── orca             ← Main executable
   │   ├── orca_*           ← Other executables
   │   └── ...
   ├── Dockerfile
   └── ...
   ```

3. **Verify**: Check that ORCA executable exists:
   ```bash
   ls -lh orca_6_1_0/orca
   ```

4. **Build Docker**: The Dockerfile will automatically:
   - Copy ORCA to `/opt/orca` inside the container
   - Create a symlink at `/usr/local/bin/orca` for easy access
   - Update PATH so `orca` command is directly available

**Note**:
- The `orca_6_1_0/` directory is excluded from git via `.gitignore`
- You don't need to manually create any symlinks - the Dockerfile handles all configuration automatically
- If you skip ORCA setup, ORCA benchmarks will fail, but all other benchmarks will work normally

### 2. (Optional) Setup MongoDB for pymatgen-db Benchmarks

Most benchmarks run fully inside Docker. However, pymatgen-db benchmarks require MongoDB running on the host machine, which Docker accesses via `--network=host`.

See [MongoDB setup instructions](../../DEVELOPMENT.md) for configuration details before running pymatgen-db benchmarks.

### 3. Set Environment Variables

Add these to your `~/.bashrc` file:

```bash
export MP_API_KEY="your_materials_project_api_key"
export ANTHROPIC_API_KEY="your_anthropic_api_key"
```

After adding, reload the environment:

```bash
source ~/.bashrc
```

## Usage

### Option 1: Test Single Question

Use this for quick testing a specific question:

```bash
./run_isolated_test.sh <benchmark_file> <question_index> <query_level> <model> <repetition> <create_agent_log> <results_file> <enable_tracing> <trace_dir>
```

**Parameters:**
- `benchmark_file`: Path to benchmark JSON file
- `question_index`: Question index (0-based)
- `query_level`: Query difficulty level (0 or 1)
- `model`: Claude model name (default: `claude-sonnet-4-5`)
- `repetition`: Repetition number (default: 1)
- `create_agent_log`: Create separate agent log file - `true` or `false` (default: `true`)
- `results_file`: Results file path (optional, default: auto-generated)
- `enable_tracing`: Enable detailed tracing - `true` or `false` (default: `false`)
- `trace_dir`: Tracing directory (default: `test_tracing`)

**Example (Basic):**
```bash
./run_isolated_test.sh \
  ../../../benchmark_tasks_and_results/questions_and_answers/data/data_processing/rdkit.json \
  0 \
  1 \
  claude-sonnet-4-5 \
  1
```

**Example (With Tracing):**
```bash
./run_isolated_test.sh \
  ../../../benchmark_tasks_and_results/questions_and_answers/data/data_processing/rdkit.json \
  0 \
  1 \
  claude-sonnet-4-5 \
  1 \
  true \
  "" \
  true \
  test_tracing
```

**Output:**
- Results: `test_results/results_rdkit_q0_level1_rep1_timestamp.json`
- Agent log: `agent_logs/agent_rdkit_q0_level1_rep1_timestamp.log`
- Trace log (if enabled): `test_tracing/trace_rdkit_q0_level1_rep1_timestamp.log`

---

### Option 2: Run Single Benchmark File (All Questions)

Use this to run all questions from one benchmark file:

```bash
python3 run_claude_code_benchmark.py \
  --benchmark <path_to_benchmark.json> \
  --repeat <num_repetitions> \
  --results-file <output_file.json> \
  --model <claude_model> \
  --parallel <num_workers> \
  [--enable-tracing] \
  [--trace-dir <trace_directory>] \
  [--detail-log-dir <log_directory>]
```

**Parameters:**
- `--benchmark`: Path to benchmark JSON file (required)
- `--repeat`: Number of repetitions per question (default: 3)
- `--results-file`: Output results file path (required)
- `--model`: Claude model name (default: `claude-sonnet-4-5`)
- `--parallel`: Number of parallel workers (0 = sequential, default: 0)
- `--enable-tracing`: Enable detailed tracing (optional flag)
- `--trace-dir`: Directory to save trace files (default: `test_tracing/trace_<timestamp>`)
- `--detail-log-dir`: Directory to save detailed log files (default: same as results file)

**Example (Sequential):**
```bash
python3 run_claude_code_benchmark.py \
  --benchmark ../../../benchmark_tasks_and_results/questions_and_answers/data/data_processing/rdkit.json \
  --repeat 3 \
  --results-file test_results/results_timestamp/results_rdkit.json \
  --model claude-sonnet-4-5
```

**Example (Parallel with 4 workers):**
```bash
python3 run_claude_code_benchmark.py \
  --benchmark ../../../benchmark_tasks_and_results/questions_and_answers/data/data_processing/rdkit.json \
  --repeat 3 \
  --results-file test_results/results_timestamp/results_rdkit.json \
  --model claude-sonnet-4-5 \
  --parallel 4
```

**Example (With Tracing Enabled):**
```bash
python3 run_claude_code_benchmark.py \
  --benchmark ../../../benchmark_tasks_and_results/questions_and_answers/data/data_processing/rdkit.json \
  --repeat 3 \
  --results-file test_results/results_timestamp/results_rdkit.json \
  --model claude-sonnet-4-5 \
  --parallel 4 \
  --enable-tracing \
  --trace-dir test_tracing/trace_timestamp
```

**Output:**
- Results: `test_results/results_timestamp/results_rdkit.json`
- Detailed log (default): `test_results/results_timestamp/results_rdkit_detail.log`
- Detailed log (if `--detail-log-dir <dir>` specified): `<dir>/results_rdkit_detail.log`
- Trace files (if `--enable-tracing`): `test_tracing/trace_timestamp/trace_rdkit_q*_level*_rep*_timestamp.log`

---

### Option 3: Run All Benchmarks (Complete Evaluation Suite)

Use this to run the complete benchmark suite with all benchmark files:

```bash
./run_benchmark_claude_code.sh [num_parallel_workers] [enable_tracing]
```

**Parameters:**
- `num_parallel_workers`: Number of parallel workers per benchmark (default: 4)
- `enable_tracing`: Enable detailed tracing - `true` or `false` (default: `false`)

**Example (Foreground):**
```bash
./run_benchmark_claude_code.sh 4
```

**Example (Background with nohup):**
```bash
nohup ./run_benchmark_claude_code.sh 4 > benchmark_output.log 2>&1 &
```

**Example (With Tracing Enabled):**
```bash
nohup ./run_benchmark_claude_code.sh 4 true > benchmark_output.log 2>&1 &
```

Monitor progress:
```bash
tail -f benchmark_output.log
```

**What it does:**
- Runs all benchmark files
- 3 repetitions per question
- 4 parallel workers per benchmark (configurable)
- Creates timestamp-based results directory
- Consolidates all logs
- Optionally generates detailed trace files

**Output Structure:**
```
test_results/results_timestamp/
├── results_materials_project.json
├── results_pymatgen_data_processing.json
├── results_ase.json
└── ... (one JSON file per benchmark)

test_log/log_timestamp/
├── benchmark_run.log                          ← Main log with progress
├── results_materials_project_detail.log       ← Detailed agent outputs
├── results_pymatgen_data_processing_detail.log
├── results_ase_detail.log
└── ... (one detail log per benchmark)

test_tracing/trace_timestamp/                  ← Tracing output (if enabled)
├── trace_materials_project_q0_level0_rep1_timestamp.log
├── trace_materials_project_q0_level0_rep2_timestamp.log
├── trace_materials_project_q0_level1_rep1_timestamp.log
└── ... (one trace file per question/level/repetition)
```

**Note:**
- `timestamp` format is `YYYYMMDD_HHMMSS`
- Trace files contain detailed execution logs including all messages, tool calls, and errors
- Tracing is useful for debugging but generates large amounts of data

---

## Understanding Tracing Output

When tracing is enabled, each question execution generates a detailed trace log file that includes:

### Trace File Contents

Each trace file (`trace_<benchmark>_q<index>_level<level>_rep<repetition>_<timestamp>.log`) contains:

**1. Summary Information:**
- Question text
- Processed output (final answer extracted from agent)
- Execution time in seconds
- Total messages exchanged

**2. Detailed Message Log:**
For each message in the conversation:
- **Message Number** and **Type** (UserMessage, AssistantMessage, ToolResultMessage, etc.)
- **Content**: The actual message text or data
- **Tool Name** (if message involves tool use)
- **Tool Input** (parameters passed to the tool)
- **Tool Output** (result from tool execution)
- **Error Information** (if tool execution failed)