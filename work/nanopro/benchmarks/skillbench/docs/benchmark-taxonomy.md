# Benchmark Taxonomy (Draft)

This defines a proposed taxonomy of skill types and their associated core suites.

## Skill Types
1. **Coding / SWE**
   - Bug fixes, refactors, tests, migrations
2. **Document / Office**
   - PDF forms, slides, reports, contracts
3. **Data / Analytics**
   - SQL, data summarization, dashboards
4. **Ops / Runbooks**
   - Incident handling, log analysis, remediation
5. **Research / Knowledge**
   - Retrieval, synthesis, citation accuracy
6. **Decision / Strategy**
   - Multi-step tradeoffs, risk-aware decisions (e.g., markets)

## Core Suites (Cross-domain)
These suites are intended to apply across most skills:
- **core.tool-use.v1** — tool selection and parameterization
- **core.recovery.v1** — error recovery and replanning
- **core.state.v1** — state tracking across steps
- **core.robustness.v1** — perturbations & distribution shift
- **core.goal.v1** — goal adherence / constraint compliance

## Domain Packs (Examples)
- **coding.swe-lite.v1** — lightweight SWE tasks
- **docs.text-lite.v1** — plain-text document edits (baseline pack)
- **data.sql-lite.v1** — SQL correctness + small datasets
- **ops.triage.v1** — incident classification + remediation
- **research.synthesis.v1** — multi-source summaries with citations
- **markets.prediction.v1** — replayed market decisions with perturbations

## Failure-Mode Mutators
Reusable perturbations applied across suites:
- Tool timeouts / 500s
- Missing fields or schema drift
- Ambiguous instructions
- Distractor data
- Partial success states

Suites should be built by composing a base task generator with mutators.
