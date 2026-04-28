#!/usr/bin/env python3
"""
Generate LLM prompts for error classification on clawbench-official glm-4.7 baseline failures.
Threshold: passed = False (score < 1.0 = failure)
Output: error_analysis/outputs/clawbench_glm_prompts.json
"""

import json
import os
import glob
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "error_analysis" / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

MODEL_DIR = "glm-4.7"


def load_clawbench_tasks():
    """Load clawbench task definitions."""
    tasks = {}
    base = PROJECT_ROOT / "benchmarks" / "claw-bench" / "tasks"

    for domain_dir in base.iterdir():
        if not domain_dir.is_dir():
            continue
        domain = domain_dir.name
        for task_dir in domain_dir.iterdir():
            if not task_dir.is_dir():
                continue
            tid = task_dir.name

            # Load instruction.md
            instruction_path = task_dir / "instruction.md"
            prompt = ""
            if instruction_path.exists():
                prompt = instruction_path.read_text(encoding="utf-8").strip()

            # Load task.toml for metadata
            metadata = {}
            toml_path = task_dir / "task.toml"
            if toml_path.exists():
                try:
                    import toml
                    metadata = toml.load(toml_path)
                except:
                    pass

            # Try to load grader.py as rubric reference
            grader_path = task_dir / "grader.py"
            rubric = ""
            if grader_path.exists():
                rubric = f"(Grader: {grader_path.read_text(encoding='utf-8')[:2000]}...)"

            tasks[tid] = {
                "prompt": prompt,
                "domain": domain,
                "level": metadata.get("task", {}).get("level", "unknown"),
                "tags": metadata.get("task", {}).get("tags", []),
                "rubric": rubric,
                "task_yaml": str(task_dir / "task.yaml") if (task_dir / "task.yaml").exists() else "",
            }
    return tasks


def collect_failures():
    """Collect all clawbench glm-4.7 failures (passed = False)."""
    failures = []
    result_dir = PROJECT_ROOT / "outputs" / "clawbench-official" / MODEL_DIR

    if not result_dir.exists():
        print(f"Error: {result_dir} not found")
        return failures

    for result_file in result_dir.glob("*.json"):
        try:
            data = json.load(open(result_file))
        except Exception as e:
            print(f"Warning: Failed to load {result_file}: {e}")
            continue

        task_id = result_file.stem  # filename without .json
        passed = data.get("passed", False)
        score = data.get("score", 0)

        if not passed and score < 0.9:  # Failure: passed=False AND score<0.9
            failures.append({
                "bench": "clawbench",
                "task_id": task_id,
                "status": data.get("status", "unknown"),
                "score": score,
                "checks_passed": data.get("checks_passed", 0),
                "checks_total": data.get("checks_total", 0),
                "error": data.get("error", ""),
                "details": data.get("details", ""),
                "result_file": str(result_file),
            })
    return failures


def build_prompts(failures, task_sources):
    """Build classification prompts for each failure."""
    prompts = []
    MAX_TRANSCRIPT_LEN = 30000

    for f in failures:
        tid = f["task_id"]
        task_info = task_sources.get(tid, {})

        # Load transcript
        transcript = ""
        transcript_path = PROJECT_ROOT / "outputs" / "clawbench-official" / "transcripts" / MODEL_DIR / tid / "transcript.json"
        if transcript_path.exists():
            try:
                transcript = transcript_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"Warning: Failed to load transcript for {tid}: {e}")
                transcript = ""

        if len(transcript) > MAX_TRANSCRIPT_LEN:
            transcript = transcript[:MAX_TRANSCRIPT_LEN] + "\n...[transcript truncated]"

        task_prompt = task_info.get("prompt", "")
        domain = task_info.get("domain", "unknown")
        level = task_info.get("level", "unknown")
        tags = task_info.get("tags", [])
        rubric = task_info.get("rubric", "")

        scores_text = f"""Passed: {f['checks_passed']}/{f['checks_total']} checks
Overall Score: {f['score']} (threshold: 1.0 for pass)
Error: {f['error'] or 'N/A'}
Details: {f['details'] or 'N/A'}"""

        prompt_text = f"""You are an expert evaluator classifying agent failures into one of six categories.

## Classification Categories

**A. Task Understanding / Planning Drift**
The agent misunderstood the task requirements, missed key constraints, pursued wrong sub-goals, or produced a plan that diverged from what was asked.

**B. Tool / Environment Grounding Failure**
The agent used tools incorrectly, called non-existent tools, passed wrong parameters, accessed wrong file paths, or failed to interact with the environment properly.

**C. Memory / State Management Failure**
The agent lost track of context, forgot earlier information, made contradictory statements across steps, or failed to maintain consistency in multi-step execution.

**D. Verification / Recovery Deficiency**
The agent did not verify its outputs, ignored error messages, repeated the same failed strategy without diagnosing the issue, or failed to recover when given the opportunity.

**E. Long-tail Procedural Knowledge / Skill Execution Deficiency**
The agent lacked the specific domain knowledge, coding skill, or procedural expertise needed to complete the task correctly. This includes situations where the agent could not figure out the right approach even with available tools.

**F. Other / Mixed**
The failure does not fit the above categories clearly, or is caused by external factors (infrastructure issues, timeout, ambiguous task definition, or mixed root causes).

---

## Task Metadata

- **Benchmark**: clawbench
- **Domain**: {domain}
- **Level**: {level}
- **Tags**: {', '.join(tags) if tags else 'N/A'}
- **Task ID**: {tid}
- **Execution Status**: {f['status']}
- **Score**: {f['score']} (pass threshold: 1.0)

## Score Breakdown

{scores_text}

---

## Task Prompt / Instruction

{task_prompt if task_prompt else '(task prompt not available)'}

---

## Agent Execution Trajectory

{transcript if transcript else '(transcript not available)'}

---

## Grading Rubric / Expected Behavior

{rubric if rubric else '(no explicit rubric available)'}

---

## Classification Task

Analyze the task prompt, the agent's execution trajectory, and the score breakdown above.

First, identify the key failure points in the agent's behavior:
1. What was the agent trying to accomplish?
2. Where did it first go wrong?
3. What category best explains this failure?

Then output your final classification as a single uppercase letter wrapped in \\boxed{{}}.

**Important**: If multiple categories contributed to the failure, choose the one that represents the **earliest/root cause** in the causal chain.

Examples:
- If the agent misunderstood the task AND used wrong tools → choose A (task understanding is the root cause)
- If the agent knew what to do but used the wrong file path → choose B
- If the agent forgot what it found earlier → choose C
- If the agent ignored error messages and kept retrying the same approach → choose D
- If the agent simply did not know the right procedure/domain knowledge → choose E
- If unclear or multiple equal causes → choose F

Output: \\boxed{{X}} where X is A, B, C, D, E, or F
"""

        prompts.append({
            "bench": f["bench"],
            "domain": domain,
            "level": level,
            "tags": tags,
            "task_id": tid,
            "status": f["status"],
            "score": f["score"],
            "prompt_for_llm": prompt_text,
            "transcript_path": str(transcript_path),
            "error": f["error"],
        })

    return prompts


def main():
    print("=" * 60)
    print("Clawbench GLM-4.7 Error Classification Prompt Generator")
    print("=" * 60)

    print("\n[1/3] Loading clawbench task definitions...")
    task_sources = load_clawbench_tasks()
    print(f"  Loaded {len(task_sources)} task definitions")

    print(f"\n[2/3] Collecting failures (passed = False)...")
    failures = list(collect_failures())
    print(f"  Found {len(failures)} failures")

    # Show score distribution
    from collections import Counter
    score_bins = Counter()
    for f in failures:
        score = f["score"]
        if score < 0.4:
            score_bins["0.0-0.4"] += 1
        elif score < 0.6:
            score_bins["0.4-0.6"] += 1
        elif score < 0.8:
            score_bins["0.6-0.8"] += 1
        else:
            score_bins["0.8-1.0"] += 1
    print("\n  Score distribution of failures:")
    for bin_name in ["0.0-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]:
        print(f"    {bin_name}: {score_bins.get(bin_name, 0)}")

    print(f"\n[3/3] Building classification prompts...")
    prompts = build_prompts(failures, task_sources)
    print(f"  Generated {len(prompts)} prompts")

    # Save prompts
    out_path = OUTPUT_DIR / "clawbench_glm_prompts.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    print(f"\nSaved prompts to: {out_path}")

    # Also save a summary CSV
    summary_path = OUTPUT_DIR / "clawbench_glm_summary.csv"
    with open(summary_path, "w") as f:
        f.write("task_id,domain,level,status,score,error\n")
        for p in prompts:
            error = (p.get("error") or "").replace(",", ";").replace("\n", " ")[:100]
            f.write(f"{p['task_id']},{p.get('domain','unknown')},{p.get('level','unknown')},{p['status']},{p['score']},{error}\n")
    print(f"Saved summary to: {summary_path}")

    print("\n" + "=" * 60)
    print("Done! Next step: run classification via LLM")
    print("=" * 60)


if __name__ == "__main__":
    main()