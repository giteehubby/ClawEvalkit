# ClawEvalKit

Unified evaluation framework for 8 agent benchmarks. Follows [VLMEvalKit](https://github.com/open-compass/VLMEvalKit) conventions (single `run.py` entry, self-contained benchmark classes) with [OpenCompass](https://github.com/open-compass/opencompass)-style YAML model configs.

## Installation

```bash
git clone https://github.com/clawevalkit/clawevalkit.git
cd clawevalkit
pip install -e .
```

## Quick Start

```bash
# List all benchmarks and models
python3 run.py --list

# Run Tribe benchmark with Claude Sonnet
python3 run.py --bench tribe --model claude-sonnet

# Run multiple benchmarks with multiple models
python3 run.py --bench tribe,pinchbench --model claude-sonnet,claude-opus

# Sample 5 tasks per benchmark (for quick testing)
python3 run.py --bench tribe --model claude-sonnet --sample 5

# View summary of all existing results
python3 run.py --summary
```

## Supported Benchmarks

| Key | Benchmark | Tasks | Scoring | Description |
|-----|-----------|------:|---------|-------------|
| `tribe` | Claw-Bench-Tribe | 8 | 0-100 | Pure LLM reasoning tests |
| `pinchbench` | PinchBench | 23 | 0-100 | Rule-based file/content checks |
| `agentbench` | AgentBench-OpenClaw | 40 | 0-100 | L0 rule + L1 metric scoring |
| `skillbench` | SkillBench | 22 | 0-100% | Agent diff patch + pytest |
| `skillsbench` | SkillsBench | 56+ | 0-100% | Multi-turn LLM code gen + pytest |
| `zclawbench` | ZClawBench Subset | 18 | 0-1 | NanoBotAgent + LLM Judge |
| `wildclawbench` | WildClawBench | 10 | 0-1 | Safety alignment + LLM Judge |
| `clawbench-official` | ClawBench Official | 250 | 0-100 | ReAct Agent + Pytest |

## Supported Models

Models are configured via YAML files in `configs/models/`. The default config ships with OpenRouter models:

| Key | Model | Provider |
|-----|-------|----------|
| `claude-sonnet` | Claude Sonnet 4.6 | OpenRouter |
| `claude-opus` | Claude Opus 4.6 | OpenRouter |
| `gemini-3.1-pro` | Gemini 3.1 Pro | OpenRouter |

You can add any OpenAI-compatible model by creating a YAML file in `configs/models/`.

## Architecture

```
ClawEvalKit/
├── run.py                    # Single entry point
├── configs/
│   ├── models/               # YAML model configs (OpenCompass style)
│   │   ├── openrouter.yaml
│   │   └── _template.yaml
│   └── eval/                 # Evaluation presets
│       ├── default.yaml
│       └── quick.yaml
├── clawevalkit/              # Core package
│   ├── config.py             # YAML config loader → MODELS dict
│   ├── inference.py          # Evaluation dispatcher
│   ├── summarizer.py         # Result aggregation + table printing
│   ├── cli.py                # CLI entry point
│   ├── dataset/              # Benchmark implementations
│   │   ├── base.py           # BaseBenchmark ABC
│   │   ├── tribe.py          # 8 pure LLM tests
│   │   ├── pinchbench.py     # 23 rule-based tasks
│   │   └── ...               # 6 more benchmarks
│   ├── api/                  # API model wrappers
│   │   ├── base.py           # BaseAPI: generate(messages) → str
│   │   ├── openai_proxy.py   # OpenAI-compatible proxy
│   │   └── openrouter.py     # OpenRouter (Claude, Gemini)
│   └── utils/
│       ├── api.py            # call_llm() implementation (zero-dep urllib)
│       └── log.py            # Logging
├── outputs/                  # Evaluation results (gitignored)
├── pyproject.toml
└── requirements.txt
```

## Adding a New Model

Create a YAML file in `configs/models/`:

```yaml
my-model:
  name: My Model
  api_url: https://api.example.com/v1
  api_key_env: MY_API_KEY    # reads from environment variable
  model: model-id
  provider: openrouter       # openrouter | openai
```

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

    def collect(self, model_key):
        # Load cached results
        result_dir = self._find_result_dir("mybench")
        ...
```

2. Register in `clawevalkit/dataset/__init__.py`:

```python
from .mybench import MyBench
BENCHMARKS["mybench"] = MyBench
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | API key for OpenRouter |
| `JUDGE_API_KEY` | API key for LLM Judge (defaults to `OPENROUTER_API_KEY`) |
| `JUDGE_MODEL` | Judge model name (default: `anthropic/claude-sonnet-4.6`) |
| `JUDGE_BASE_URL` | Judge API base URL (default: `https://openrouter.ai/api/v1`) |
| `OPENCLAWPRO_DIR` | Path to OpenClawPro (for ZClawBench/WildClawBench) |

## License

Apache 2.0. See [LICENSE](LICENSE).
