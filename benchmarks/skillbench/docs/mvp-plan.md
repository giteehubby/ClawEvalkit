# MVP Plan: Skill Behavioral Profile

## Core Promise

> "Upload your skill to see how it behaves."

Users learn what their skill actually does - not through scores or benchmarks, but through a narrative that builds trust.

---

## The One Moment of Value

> "Oh — this is what my skill actually does."

Everything else is invisible scaffolding.

---

## User Flow

```
Upload → Running (~2 min) → Results
```

### Upload
- "Drop your skill here"
- Accept: SKILL.md or .zip (directory)
- Internally normalize to "skill package"

### Running
- "We'll run your skill in a few controlled scenarios and compare it to a baseline agent."
- No mention of benchmarks, suites, or eval philosophy

### Results
Single page with:

1. **Summary sentence** (human readable)
   > "This skill helped the agent fix arithmetic bugs it couldn't solve alone. No impact on other bug types."

2. **Behavioral bars** (Reliability, Efficiency)
   - Visual bars with small deltas (+10%, no change)
   - Numbers expandable, not default

3. **Three example cards**
   - "Here's a case where it helped"
   - "Here's where it didn't matter"
   - "Here's a failure mode we observed"

4. **Footer links** (for auditability)
   - "What this was tested on" → suite name, trial count, environment version
   - "View traces" → full execution logs
   - "Download scorecard.json" → machine-readable for marketplaces

---

## Auditability (Hidden but Available)

The methodology must be discoverable without being prominent.

When user sees "+10% reliability":
- Clickable disclosure: "Compared to a standard agent without this skill"
- Expandable: "Tested across N trials on Core Bugfix Suite v1"

Sophisticated users will look for the control condition. It must exist.

---

## What We Don't Ship (Yet)

- Suite marketplaces
- Multiple eval modes
- Public leaderboards
- Third-party attestations
- Badges or rankings
- Pricing

These are future affordances, not MVP requirements.

---

## Technical Requirements

### Results Page (Build First)
- HTML/CSS results page
- Summary generation from profile data
- Bar visualization for dimensions
- Example card rendering from traces
- Footer with metadata and download

### Agentic Adapter (Build Second)
For real skill evaluation, the adapter needs:
- Sandboxed file read/write
- Tool call interception/logging
- Step limit + timeout
- Deterministic-ish replay where applicable
- Trace emission with hashes

Not a full agent framework - a controlled loop that executes a skill and produces comparable logs.

### Upload Flow (Build Third)
- Simple drop zone
- SKILL.md or .zip handling
- Normalize to skill package
- Trigger evaluation pipeline

---

## Current Assets

From Phase 0:
- 10-task coding suite (swe-lite)
- CLI harness with run/infer/eval/compare
- Multi-dimensional profiling (reliability, efficiency, robustness, composability, legibility)
- Real pilot data: calc-fixer skill, +10% reliability delta

---

## Immediate Next Step

Build the results page using real pilot data:
- reports/real-agent-test.json (profile data)
- reports/tasks/augmented/swe-lite-001.json (helped example)
- reports/tasks/augmented/swe-lite-002.json (didn't matter example)

Create a static HTML page that embodies the UX. Iterate visually before wiring up the pipeline.

---

## Design Principles

1. **Calm over impressive** - Trustworthy by default
2. **Narrative over numbers** - Tell a story, not a scorecard
3. **Curious over judgmental** - "Here's what we observed" not "You scored 37%"
4. **Hidden complexity** - Scaffolding is invisible until needed
