# Agent Skills Benchmark

An open benchmarking harness (inspired by SWE-bench) for measuring how individual Agent Skills improve a base agent’s performance. The project pairs:
- **Open task packs** (coding, documents, etc.) with automated grading.
- **Baseline vs augmented runs** to quantify deltas introduced by a Skill.
- **Structured reports** that marketplaces and builders can ingest.

## Repo Layout (initial)
```
agent-skills-benchmark/
├── README.md
├── scope-of-work.md
├── roadmap.md
├── docs/
│   └── benchmark-design.md
├── harness/
│   ├── cli.py            # CLI entrypoint (WIP)
│   ├── __init__.py
│   └── runners/          # sandbox utilities
├── packs/
│   └── coding/
│       └── swe-lite/     # placeholder pack
├── reports/
│   └── .gitkeep
└── scripts/
    └── .gitkeep
```

> Structure mirrors SWE-bench’s `tasks/` + grading scripts, but extends to Agent Skills by running each scenario twice (baseline vs augmented) and capturing deltas.

## Getting Started
1. Install Python 3.11+ (initial harness prototype will be Python-based).
2. `pip install -r harness/requirements.txt`
3. Build the Docker base image:
   ```bash
   ./scripts/build-base-image.sh
   ```
4. Run baseline (combined run):
   ```bash
   python -m harness.cli --pack packs/coding/swe-lite --mode baseline
   ```
5. Run baseline + augmented with mock solver (to validate deltas):
   ```bash
   python -m harness.cli --pack packs/coding/swe-lite --mode both \
     --agent mock \
     --skill packs/coding/swe-lite/skills/calc-fixer
   ```

## SWE-bench-style split
Generate patches:
```bash
python -m harness.cli infer --pack packs/coding/swe-lite --mode both \
  --agent mock --skill packs/coding/swe-lite/skills/calc-fixer
```
Evaluate patches:
```bash
python -m harness.cli eval --pack packs/coding/swe-lite --mode baseline --predictions predictions \
  --output reports/baseline.json
python -m harness.cli eval --pack packs/coding/swe-lite --mode augmented --predictions predictions \
  --output reports/augmented.json
```
Compare:
```bash
python -m harness.cli compare --baseline reports/baseline.json --augmented reports/augmented.json
```
Profile-only output:
```bash
python -m harness.cli compare --baseline reports/baseline.json --augmented reports/augmented.json \
  --profile-output reports/profile.json
```

## Document pack (text-lite)
Run the docs pack:
```bash
python3 -m harness.cli run --runner local --pack packs/docs/text-lite --mode both \
  --agent mock
```
With a docs skill:
```bash
python3 -m harness.cli run --runner local --pack packs/docs/text-lite --mode both \
  --agent mock --skill packs/docs/text-lite/skills/doc-filler
```

## Data pack (sql-lite)
Run the SQL pack:
```bash
python3 -m harness.cli run --runner local --pack packs/data/sql-lite --mode both \
  --agent mock
```
Validate predictions:
```bash
python3 scripts/validate_predictions.py predictions/baseline.jsonl
python3 scripts/validate_predictions.py predictions/augmented.jsonl
```

## Leaderboard summary
Generate a compact summary from two eval reports:
```bash
python3 scripts/leaderboard.py reports/baseline.json reports/augmented.json > reports/leaderboard.json
```

## Leaderboard aggregation
If you store report pairs per-skill:
```
leaderboard/
  calc-fixer/
    baseline.json
    augmented.json
  another-skill/
    baseline.json
    augmented.json
```
Then run:
```bash
python3 scripts/aggregate_leaderboard.py leaderboard > reports/leaderboard.json
```

## Robustness checks (perturbations)
Run eval with injected perturbations:
```bash
python3 scripts/robustness_eval.py packs/coding/swe-lite baseline predictions tool_failure
python3 scripts/robustness_eval.py packs/coding/swe-lite baseline predictions ambiguous_instructions
python3 scripts/robustness_eval.py packs/coding/swe-lite baseline predictions missing_fields
```
Fold robustness into compare by passing files:
```bash
python3 scripts/robustness_eval.py packs/coding/swe-lite baseline predictions tool_failure reports/robust-baseline.json
python3 scripts/robustness_eval.py packs/coding/swe-lite augmented predictions tool_failure reports/robust-augmented.json
python -m harness.cli compare --baseline reports/baseline.json --augmented reports/augmented.json \
  --robustness-baseline reports/robust-baseline.json \
  --robustness-augmented reports/robust-augmented.json
```
You can also point compare at a directory of robustness files:
```bash
python -m harness.cli compare --baseline reports/baseline.json --augmented reports/augmented.json \
  --robustness-dir reports
```

## Composability (multi-skill)
Run with multiple skills:
```bash
python3 -m harness.cli --runner local --pack packs/coding/swe-lite --mode both \
  --agent mock \
  --skill packs/coding/swe-lite/skills/calc-fixer \
  --skills packs/coding/swe-lite/skills/slugify-fixer
```

## Real Agent Adapter (Claude Code)
If you have the `claude` CLI installed, run with the local runner:
```bash
python -m harness.cli --runner local --pack packs/coding/swe-lite --mode augmented \
  --agent claude --agent-model sonnet \
  --skill packs/coding/swe-lite/skills/calc-fixer
```
Note: the Docker runner does not include the `claude` binary, so use `--runner local` for this adapter.

## API Adapter (Anthropic)
Set environment variables (option 1 - export):
```
export ANTHROPIC_API_KEY=...
export SKILLBENCH_AGENT_MODEL=claude-3-5-sonnet-20241022
```
Or use a `.env` file (option 2 - recommended):
```bash
cp .env.example .env
# Edit .env and add your API key
```
The CLI automatically loads variables from `.env` at startup.
Run (local runner recommended for now):
```bash
python -m harness.cli --runner local --pack packs/coding/swe-lite --mode both \
  --agent anthropic --include-skill-body \
  --skill packs/coding/swe-lite/skills/calc-fixer
```
TLS notes: if your system CA bundle is missing or custom, set `SKILLBENCH_CA_BUNDLE`
to point at a PEM file. The adapters will also use `SSL_CERT_FILE` or
`REQUESTS_CA_BUNDLE` if set.
Timeouts + retries (optional):
```
export SKILLBENCH_AGENT_TIMEOUT=300            # total agent subprocess timeout
export SKILLBENCH_AGENT_REQUEST_TIMEOUT=120    # per-API call timeout
export SKILLBENCH_AGENT_RETRIES=2              # API retries
export SKILLBENCH_AGENT_BACKOFF=1.5            # exponential backoff base (seconds)
```

## API Adapter (OpenAI)
Set environment variables (or use `.env` file as shown above):
```
export OPENAI_API_KEY=...
export SKILLBENCH_AGENT_MODEL=gpt-4.1-mini
```
Run:
```bash
python -m harness.cli --runner local --pack packs/coding/swe-lite --mode both \
  --agent openai --include-skill-body \
  --skill packs/coding/swe-lite/skills/calc-fixer
```
TLS notes: if your system CA bundle is missing or custom, set `SKILLBENCH_CA_BUNDLE`
to point at a PEM file. The adapters will also use `SSL_CERT_FILE` or
`REQUESTS_CA_BUNDLE` if set.
Timeouts + retries (optional):
```
export SKILLBENCH_AGENT_TIMEOUT=300            # total agent subprocess timeout
export SKILLBENCH_AGENT_REQUEST_TIMEOUT=120    # per-API call timeout
export SKILLBENCH_AGENT_RETRIES=2              # API retries
export SKILLBENCH_AGENT_BACKOFF=1.5            # exponential backoff base (seconds)
```

## Skill Format
Skills must follow the Agent Skills standard:
- A directory containing `SKILL.md`
- `SKILL.md` must start with YAML frontmatter and include `name` and `description`
The runner installs skills into `.claude/skills/<name>` before running the agent.

## Report Validation
You can validate the report JSON using:
```bash
python3 scripts/validate_report.py reports/latest.json
```

## Status
**Phase 0 (Foundations) - Complete**
- ✅ Scope and roadmap drafted
- ✅ Benchmark design doc drafted
- ✅ Harness CLI with `run`, `infer`, `eval`, `compare` commands
- ✅ Coding task pack with 10 tasks (swe-lite)
- ✅ Document and data task packs
- ✅ Multi-dimensional profiling (reliability, efficiency, robustness, composability, failure legibility)
- ✅ Agent adapters (mock, Claude Code, Anthropic API, OpenAI API)
- ✅ Local and Docker runners

See `docs/benchmark-design.md` for detailed architecture/metrics plans.
See `docs/skill-profile.md` for the multi-dimensional profile schema.
See `docs/benchmark-taxonomy.md` for skill types and core suites.
See `docs/suite-governance.md` for trust tiers and suite review process.
