# Suite Governance (Draft)

Define trust tiers for community test suites and how they are accepted.

## Trust Tiers
1. **Experimental**
   - Anyone can publish
   - No guarantees; not used for marketplace verification
2. **Reviewed**
   - Passes automated checks (schema, minimum trials, reproducibility)
3. **Certified**
   - Approved by review council / maintainers
   - Eligible for official verification badges
4. **Reference**
   - Used as canonical benchmarks in marketplace filtering

## Requirements (Minimum)
- Deterministic replay or seeded generation
- Clear grading logic
- Documentation of failure modes tested
- Non-manipulable metric schema (platform-defined)

## Anti-Gaming Measures
- Hidden canary tasks
- Random perturbations
- Variance checks
- Minimum trial counts

## Review Process
1. Author submits suite pack
2. Automated checks + smoke runs
3. Human review for Certified/Reference tiers

## Marketplace Integration
Marketplaces should display:
- Suite tier
- Version hash
- Last verification timestamp
