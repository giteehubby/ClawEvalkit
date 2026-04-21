#!/usr/bin/env python3
"""
Generate LLM prompts for error classification on claweval glm-4.7 baseline failures.
Threshold: passed = False (score < 0.8 = failure)
Output: error_analysis/outputs/claweval_glm_prompts.json
"""

import json
import os
import glob
from pathlib import Path
import yaml

# Try tomllib (Python 3.11+), fall back to toml if available
try:
    import tomllib
except ImportError:
    try:
        import toml as tomllib
    except ImportError:
        tomllib = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "error_analysis" / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

FAILURE_THRESHOLD = 0.8  # score < 0.8 means failure
MODEL_DIR = "glm-4.7"


def load_claweval_tasks():
    """Load claweval task definitions."""
    tasks = {}
    base = PROJECT_ROOT / "benchmarks" / "claw-eval" / "tasks"

    for task_dir in base.iterdir():
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
        if toml_path.exists() and tomllib:
            try:
                with open(toml_path, "rb") as f:
                    metadata = tomllib.load(f)
            except Exception as e:
                print(f"Warning: Failed to load toml for {tid}: {e}")

        # Get category from task id prefix (e.g., C01zh -> user_agent type)
        category = metadata.get("task", {}).get("category", tid.split("_")[0] if "_" in tid else "unknown")

        # Try to load verifier/ grading info
        verifier_dir = task_dir / "verifier"
        rubric = ""
        if verifier_dir.exists():
            rubric_files = list(verifier_dir.glob("*.py"))
            if rubric_files:
                rubric = f"(Verifier files: {[str(f.name) for f in rubric_files]})"

        tasks[tid] = {
            "prompt": prompt,
            "category": category,
            "metadata": metadata,
            "rubric": rubric,
        }
    return tasks


def collect_failures():
    """Collect all claweval glm-4.7 failures (passed = False or score < 0.8)."""
    failures = []
    result_file = PROJECT_ROOT / "outputs" / "claweval" / f"{MODEL_DIR}.json"

    if not result_file.exists():
        print(f"Error: {result_file} not found")
        return failures

    try:
        data = json.load(open(result_file))
    except Exception as e:
        print(f"Error: Failed to load {result_file}: {e}")
        return failures

    details = data.get("details", [])
    for task_result in details:
        task_id = task_result.get("task_id", "")
        passed = task_result.get("passed", False)
        score = task_result.get("score", 0)

        if not passed or score < FAILURE_THRESHOLD:
            failures.append({
                "bench": "claweval",
                "task_id": task_id,
                "task_name": task_result.get("task_name", ""),
                "category": task_result.get("category", "unknown"),
                "difficulty": task_result.get("difficulty", "unknown"),
                "status": task_result.get("status", "unknown"),
                "score": score,
                "passed": passed,
                "completion": task_result.get("completion", 0),
                "robustness": task_result.get("robustness", 0),
                "communication": task_result.get("communication", 0),
                "safety": task_result.get("safety", 0),
                "wall_time_s": task_result.get("wall_time_s", 0),
                "judge_calls": task_result.get("judge_calls", 0),
                "turns": task_result.get("turns", 0),
                "dispatches": task_result.get("dispatches", 0),
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
        transcript_path = PROJECT_ROOT / "outputs" / "claweval" / "transcripts" / MODEL_DIR / tid / "transcript.json"
        if transcript_path.exists():
            try:
                transcript = transcript_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"Warning: Failed to load transcript for {tid}: {e}")
                transcript = ""

        if len(transcript) > MAX_TRANSCRIPT_LEN:
            transcript = transcript[:MAX_TRANSCRIPT_LEN] + "\n...[transcript truncated]"

        task_prompt = task_info.get("prompt", "")
        category = task_info.get("category", f.get("category", "unknown"))
        difficulty = f.get("difficulty", "unknown")
        rubric = task_info.get("rubric", "")

        scores_text = f"""Passed: {f['passed']}
Score: {f['score']}
Completion: {f['completion']}
Robustness: {f['robustness']}
Communication: {f['communication']}
Safety: {f['safety']}
Wall Time: {f['wall_time_s']:.1f}s
Judge Calls: {f['judge_calls']}
Turns: {f['turns']}
Dispatches: {f['dispatches']}"""

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

- **Benchmark**: claweval
- **Task ID**: {tid}
- **Task Name**: {f['task_name'] or 'N/A'}
- **Category**: {category}
- **Difficulty**: {difficulty}
- **Execution Status**: {f['status']}
- **Score**: {f['score']} (failure threshold: < 0.8)

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
            "category": category,
            "difficulty": difficulty,
            "task_id": tid,
            "task_name": f["task_name"],
            "status": f["status"],
            "score": f["score"],
            "passed": f["passed"],
            "prompt_for_llm": prompt_text,
            "transcript_path": str(transcript_path),
        })

    return prompts


def main():
    print("=" * 60)
    print("Claweval GLM-4.7 Error Classification Prompt Generator")
    print("=" * 60)

    print(f"\n[1/3] Loading claweval task definitions (threshold: score < {FAILURE_THRESHOLD})...")
    task_sources = load_claweval_tasks()
    print(f"  Loaded {len(task_sources)} task definitions")

    print(f"\n[2/3] Collecting failures (passed = False or score < {FAILURE_THRESHOLD})...")
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

    # Show category distribution
    cat_bins = Counter(f.get("category", "unknown") for f in failures)
    print("\n  Category distribution of failures:")
    for cat, count in cat_bins.most_common(10):
        print(f"    {cat}: {count}")

    print(f"\n[3/3] Building classification prompts...")
    prompts = build_prompts(failures, task_sources)
    print(f"  Generated {len(prompts)} prompts")

    # Save prompts
    out_path = OUTPUT_DIR / "claweval_glm_prompts.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    print(f"\nSaved prompts to: {out_path}")

    # Also save a summary CSV
    summary_path = OUTPUT_DIR / "claweval_glm_summary.csv"
    with open(summary_path, "w") as f:
        f.write("task_id,task_name,category,difficulty,status,score,passed\n")
        for p in prompts:
            task_name = (p.get("task_name") or "").replace(",", ";").replace("\n", " ")[:100]
            f.write(f"{p['task_id']},{task_name},{p.get('category','unknown')},{p.get('difficulty','unknown')},{p['status']},{p['score']},{p.get('passed', False)}\n")
    print(f"Saved summary to: {summary_path}")

    print("\n" + "=" * 60)
    print("Done! Next step: run classification via LLM")
    print("=" * 60)


if __name__ == "__main__":
    main()