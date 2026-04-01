# ClawEvalKit Development Guide

## Project Overview

ClawEvalKit is a unified evaluation framework for 8 agent benchmarks, designed following [VLMEvalKit](https://github.com/open-compass/VLMEvalKit) conventions (single `run.py` entry, self-contained benchmark classes) with [OpenCompass](https://github.com/open-compass/opencompass)-style YAML model configs.

## Architecture

| Component | Description |
|-----------|-------------|
| `clawevalkit/dataset/` | 8 Benchmark implementations (each a self-contained class) |
| `clawevalkit/grading/` | LLM Judge scoring logic |
| `clawevalkit/api/` | API model wrappers (BaseAPI + providers) |
| `clawevalkit/config.py` | YAML config loader → MODELS dict |
| `clawevalkit/inference.py` | Evaluation dispatcher |
| `clawevalkit/summarizer.py` | Result aggregation + table printing |
| `OpenClawPro/harness/` | Agent execution framework (NanoBotAgent) |
| `benchmarks/` | Evaluation data (7 directories) |

### Key Design Decisions

1. **Evaluation & inference decoupled**: ClawEvalKit handles evaluation logic; OpenClawPro provides agent execution (NanoBotAgent), connected via lazy import `_import_nanobot_agent()`
2. **YAML config externalized**: Model definitions in `configs/models/*.yaml`, not hardcoded
3. **Grading module independent**: Judge scoring extracted to `clawevalkit/grading/`, no circular dependency on inference framework
4. **Benchmarks data built-in**: Small datasets (~50MB) in `benchmarks/`; large datasets (skillsbench 2.2G) via HuggingFace

## Quick Start

```bash
pip install -e .

python3 run.py --list              # List benchmarks and models
python3 run.py --summary           # Summarize existing results
python3 run.py --bench tribe --model claude-sonnet
python3 run.py --bench tribe,pinchbench --model claude-sonnet,claude-opus
python3 run.py --sample 5          # Quick sampling mode
```

## Adding a New Model

Create a YAML in `configs/models/your_model.yaml`:

```yaml
my-model:
  name: My Model
  api_url: https://api.example.com/v1
  api_key_env: MY_API_KEY
  model: model-id
  provider: openrouter
```

## Adding a New Benchmark

1. Create `clawevalkit/dataset/mybench.py` implementing `BaseBenchmark`
2. Register in `clawevalkit/dataset/__init__.py`

See `examples/add_benchmark.py` for details.

## Tests

```bash
pytest tests/ -v  # 13 tests
```

## TODO

- [ ] SkillsBench: upgrade to multi-turn agent mode
- [ ] SkillBench: improve diff patch format handling
- [ ] ClawBench Official: full 250-task evaluation
- [ ] CI/CD: GitHub Actions automated testing
