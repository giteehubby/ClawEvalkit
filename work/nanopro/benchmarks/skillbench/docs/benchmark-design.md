# Agent Skills Benchmark — Design Overview

## 1. Goals
- Measure the **marginal impact** of installing a specific Agent Skill on a base agent configuration.
- Provide **comparable, reproducible metrics** across skills, domains, and model versions.
- Keep the system **open and auditable** so community members can contribute task packs, harness modules, and verified results.

## 2. Evaluation Dimensions
| Dimension | Description | Example Metrics |
| --- | --- | --- |
| Success | Did the agent satisfy the task requirements? | Pass/fail count, quality score, human review flag |
| Efficiency | Resource consumption relative to baseline | Tokens, runtime, tool calls, dollar estimate |
| Reliability | Stability and safety | Error types, crash rate, policy violations |
| Ergonomics | Author effort to integrate skill | Setup complexity, dependency checks (qualitative) |

Each benchmark run must output (a) absolute metrics per scenario and (b) delta vs baseline (percentage or absolute change).

## 3. Benchmark Flow (SWE-bench-style)
1. **Preparation**
   - Select `task_pack` (e.g., `coding/swe-lite@v1`).
   - Provide `baseline_config` (model, agent scaffold, tool access).
   - Provide `skill_config` (path or repo, setup script, version metadata).
2. **Inference (patch generation)**
   - `baseline`: run agent without skill to produce a patch per task.
   - `augmented`: install skill and rerun identical tasks to produce patches.
   - Output: predictions directory containing one patch (unified diff) per task.
3. **Evaluation (Docker harness)**
   - Apply patches in clean containers and run tests.
   - Score pass/fail + runtime metrics; no API calls.
4. **Reporting**
   - Generate structured JSON (per-task metrics, aggregate stats, environment info).
   - Compute deltas between baseline and augmented runs.
   - Optional markdown/PDF summary for sharing.

## 4. Harness Architecture
```
/harness
  /cli          # entrypoint (Python/Node)
  /core         # orchestrator: task loader, runner, metrics aggregator
  /packs        # references to task packs (git submodules or registry)
  /skills       # optional local skill installs for testing
  /reporting    # JSON schema + templates
```

**Components**
- **Runner**: spins up sandbox (Docker?) with defined tool access; enforces max steps, context, runtime.
- **Task Adapter**: standardized interface (`prepare()`, `execute(agent)`, `grade()`).
- **Skill Installer**: handles SKILL.md detection, dependencies, environment setup.
- **Metrics Collector**: wraps agent to capture tokens, latency, errors.
- **Report Generator**: compiles baseline vs augmented stats + metadata (versions, git commit).

## 5. Task Packs
- **Structure**: `packs/<domain>/<pack-name>/manifest.yaml`
  - Metadata: version, description, dependencies, licensing.
  - Task list: pointer to repositories/files + grading instructions.
- **Types**:
  - *Coding*: SWE-bench subset, single-file bug fixes, script writing.
  - *Documents*: PDF form fill, Word/PPT generation, compliance memos.
  - *Data/Analytics*: SQL review, dashboard updates.
  - *Operations*: Runbook execution, incident triage.
- **Versioning**: Semantic versioning; harness pin ensures reproducibility.

## 6. Metrics Schema (draft)
```jsonc
{
  "benchmark_version": "0.1.0",
  "task_pack": "coding/swe-lite@1.0.0",
  "predictions_dir": "predictions/baseline",
  "baseline": {
    "model": "claude-3.5-sonnet",
    "skill": null,
    "aggregate": {
      "success_rate": 0.35,
      "avg_tokens": 48_000,
      "avg_runtime_s": 320
    }
  },
  "augmented": {
    "model": "claude-3.5-sonnet",
    "skill": {
      "name": "supabase/postgres-patterns",
      "version": "1.2.0",
      "hash": "abc123"
    },
    "aggregate": {
      "success_rate": 0.47,
      "avg_tokens": 39_000,
      "avg_runtime_s": 290
    },
    "delta": {
      "success_rate": +0.12,
      "avg_tokens": -9_000,
      "avg_runtime_s": -30
    }
  },
  "tasks": [
    {
      "id": "swe-lite-001",
      "baseline": { "result": "fail", "tokens": 52_300 },
      "augmented": { "result": "pass", "tokens": 41_900, "notes": "Added missing store_cv flag" }
    }
  ],
  "environment": {
    "runner": "docker://skillbench/runner@sha256:...",
    "timestamp": "2026-01-24T15:40:00Z",
    "git_commit": "..."
  }
}
```

## 7. Governance & Contributions
- **Task Pack Review**: use PR-based process; require grading instructions and reproducibility proof.
- **Skill Submissions**: authors run harness locally or via hosted service; submit JSON + logs.
- **Leaderboard Policies**: clearly state scoring formula, allow multiple skill entries, flag runs older than N days.
- **Security**: skills executed in sandbox; restrict network/file access based on pack requirements.
- **Version Compatibility**: tag benchmark releases; older reports reference specific harness version.

## 8. Open Questions
- Deterministic agent behavior is hard—how many retries allowed before marking failure?
- How to handle skills needing external APIs (provide stubs? allow opt-in network)?
- Do we require provenance/signatures for reports to prevent falsified results?
- Should we support composite skills (multiple SKILL.md packages) or test one at a time?

## 9. Immediate Tasks
1. Finalize metrics schema and decide on serialization format (JSON vs JSONL).
2. Choose runner technology (Docker vs Firecracker vs local process with sandbox).
3. Implement CLI skeleton (`python -m harness.cli --pack packs/coding/swe-lite --skill path/to/skill`).
4. Draft contribution guidelines for task packs + result submissions.
