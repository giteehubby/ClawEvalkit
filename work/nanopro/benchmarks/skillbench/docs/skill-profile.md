# Skill Profile (Draft)

This document defines the profile schema used to describe how a skill changes agent behavior.
Profiles are **multi-dimensional** and compare **baseline vs augmented** runs.

## Core Dimensions

### 1) Reliability
Measures whether a skill makes the agent succeed more consistently.
- Success rate delta (baseline vs augmented)
- Failure variance across trials (optional)
- Partial completion rate (optional)

### 2) Efficiency
Measures resource cost and wasted motion.
- Avg runtime delta
- Avg steps / tool calls delta (future)
- Token cost delta (future)

### 3) Robustness
Measures performance under perturbation and noise.
- Success rate delta under injected tool failures
- Drawdown under noisy inputs (domain-specific)

### 4) Composability
Measures whether skill plays nicely with other skills.
- State leakage detection (future)
- Tool override conflicts (future)

### 5) Failure Legibility
Measures how easy it is to understand failures.
- Presence of structured error outputs
- Clear error vs silent failure rates

## Output Example
```json
{
  "skill": "calc-fixer",
  "task_pack": "coding/swe-lite@0.0.1",
  "profile": {
    "reliability": {
      "success_rate": { "baseline": 0.33, "augmented": 0.67, "delta": 0.34 }
    },
    "efficiency": {
      "avg_runtime_s": { "baseline": 0.030, "augmented": 0.028, "delta": -0.002 }
    },
    "robustness": {
      "tool_failure": { "baseline": 0.4, "augmented": 0.6, "delta": 0.2 }
    },
    "composability": {
      "avg_skill_count": { "baseline": 1.0, "augmented": 2.0, "delta": 1.0 },
      "max_skill_count": { "baseline": 1, "augmented": 2, "delta": 1 },
      "multi_skill": { "baseline": false, "augmented": true, "delta": null }
    },
    "failure_legibility": {
      "explicit_error_rate": { "baseline": 0.5, "augmented": 0.9, "delta": 0.4 },
      "silent_failure_rate": { "baseline": 0.5, "augmented": 0.1, "delta": -0.4 }
    }
  }
}
```

## Notes
- Profiles should be derived from **repeatable harness metrics**, not manual judgment.
- Domains can extend the schema with additional fields (e.g., finance, docs).
