# Agent Skills Benchmark — Scope of Work

## 1. Purpose
- Establish an open, repeatable way to measure how individual Agent Skills improve (or regress) an agent’s performance relative to a baseline configuration.
- Give skill authors and marketplaces objective data (beyond install counts) so they can highlight capability gains, efficiency trade-offs, and safety considerations.

## 2. Success Criteria
1. **Benchmark Harness**: CLI/Action that runs a fixed suite of tasks in two modes—baseline and augmented—and emits structured metrics/logs.
2. **Task Packs**: At least one domain-specific pack (target: coding) with 10+ reproducible tasks, grading scripts, and documentation for extending to other domains (documents, analytics, operations).
3. **Reporting Schema**: JSON schema + markdown template that summarizes success deltas, resource cost changes, and notable failures.
4. **Pilot Results**: Reference runs for at least two skills that demonstrate end-to-end workflow and surface example insights.

## 3. Scope & Deliverables
| Workstream | Deliverables | Notes |
| --- | --- | --- |
| Benchmark Design | Process doc describing run flow, metrics, and governance | Draft from current discussion; iterate as requirements emerge. |
| Harness Implementation | Repo with CLI (likely Node/Python) + GitHub Action template, logging, config for skills | Must support plug-in “task pack” concept; deterministic seeds where possible. |
| Task Pack #1 – Coding | Curated SWE-bench-style repos or smaller tickets, grading scripts, dataset manifest | Prioritize open-source tasks with automated verification via tests. |
| Reporting & Publishing | JSON schema, sample report, guidance for marketplaces to ingest | Consider signed attestations (e.g., provenance hash). |
| Community Onboarding | Contribution guide + checklist for authors to run the benchmark locally and submit data | Optional but improves adoption. |

## 4. Out of Scope (initial phase)
- Hidden/private eval sets (may be future work).
- Automated security vetting of Skills (document guidelines instead).
- Marketplace integrations beyond a lightweight data ingestion spec.

## 5. Approach & Phasing
1. **Discovery (Week 0-1)**: Finalize benchmark goals, define metrics, pick tooling stack, identify 10 candidate coding tasks. Output: Benchmark design doc draft.
2. **Prototype Harness (Week 1-2)**: Build minimal CLI to run baseline vs skill, collect logs, and compare success metric for one trivial task.
3. **Task Pack Build-out (Week 2-3)**: Implement coding pack with auto-grading (leveraging pytest, etc.), document setup scripts, ensure deterministic runs.
4. **Reporting Layer (Week 3-4)**: Define JSON schema, summary markdown template, and sample scoreboard.
5. **Pilot Runs (Week 4-5)**: Select two real skills, run benchmark, refine ergonomics from feedback, publish example reports.

## 6. Open Questions / Risks
- **Task Diversity**: How to represent domains beyond coding? Need SMEs for docs, data-heavy workflows.
- **Benchmark Gaming**: Mitigation for overfitting (e.g., rotating hidden tasks, run attestations).
- **Resource Cost**: Running full SWE-bench is expensive; may need lightweight subset or hosted infra plan.
- **Skill Compatibility**: Some skills require network/file access; harness needs configurable sandbox and clear policy.

## 7. Immediate Next Steps
1. Draft “Benchmark Design” doc expanding on metrics, harness architecture, and governance.
2. Inventory candidate coding tasks (SWE-bench issues or smaller repositories) and evaluate licensing/setup.
3. Choose implementation stack (language, test runner, packaging) and sketch CLI interface (`benchmark run --skill path/to/skill`).
4. Set up repo structure (e.g., `/harness`, `/tasks/coding`, `/reports`, `/docs`) with contribution guidelines.

