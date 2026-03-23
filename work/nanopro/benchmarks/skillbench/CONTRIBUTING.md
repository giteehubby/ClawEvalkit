# Contributing to Agent Skills Benchmark

Thanks for helping build an open benchmark for Agent Skills! This guide covers how to get started.

## Project Structure
- `harness/`: CLI + runner code.
- `packs/`: task packs (coding, docs, etc.).
- `docs/`: design/architecture notes.
- `reports/`: local output artifacts (ignored in git except placeholders).

## Getting Started
1. Fork the repo and clone locally.
2. Ensure Python 3.11+ and Docker (for future runner support) are installed.
3. Install harness dependencies (placeholder): `pip install -r harness/requirements.txt`.
4. Build the Docker base image: `./scripts/build-base-image.sh`
5. Run the CLI stub to verify setup:
   ```bash
   python -m harness.cli --pack packs/coding/swe-lite --mode baseline
   ```
6. Test baseline + augmented mode with the mock solver:
   ```bash
   python -m harness.cli run --pack packs/coding/swe-lite --mode both \
     --agent mock \
     --skill packs/coding/swe-lite/skills/calc-fixer
   ```

## SWE-bench-style split
```bash
python -m harness.cli infer --pack packs/coding/swe-lite --mode both \
  --agent mock --skill packs/coding/swe-lite/skills/calc-fixer

python -m harness.cli eval --pack packs/coding/swe-lite --mode baseline --predictions predictions \
  --output reports/baseline.json
python -m harness.cli eval --pack packs/coding/swe-lite --mode augmented --predictions predictions \
  --output reports/augmented.json

python -m harness.cli compare --baseline reports/baseline.json --augmented reports/augmented.json
```

Validate predictions:
```bash
python3 scripts/validate_predictions.py predictions/baseline.jsonl
python3 scripts/validate_predictions.py predictions/augmented.jsonl
```
7. If you have Claude Code installed, try the real agent adapter (local runner):
   ```bash
   python -m harness.cli --runner local --pack packs/coding/swe-lite --mode augmented \
     --agent claude --agent-model sonnet \
     --skill packs/coding/swe-lite/skills/calc-fixer
   ```

8. API adapter (Anthropic) example:
   ```bash
   export ANTHROPIC_API_KEY=...
   export SKILLBENCH_AGENT_MODEL=claude-3-5-sonnet-20241022
   python -m harness.cli --runner local --pack packs/coding/swe-lite --mode both \
     --agent anthropic --include-skill-body \
     --skill packs/coding/swe-lite/skills/calc-fixer
   ```

9. API adapter (OpenAI) example:
   ```bash
   export OPENAI_API_KEY=...
   export SKILLBENCH_AGENT_MODEL=gpt-4.1-mini
   python -m harness.cli --runner local --pack packs/coding/swe-lite --mode both \
     --agent openai --include-skill-body \
     --skill packs/coding/swe-lite/skills/calc-fixer
   ```

## Report Validation
Run:
```bash
python3 scripts/validate_report.py reports/latest.json
```
   (Currently outputs a placeholder JSON report.)

## How to Contribute
- **Task Packs**: Add tasks under `packs/<domain>/<pack>/` with `manifest.yaml`, setup scripts, and grading logic. Follow governance rules in `docs/benchmark-design.md`.
- **Harness**: Improve CLI, runner integration, reporting schema. Coordinate larger changes via GitHub Issues/PRs.
- **Documentation**: Expand design docs, guides, and examples.

## Skill Format Requirements
Skills must include a `SKILL.md` with YAML frontmatter containing `name` and `description`.
The benchmark runner installs skills into `.claude/skills/<name>` for agents to load.

## Coding Standards
- Python code should pass `ruff`/`black` (formatting rules to be added).
- Use descriptive commit messages and reference relevant issues.

## Reporting Results
- Until hosted services exist, run the harness locally and attach generated JSON + logs to PRs/issues for discussion.

## Questions?
Open an issue or start a discussion—feedback is welcome!
