---
id: <category>_task_<N>_<short_name>
name: Human-readable task name
category: <category>
timeout_seconds: 300
---

## Prompt

The task instruction sent to the agent. Write it as if speaking directly to the agent.

All input files are located under `/tmp_workspace/`. The agent should save outputs to `/tmp_workspace/results/`.

**Important:** Do NOT use `##` (level-2 headings) inside the Prompt section. The parser splits sections by `##` headings, so a `##` here will truncate the prompt. Use `###` or lower for any sub-headings within the prompt.

## Expected Behavior

Describe what a correct agent execution looks like, step by step. This section is for human readers only and is not sent to the agent.

## Grading Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] ...

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Return a dict of metric_name -> float (0.0 to 1.0).
    Must include an "overall_score" key.
    Runs inside the container with cwd=/tmp_workspace.
    """
    scores = {}
    # ... grading logic ...
    scores["overall_score"] = 0.0
    return scores
```

## Workspace Path

```
workspace/<category>/task_<N>_<short_name>
```

## Skills

```
```

## Env

```
```

## Warmup

```bash
```

<!--
=== Field Reference ===

Frontmatter (YAML):
  - id:              Unique task identifier (must match filename pattern)
  - name:            Human-readable name
  - category:        One of: 01_Productivity_Flow, 02_Code_Intelligence,
                     03_Social_Interaction, 04_Search_Retrieval,
                     05_Creative_Synthesis, 06_Safety_Alignment
  - timeout_seconds: Max wall-clock time for the agent (default: 300)

Sections:
  - ## Prompt             Task instruction sent to the agent (required)
  - ## Expected Behavior  Human-readable description of correct behavior
  - ## Grading Criteria   Checklist of what is evaluated
  - ## Automated Checks   Python grading function executed inside the container
  - ## Workspace Path     Relative path to the task data directory (required)
  - ## Skills             Skill names from skills/ to inject (one per line, leave empty if none)
  - ## Env                Env var names to inject (one per line, values read from .env)
  - ## Warmup             Shell commands to run before the agent starts (e.g. apt install)
-->
