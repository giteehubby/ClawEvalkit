# Deep Solver Benchmark

This directory contains the Deep Solver multi-agent system and benchmark infrastructure for evaluating agent performance on materials science and chemistry problems.

## Quick Links

- **[DEVELOPMENT.md](DEVELOPMENT.md)** - Local development setup and running benchmarks
- **[ADAPTIVE_AGENTS.md](../conversational_system/ADAPTIVE_AGENTS.md)** - Using vLLM and non-OpenAI models
- **[LAMMPS_INSTALLATION_README.md](LAMMPS_INSTALLATION_README.md)** - LAMMPS installation for MD benchmarks

## Agent System Variants

| Directory | Purpose | `processed_output` Style |
|-----------|---------|--------------------------|
| `deep_solver/` | Automated benchmarking | Extracted, formatted answers |
| `deep_solver_free_form/` | Human demonstrations | Detailed explanations and analysis |

Both variants use the same 4-agent architecture and Pydantic structured output:
1. **Solution Researcher** - Web search and code extraction
2. **Code Agent** - Code execution and verification
3. **Debug Agent** - Systematic debugging (3 parallel instances)
4. **Output Processor** - Result selection and formatting

The key difference is in the `processed_output` field: `deep_solver/` produces concise, machine-parseable answers for automated evaluation, while `deep_solver_free_form/` produces detailed explanations suitable for human reading.

## Directory Structure

```
deep_solver_benchmark/
├── deep_solver/              # Structured output agents
├── deep_solver_free_form/    # Free-form output agents
├── ablation_studies/         # Ablation study variants
├── baselines/                # Baseline agent implementations
├── data_for_demonstration/   # Data files for demonstration tasks
├── run_benchmark.sh          # Benchmark runner script
└── test_workflow.py          # Integration tests
```

## Data for Demonstration

The `data_for_demonstration/` directory contains data files used by free-form demonstration tasks located in `benchmark_tasks_and_results/demonstration/free_form_output/`. These files are placed here (outside `benchmark_tasks_and_results/`) because agents have read access to this directory but not to `benchmark_tasks_and_results/` (which is configured as a forbidden path to prevent agents from accessing benchmark questions and answers).

Environment variables for these data files:
- `ICSD_DATA_PATH` - Path to `icsd_structure.json`
- `STRUCTURE_PATH` - Path to `structure.json`
- `PEIS_DATA_PATH` - Path to `Li2Fe0p8Ni0p2Cl4_PEIS.json`

## Running Benchmarks

**Quick start:**
```bash
# Single question mode
python -u test_workflow.py

# Batch benchmark mode
./run_benchmark.sh
```

**For vLLM / non-OpenAI models**, set these environment variables:
```bash
export USE_ADAPTIVE_AGENTS=true
export OPENAI_BASE_URL=http://localhost:8000/v1
export AGENT_MODEL_NAME=your-model-name
export REQUIRE_OPENAI_API_KEY=false
```

**Using variants (free-form, baselines, ablations):**
Replace files in `deep_solver/` with those from the variant directory, then run as usual.

See [DEVELOPMENT.md](DEVELOPMENT.md) for complete setup and usage instructions.
