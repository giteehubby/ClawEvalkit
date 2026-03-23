# Agent Skills Benchmark — Product Roadmap (North Star)

## Vision
Create the trusted evaluation layer for Agent Skills, evolving from an open benchmark to a full observability + orchestration platform where builders can test, verify, and distribute high-quality skills—similar to how LangChain/LangSmith pairs a developer framework with managed evaluation tooling.

## Phase 0 – Foundations (Weeks 0-5)
- Deliverables: scope doc, benchmark design, initial harness, coding task pack, sample reports.
- Goal: prove feasibility and gather early adopter feedback (skill authors, marketplaces).

## Phase 1 – Open Benchmark (Months 1-3)
**Focus**: Make the benchmark a community standard.
- Expand task packs (documents, analytics, ops).
- Finalize scoring schema + contribution guidelines.
- Publish reference runs + badges (e.g., “+18% coding success / −22% tokens”).
- Foster public leaderboard (self-hosted site or integration with skills marketplaces).
 - Split workflow into SWE-bench-style stages: `infer` (patch generation) + `eval` (Docker scoring).
 - Standardize baseline vs augmented inference runs to produce skill deltas.

## Phase 2 – Managed Benchmarking Platform (Months 3-6)
**Focus**: Offer a hosted, reproducible experience akin to LangSmith eval runs.
- Hosted runners (self-serve or managed credits) to execute benchmark suites in the cloud.
- Run history dashboard: compare skill versions, detect regressions, slice by task pack.
- Artifacts: store logs, diffs, test outputs, and attach to skill versions for provenance.
- API + CLI integration for CI pipelines (auto-run benchmark before publishing a skill).
- Optional attestations/signatures to prevent tampering with results.

## Phase 3 – Observability & Insights (Months 6-9)
**Focus**: Deep analytics and diagnostics to help authors improve skills.
- Trace viewer: inspect agent/tool steps, classify failure causes, highlight token hotspots.
- Regression alerts: detect when a skill’s performance drops vs previous runs.
- Comparative analytics: benchmark multiple skills side-by-side for the same task pack.
- Marketplace widgets: embeddable performance cards that stay in sync with latest runs.

## Phase 4 – Skill Operations Suite (Months 9-12+)
**Focus**: Broader platform services beyond benchmarking.
- Managed task packs or proprietary eval sets (public + private/enterprise).
- A/B experimentation harness to test skills with real traffic (opt-in).
- Secure artifact distribution (versioned skill bundles, shift-left security scans).
- Potential monetization: premium hosting, private benchmarks, compliance reports.

## Key Principles
1. **Open Core**: benchmarking harness + task packs remain open-source to drive adoption.
2. **Trust & Transparency**: every hosted run is reproducible locally; logs + configs are downloadable.
3. **Modularity**: task packs, harness, and reporting are pluggable so partners/marketplaces can integrate easily.
4. **Community First**: maintain contributor program (task authors, skill authors) and align roadmap with their needs.

## Next Steps
1. Finish Phase 0 deliverables (scope + design + harness prototype).
2. Draft messaging + brand (“SkillBench” style) for the open benchmark site.
3. Identify early design partners (skills.sh, skillsmp.com, top skill authors) for Phase 1 adoption.
4. Outline infrastructure requirements for hosted runs (Phase 2) so we can plan budget and architecture early.
