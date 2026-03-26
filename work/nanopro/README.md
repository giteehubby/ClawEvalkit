# NanoBot Benchmark Project

Unified evaluation harness for OpenClaw-like agents.

## Project Structure

```
nanopro/
├── configs/               # Configuration files
│   ├── benchmarks/        # Benchmark-specific configs
│   ├── conditions/       # Condition configs (training-free recipes)
│   └── experiments/       # Experiment configs
├── src/                  # Source code
│   ├── harness/          # Agent harness (NanoBot)
│   ├── runners/          # Benchmark runners
│   ├── conditions/       # Training-free recipe implementations
│   ├── logging/          # Logging utilities
│   ├── analysis/         # Analysis tools
│   ├── annotation/       # Annotation tools
│   └── training/         # SFT training utilities
├── artifacts/            # Experiment outputs
│   ├── runs/            # Raw run results & transcripts
│   ├── aggregates/      # Aggregated results
│   ├── plots/           # Visualizations
│   ├── tables/          # Result tables
│   └── failure_cases/   # Failure case analyses
├── docs/                 # Documentation
├── scripts/              # Utility scripts
└── benchmarks/           # Benchmark repositories
```

## Quick Start

```bash
cd /Volumes/F/Clauding/AwesomeSkill/work/nanopro/scripts

# Run all benchmarks
python run_all_benchmarks.py

# Run specific benchmark
python run.py --benchmark skillsbench --threads 10
```

## Benchmarks

| Benchmark | Status |
|-----------|--------|
| AgentBench-OpenClaw | ✅ Complete |
| claw-bench (official) | ✅ Complete |
| PinchBench | ✅ Complete |
| SkillsBench | ✅ Complete |
| TRIBE-INC/claw-bench | ✅ Complete |
| skillbench | ✅ Complete |
| SciSkillBench | ❌ Abandoned |

## Documentation

- [Paper Plan](docs/paper_plan.md)
- [Experiment Schedule](docs/experiment_schedule.md)
- [Project Schedule](docs/schedule.md)
