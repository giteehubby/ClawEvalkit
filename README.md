# ClawEvalKit

<p align="center">
  <strong>Unified evaluation framework for agent benchmarks</strong><br>
  One entry point, multiple benchmarks, any model.
</p>

---

ClawEvalKit is a unified evaluation toolkit for **agent benchmarks**. It follows [VLMEvalKit](https://github.com/open-compass/VLMEvalKit) conventions (single `run.py` entry, self-contained benchmark classes) with [OpenCompass](https://github.com/open-compass/opencompass)-style YAML model configs.

All benchmarks execute agents inside **Docker containers** for reproducibility and sandboxing.

## Features

- **Single command**: `python3 run.py --bench <bench> --model <model>` to evaluate any model on any benchmark
- **YAML-driven model configs**: Add new models by creating a single YAML file, no code changes needed
- **Docker sandboxing**: All benchmarks run in Docker containers for reproducibility and safety
- **Incremental caching**: Per-task result files with automatic resume after interruption
- **Parallel execution**: Run multiple tasks concurrently with `--parallel`
- **LLM Judge scoring**: Automated trajectory evaluation with configurable judge models

## Supported Benchmarks

| Key | Benchmark | Tasks | Scoring | Description |
|-----|-----------|------:|---------|-------------|
| `skillsbench` | SkillsBench | 56 | 0-100% | Multi-turn code generation + pytest, per-task Docker environment |
| `agentbench` | AgentBench-OpenClaw | 40 | 0-100 | L0 rule-based + L1 metric scoring |
| `clawbench-official` | ClawBench | 250 | 0-100 | NanoBotAgent execution + Pytest verification across multiple domains |
| `claweval` | ClawEval | 300 | 0-1 | Mock services + Docker sandbox + multi-dimension grader (completion, robustness, communication, safety) |
| `zclawbench` | ZClawBench | 116 | 0-1 | LLM Judge scoring across 4 dimensions |
| `pinchbench` | PinchBench | 23 | 0-100 | Rule-based file/content checks with embedded grading functions |
| `tribe` | Claw-Bench-Tribe | 8 | 0-100 | Pure LLM scoring without tool use |
| `skillbench` | SkillBench | 22 | 0-100% | Harness + pytest scoring |

## Installation

### Prerequisites

- **Python 3.9+**
- **Docker** (required for all benchmarks)
- **Git** (with submodules support)

### Steps

```bash
# 1. Clone the repository with submodules
git clone --recurse-submodules https://github.com/giteehubby/ClawEvalkit.git
cd ClawEvalkit

# 2. Install the package
pip install -e .

# 3. Set up your API key
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY (or any OpenAI-compatible API key)
```

## Docker Setup

All benchmarks require Docker for sandboxed task execution. You need to build the Docker images before running evaluations.

### Step 1: Build the NanoBotAgent image

This is the shared image used by `agentbench`, `clawbench-official`, `zclawbench`, `pinchbench`, and `tribe`:

```bash
# Option 1: Build all images with the convenience script
./docker/build.sh

# Option 2: Build only the base NanoBotAgent image
docker build -f docker/Dockerfile.base -t clawbase-nanobot:v1 .
```

> **Note**: The image is based on `ubuntu:24.04` and includes all NanoBotAgent dependencies. OpenClawPro is mounted at runtime via `-v /path/to/OpenClawPro:/root/OpenClawPro:rw`.

### Step 2: (For ClawEval) Build the ClawEval agent image

ClawEval uses its own Docker image for sandboxed task execution:

```bash
# Build from the claw-eval benchmark directory
docker build -f benchmarks/claw-eval/Dockerfile.agent -t claw-eval-agent:latest benchmarks/claw-eval/
```

### Step 3: (For SkillsBench) Build the base Python images

SkillsBench uses per-task Dockerfiles. Some tasks need pre-built Python 3.11 base images:

```bash
# Build the Python 3.11 base images (needed by some SkillsBench tasks)
docker build -f Dockerfile.skillsbench-base -t skillsbench-base:latest .
docker build -f Dockerfile.skillsbench-py311 -t skillsbench-py311:latest .
docker build -f Dockerfile.skillsbench-py311-ubuntu24 -t skillsbench-py311-ubuntu24:latest .
```

### Verify Docker setup

```bash
# Check that the images are built
docker images | grep -E "clawbase|skillsbench|claw-eval-agent"
```

## Quick Start

```bash
# List all available benchmarks and models
python3 run.py --list

# Run SkillsBench with Claude Sonnet (requires Docker)
python3 run.py --bench skillsbench --model claude-sonnet --docker

# Run AgentBench with parallel execution
python3 run.py --bench agentbench --model claude-sonnet --docker --parallel 4

# Run ClawBench (250 tasks, Docker mode)
python3 run.py --bench clawbench-official --model claude-sonnet --docker

# Run ClawEval (300 tasks, with mock services + Docker sandbox)
python3 run.py --bench claweval --model claude-sonnet --docker

# Run ZClawBench with LLM Judge scoring
python3 run.py --bench zclawbench --model claude-sonnet --docker

# Run PinchBench
python3 run.py --bench pinchbench --model claude-sonnet --docker

# Run multiple benchmarks in one command
python3 run.py --bench skillsbench,agentbench,clawbench-official --model claude-sonnet --docker

# Sample 5 tasks for quick testing
python3 run.py --bench clawbench-official --model claude-sonnet --docker --sample 5

# Run a specific task
python3 run.py --bench claweval --model claude-sonnet --docker --task task_id_here

# View summary of existing results
python3 run.py --summary
```

## CLI Reference

```
python3 run.py [OPTIONS]

Options:
  --bench, -b         Comma-separated benchmark keys (default: all)
  --model, -m         Comma-separated model keys (default: claude-sonnet)
  --sample, -s        Sample N tasks per benchmark (0=all)
  --docker            Use Docker containers for execution
  --parallel, -p      Number of parallel tasks in Docker mode (default: 1)
  --task, -t          Run a specific task by ID
  --category, -c      Run tasks from a specific category
  --max-turns         Max retry turns for SkillsBench multi-turn (default: 3)
  --force             Force re-evaluation (ignore cached results)
  --reuse-container   Reuse existing containers (skip rebuild)
  --judge-model       Override the judge model for LLM-based scoring
  --summary           Print summary of existing results (no evaluation)
  --list              List available benchmarks and models
  --env               Path to .env file (default: auto-detect)
  --output-dir        Output directory (default: ./outputs)
```

## Supported Models

Models are configured via YAML files in `configs/models/`. The default config ships with OpenRouter models:

| Key | Model | Provider |
|-----|-------|----------|
| `claude-sonnet` | Claude Sonnet 4.6 | OpenRouter |
| `claude-opus` | Claude Opus 4.6 | OpenRouter |
| `gemini-3.1-pro` | Gemini 3.1 Pro | OpenRouter |

### Adding a Custom Model

Create a YAML file in `configs/models/`:

```yaml
my-model:
  name: My Model
  api_url: https://api.example.com/v1
  api_key_env: MY_API_KEY    # reads from environment variable
  model: model-id
  provider: openrouter       # openrouter | openai | ark | gpt_proxy
```

Then run with `--model my-model`.

## Architecture

```
ClawEvalKit/
├── run.py                          # Single entry point
├── Dockerfile.nanobot              # NanoBotAgent Docker image
├── Dockerfile.skillsbench-*        # SkillsBench base images
├── configs/
│   └── models/                     # YAML model configs (OpenCompass style)
│       ├── openrouter.yaml
│       └── _template.yaml
├── clawevalkit/                    # Core package
│   ├── config.py                   # YAML config loader
│   ├── inference.py                # Evaluation dispatcher
│   ├── summarizer.py               # Result aggregation + table printing
│   ├── dataset/                    # Benchmark implementations
│   │   ├── base.py                 # BaseBenchmark ABC
│   │   ├── skillsbench.py          # 56 tasks, per-task Docker
│   │   ├── agentbench.py           # 40 tasks, shared Docker image
│   │   ├── clawbench_official.py   # 250 tasks, NanoBotAgent + Pytest
│   │   ├── claweval.py             # 300 tasks, mock services + Docker sandbox + grader
│   │   ├── zclawbench.py           # 116 tasks, LLM Judge scoring
│   │   ├── pinchbench.py           # 23 tasks, shared Docker image
│   │   ├── tribe.py                # 8 tasks, pure LLM
│   │   └── skillbench.py           # 22 tasks, harness + pytest
│   ├── api/                        # API model wrappers
│   │   ├── openrouter.py           # OpenRouter (Claude, Gemini, etc.)
│   │   └── ...
│   ├── grading/                    # Scoring logic
│   │   ├── judge_prompt.py         # LLM Judge prompts
│   │   └── zclawbench_grading.py   # 4-dimension Judge scoring
│   └── utils/
│       ├── docker_runner.py        # Docker container lifecycle manager
│       ├── nanobot.py              # NanoBotAgent import helper
│       └── ...
├── benchmarks/                     # Benchmark data
│   ├── skillsbench/
│   ├── agentbench-openclaw/
│   ├── claw-bench/                 # ClawBench Official tasks
│   ├── claw-eval/                  # ClawEval tasks + mock services + graders
│   ├── claw-bench-tribe/           # Tribe tasks
│   ├── zclawbench/
│   └── pinchbench/
├── OpenClawPro/                    # NanoBotAgent engine (submodule)
└── outputs/                        # Evaluation results (gitignored)
```

## Benchmark Details

### SkillsBench (`skillsbench`)

56 tasks that test code generation and modification capabilities. Each task has its own Dockerfile defining the target environment. The agent reads instructions, generates/modifies code, and results are verified via pytest. Supports multi-turn feedback: if tests fail, the agent sees the error and retries.

### AgentBench-OpenClaw (`agentbench`)

40 tasks covering file operations, system administration, and information retrieval. Uses L0 (file existence) and L1 (metric-based) scoring. Tasks run inside the shared NanoBotAgent Docker container with volume-mounted workspaces.

### WildClawBench (`wildclawbench`)

**[Deprecated]** WildClawBench has been removed from the toolkit. Use `clawbench-official` or `claweval` instead.

### ClawBench (`clawbench-official`)

250 tasks across multiple domains. Each task has its own `task.toml` config defining instructions, environment, and verification criteria. The agent executes inside Docker containers using NanoBotAgent, and results are verified via Pytest. Supports both native (subprocess) and Docker execution modes.

### ClawEval (`claweval`)

300 tasks evaluating agent capabilities through mock API services and Docker sandboxes. Each task defines tools (mock HTTP endpoints), fixtures, and graders. The workflow per task: start mock services → launch Docker sandbox → inject fixtures → run NanoBotAgent → collect audit data → grade using multi-dimension scorers (completion, robustness, communication, safety). Supports parallel execution with port-offset isolation.

### ZClawBench (`zclawbench`)

116 tasks evaluated by an LLM Judge across 4 weighted dimensions: Task Completion (35%), Tool Usage (25%), Reasoning (20%), and Answer Quality (20%). Supports both native (18 tasks) and Docker (116 tasks) modes.

### PinchBench (`pinchbench`)

23 tasks with rule-based scoring. Each task contains embedded `grade()` functions that are executed inside the Docker container to verify correctness.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | API key for OpenRouter (or any OpenAI-compatible API) | — |
| `JUDGE_API_KEY` | API key for LLM Judge | Falls back to `OPENROUTER_API_KEY` |
| `JUDGE_MODEL` | Judge model name | `anthropic/claude-sonnet-4.6` |
| `JUDGE_BASE_URL` | Judge API base URL | `https://openrouter.ai/api/v1` |
| `DOCKER_IMAGE_NANOBOT` | NanoBotAgent Docker image | `clawbase-nanobot:v1` |
| `CLAWBENCH_DOCKER_IMAGE` | ClawBench Docker image | `clawbase-nanobot:v1` |
| `OPENCLAWPRO_DIR` | Path to OpenClawPro source | `ClawEvalkit/OpenClawPro` |

## Adding a New Benchmark

1. Create `clawevalkit/dataset/mybench.py`:

```python
from .base import BaseBenchmark

class MyBench(BaseBenchmark):
    DISPLAY_NAME = "My Benchmark"
    TASK_COUNT = 100
    SCORE_RANGE = "0-100"

    def evaluate(self, model_key, config, sample=0, **kwargs):
        # Your evaluation logic
        return {"score": 85.0, "passed": 85, "total": 100}
```

2. Register in `clawevalkit/dataset/__init__.py`:

```python
from .mybench import MyBench
BENCHMARKS["mybench"] = MyBench
```

## License

Apache 2.0. See [LICENSE](LICENSE).
