#!/usr/bin/env python3
"""
Generate LLM prompts for error classification on agentbench glm-4.7 baseline failures.
Threshold: overall_score < 80 = failure
Output: error_analysis/outputs/agentbench_glm_prompts.json
"""

import json
import os
import glob
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "error_analysis" / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

FAILURE_THRESHOLD = 80  # overall_score < 80 means failure
MODEL_DIR = "glm-4.7"


def load_agentbench_tasks():
    """Load agentbench task definitions."""
    tasks = {}
    base = PROJECT_ROOT / "benchmarks/agentbench-openclaw/tasks"
    if not base.exists():
        print(f"Warning: {base} not found")
        return tasks

    for yaml_path in base.rglob("task.yaml"):
        data = yaml.safe_load(open(yaml_path))
        tid = yaml_path.parent.name
        category = yaml_path.parent.parent.name  # e.g. "data-analysis" from "tasks/data-analysis/cross-reference/task.yaml"
        prompt = (data.get("user_message") or "").strip()
        if not prompt and data.get("turns"):
            turn_msgs = []
            for turn in data["turns"]:
                if turn.get("role") == "user" and turn.get("message"):
                    turn_msgs.append(turn["message"].strip())
            prompt = "\n\n".join(turn_msgs)
        if not prompt and data.get("input_files"):
            input_files = data.get("input_files")
            if isinstance(input_files, list) and input_files:
                first_input = input_files[0].get("name") if isinstance(input_files[0], dict) else input_files[0]
                prompt = f"(Task uses input file: {first_input})"
        tasks[tid] = {
            "prompt": prompt,
            "description": (data.get("description") or "").strip(),
            "rubric": json.dumps(data.get("scoring") or {}, ensure_ascii=False, indent=2),
            "category": category,
        }
    return tasks


def collect_failures():
    """Collect all agentbench glm-4.7 failures (score < 80)."""
    failures = []
    result_dir = PROJECT_ROOT / "outputs" / "agentbench" / MODEL_DIR

    if not result_dir.exists():
        print(f"Error: {result_dir} not found")
        return failures

    for task_dir in result_dir.iterdir():
        if not task_dir.is_dir():
            continue
        result_file = task_dir / "result.json"
        if not result_file.exists():
            continue

        data = json.load(open(result_file))
        scores = data.get("scores", {})
        overall = scores.get("overall_score", 0)
        status = data.get("status", "")

        task_id = task_dir.name
        failures.append({
            "bench": "agentbench",
            "task_id": task_id,
            "status": status,
            "score": overall,
            "scores": scores,
            "judge_breakdown": data.get("judge_breakdown", {}),
            "result_file": str(result_file),
            "agent_result_file": str(task_dir / "agent_result.json"),
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
        transcript_path = f["agent_result_file"]
        if os.path.exists(transcript_path):
            try:
                d = json.load(open(transcript_path))
                t = d.get("transcript", [])
                transcript = json.dumps(t, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Warning: Failed to load transcript for {tid}: {e}")
                transcript = ""

        if len(transcript) > MAX_TRANSCRIPT_LEN:
            transcript = transcript[:MAX_TRANSCRIPT_LEN] + "\n...[transcript truncated]"

        task_prompt = task_info.get("prompt", "")
        rubric = task_info.get("rubric", "")
        description = task_info.get("description", "")
        category = task_info.get("category", "unknown")

        # Build detailed scores section
        scores = f.get("scores", {})
        judge_breakdown = f.get("judge_breakdown", {})

        scores_text = f"""L0 Score: {scores.get('l0_score', 'N/A')}
L1 Score: {scores.get('l1_score', 'N/A')}
L2 Score: {scores.get('l2_score', 'N/A')}
L3 Score: {scores.get('l3_score', 'N/A')}
Overall Score: {f['score']}"""

        if judge_breakdown:
            scores_text += "\n\nJudge Breakdown:"
            scores_text += f"\n{json.dumps(judge_breakdown, ensure_ascii=False, indent=2)}"

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

- **Benchmark**: agentbench
- **Category**: {category}
- **Task ID**: {tid}
- **Description**: {description or 'N/A'}
- **Execution Status**: {f['status']}
- **Overall Score**: {f['score']} / 100 (threshold for failure: < 80)

## Score Breakdown

{scores_text}

---

## Task Prompt / Instruction

{task_prompt if task_prompt else '(task prompt not available)'}

---

## Agent Execution Trajectory

{transcript if transcript else '(transcript not available)'}

---

## Grading Rubric

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
            "category": category,
            "task_id": tid,
            "status": f["status"],
            "score": f["score"],
            "prompt_for_llm": prompt_text,
            "transcript_path": transcript_path,
            "description": description,
        })

    return prompts


def main():
    print("=" * 60)
    print("AgentBench GLM-4.7 Error Classification Prompt Generator")
    print("=" * 60)

    print("\n[1/3] Loading agentbench task definitions...")
    task_sources = load_agentbench_tasks()
    print(f"  Loaded {len(task_sources)} task definitions")

    print(f"\n[2/3] Collecting failures (score < {FAILURE_THRESHOLD})...")
    failures = []
    for f in collect_failures():
        if f["score"] < FAILURE_THRESHOLD:
            failures.append(f)
    print(f"  Found {len(failures)} failures out of 40 tasks")

    # Show score distribution
    from collections import Counter
    score_bins = Counter()
    for f in failures:
        score = f["score"]
        if score < 20:
            score_bins["0-20"] += 1
        elif score < 40:
            score_bins["20-40"] += 1
        elif score < 60:
            score_bins["40-60"] += 1
        elif score < 80:
            score_bins["60-80"] += 1
    print("\n  Score distribution of failures:")
    for bin_name in ["0-20", "20-40", "40-60", "60-80"]:
        print(f"    {bin_name}: {score_bins.get(bin_name, 0)}")

    print(f"\n[3/3] Building classification prompts...")
    prompts = build_prompts(failures, task_sources)
    print(f"  Generated {len(prompts)} prompts")

    # Save prompts
    out_path = OUTPUT_DIR / "agentbench_glm_prompts.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    print(f"\nSaved prompts to: {out_path}")

    # Also save a summary CSV
    summary_path = OUTPUT_DIR / "agentbench_glm_summary.csv"
    with open(summary_path, "w") as f:
        f.write("task_id,category,status,score,description\n")
        for p in prompts:
            desc = p.get("description", "").replace(",", ";").replace("\n", " ")[:100]
            f.write(f"{p['task_id']},{p.get('category','unknown')},{p['status']},{p['score']},{desc}\n")
    print(f"Saved summary to: {summary_path}")

    print("\n" + "=" * 60)
    print("Done! Next step: run classification via LLM")
    print("=" * 60)


if __name__ == "__main__":
    main()
