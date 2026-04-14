#!/usr/bin/env python3
"""Generate LLM prompts for error classification from failed agent traces."""

import json
import os
import glob
from pathlib import Path
import yaml

# Resolve project root relative to this script (scripts/ -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# =====================
# Load benchmark tasks
# =====================

def load_agentbench_tasks():
    tasks = {}
    base = PROJECT_ROOT / "benchmarks/agentbench-openclaw/tasks"
    for yaml_path in base.rglob("task.yaml"):
        data = yaml.safe_load(open(yaml_path))
        # Directory name matches output task_id; yaml "id" may differ
        tid = yaml_path.parent.name
        prompt = (data.get("user_message") or "").strip()
        # For multi-turn tasks, concatenate turn messages
        if not prompt and data.get("turns"):
            turn_msgs = []
            for turn in data["turns"]:
                if turn.get("role") == "user" and turn.get("message"):
                    turn_msgs.append(turn["message"].strip())
            prompt = "\n\n".join(turn_msgs)
        # Some agentbench tasks reference input files for the actual prompt
        if not prompt and data.get("input_files"):
            input_files = data.get("input_files")
            if isinstance(input_files, list) and input_files:
                first_input = input_files[0].get("name") if isinstance(input_files[0], dict) else input_files[0]
                prompt = f"(Task uses input file: {first_input})"
        tasks[tid] = {
            "prompt": prompt,
            "description": (data.get("description") or "").strip(),
            "rubric": json.dumps(data.get("scoring") or {}, ensure_ascii=False, indent=2),
        }
    return tasks


def load_clawbench_tasks():
    tasks = {}
    base = PROJECT_ROOT / "benchmarks/claw-bench/tasks"
    import tomli
    for toml_path in base.rglob("task.toml"):
        with open(toml_path, "rb") as f:
            raw = tomli.load(f)
        if "task" in raw:
            raw = {**raw.pop("task"), **raw}
        tid = raw.get("id", toml_path.parent.name)
        instruction = ""
        inst_path = toml_path.parent / "instruction.md"
        if inst_path.exists():
            instruction = inst_path.read_text().strip()
        tasks[tid] = {
            "prompt": instruction,
            "description": raw.get("title", ""),
            "rubric": "",
        }
    return tasks


def load_claweval_tasks():
    tasks = {}
    base = PROJECT_ROOT / "benchmarks/claw-eval/tasks"
    for task_dir in base.iterdir():
        if not task_dir.is_dir():
            continue
        yaml_path = task_dir / "task.yaml"
        if not yaml_path.exists():
            continue
        data = yaml.safe_load(open(yaml_path))
        tid = data.get("task_id", task_dir.name)
        prompt_text = ""
        if data.get("prompt"):
            prompt_text = data["prompt"].get("text", "")
        rubric = data.get("judge_rubric", "")
        tasks[tid] = {
            "prompt": prompt_text.strip(),
            "description": data.get("task_name", ""),
            "rubric": rubric.strip() if rubric else "",
        }
    return tasks


def load_pinchbench_tasks():
    tasks = {}
    base = PROJECT_ROOT / "benchmarks/pinchbench/tasks"
    import re
    for md_path in base.glob("*.md"):
        if md_path.name.startswith("_") or md_path.name.startswith("TASK_TEMPLATE"):
            continue
        content = md_path.read_text()
        fm = {}
        m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if m:
            fm = yaml.safe_load(m.group(1))
        prompt = ""
        pm = re.search(r"## Prompt\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
        if pm:
            prompt = pm.group(1).strip()
        rubric = ""
        rm = re.search(r"## LLM Judge Rubric.*?```.*?```", content, re.DOTALL)
        if not rm:
            rm = re.search(r"## Automated Checks.*?```python\s*\n(.*?)```", content, re.DOTALL)
        if rm:
            rubric = rm.group(0).strip()[:2000]
        tid = fm.get("id", md_path.stem)
        tasks[tid] = {
            "prompt": prompt,
            "description": fm.get("name", ""),
            "rubric": rubric,
        }
    return tasks


def load_skillsbench_tasks():
    tasks = {}
    base = PROJECT_ROOT / "benchmarks/skillsbench/tasks"
    for task_dir in base.iterdir():
        if not task_dir.is_dir():
            continue
        inst_path = task_dir / "instruction.md"
        if not inst_path.exists():
            continue
        tid = task_dir.name
        tasks[tid] = {
            "prompt": inst_path.read_text().strip(),
            "description": "",
            "rubric": "",
        }
    return tasks


def load_zclawbench_tasks():
    tasks = {}
    path = PROJECT_ROOT / "benchmarks/zclawbench/zclawbench.jsonl"
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                tid = row["task_id"]
                traj = json.loads(row["trajectory"]) if isinstance(row.get("trajectory"), str) else row.get("trajectory", [])
                prompt = ""
                for msg in traj:
                    if msg.get("role") == "user":
                        for c in msg.get("content", []):
                            if isinstance(c, dict) and c.get("type") == "text":
                                prompt = c.get("text", "")
                                break
                        if prompt:
                            break
                tasks[tid] = {
                    "prompt": prompt.strip(),
                    "description": "",
                    "rubric": "",
                }
    return tasks


# =====================
# Collect failures
# =====================

THRESHOLDS = {
    "agentbench": 70,
    "clawbench-official": 0.7,
    "claweval": 0.7,
    "pinchbench": 0.7,
    "skillsbench": 70,
    "zclawbench": 0.7,
}


def score_below_threshold(bench, score):
    """Return True if the failure score is below the benchmark-specific threshold."""
    thresh = THRESHOLDS.get(bench, 0)
    return score < thresh


def collect_failures():
    failures = []

    # agentbench
    for f in glob.glob(str(PROJECT_ROOT / "outputs/agentbench/minimax-m2.7/*/result.json")):
        data = json.load(open(f))
        scores = data.get("scores", {})
        overall = scores.get("overall_score", 0)
        status = data.get("status", "")
        if status != "success" or overall < 95:
            task_id = data.get("task_id", os.path.basename(os.path.dirname(f)))
            failures.append({"bench": "agentbench", "task_id": task_id, "status": status, "score": overall, "result_file": f})

    # clawbench-official
    d = json.load(open(PROJECT_ROOT / "outputs/clawbench-official/result.json"))
    for r in d.get("details", []):
        if not r.get("passed"):
            failures.append({"bench": "clawbench-official", "task_id": r["task_id"], "status": "failed", "score": r.get("score", 0), "result_file": None})

    # claweval
    d = json.load(open(PROJECT_ROOT / "outputs/claweval/glm-4.7.json"))
    for r in d.get("details", []):
        if r.get("passed") is False:
            failures.append({"bench": "claweval", "task_id": r["task_id"], "status": r.get("status", "failed"), "score": r.get("score", 0), "result_file": None})

    # pinchbench
    d = json.load(open(PROJECT_ROOT / "outputs/pinchbench/result.json"))
    for r in d.get("details", []):
        if r.get("mean", 1) < 0.95:
            failures.append({"bench": "pinchbench", "task_id": r["task_id"], "status": "failed", "score": r.get("mean", 0), "result_file": None})

    # skillsbench
    d = json.load(open(PROJECT_ROOT / "outputs/skillsbench/minimax-m2.7.json"))
    for r in d.get("results", []):
        if r.get("status") != "passed":
            failures.append({"bench": "skillsbench", "task_id": r["task"], "status": r.get("status", "unknown"), "score": 0, "result_file": None})

    # zclawbench
    d = json.load(open(PROJECT_ROOT / "outputs/zclawbench/minimax-m2.7.json"))
    for r in d.get("details", []):
        scores = r.get("scores", {})
        overall = scores.get("overall_score", 0)
        status = r.get("status", "")
        if status != "success" or overall < 0.95:
            failures.append({"bench": "zclawbench", "task_id": r["task_id"], "status": status, "score": overall, "result_file": None})

    return failures


# =====================
# Build prompts
# =====================

def build_prompts(failures, task_sources):
    prompts = []
    MAX_TRANSCRIPT_LEN = 32000

    for f in failures:
        bench = f["bench"]
        tid = f["task_id"]
        if f["status"] == "error":
            continue

        # Filter out high-score failures
        if not score_below_threshold(bench, f["score"]):
            continue

        task_info = task_sources[bench].get(tid, {})

        # Load transcript
        transcript = ""
        transcript_path = None
        if bench == "agentbench":
            p = PROJECT_ROOT / f"outputs/agentbench/minimax-m2.7/{tid}/agent_result.json"
            if p.exists():
                d = json.load(open(p))
                t = d.get("transcript", [])
                transcript = json.dumps(t, ensure_ascii=False, indent=2)
                transcript_path = str(p)
        elif bench == "clawbench-official":
            p = PROJECT_ROOT / f"outputs/clawbench-official/transcripts/minimax-m2.7/{tid}/transcript.json"
            if p.exists():
                t = json.load(open(p))
                transcript = json.dumps(t, ensure_ascii=False, indent=2)
                transcript_path = str(p)
        elif bench == "claweval":
            p = PROJECT_ROOT / f"outputs/claweval/transcripts/glm-4.7/{tid}/transcript.json"
            if p.exists():
                t = json.load(open(p))
                transcript = json.dumps(t, ensure_ascii=False, indent=2)
                transcript_path = str(p)
        elif bench == "pinchbench":
            p = PROJECT_ROOT / f"outputs/pinchbench/transcripts/minimax-m2.7/{tid}/transcript.json"
            if p.exists():
                t = json.load(open(p))
                transcript = json.dumps(t, ensure_ascii=False, indent=2)
                transcript_path = str(p)
        elif bench == "skillsbench":
            p = PROJECT_ROOT / f"outputs/skillsbench/transcripts/minimax-m2.7/{tid}/transcript.json"
            if p.exists():
                t = json.load(open(p))
                transcript = json.dumps(t, ensure_ascii=False, indent=2)
                transcript_path = str(p)
        elif bench == "zclawbench":
            p = PROJECT_ROOT / f"outputs/zclawbench/minimax-m2.7/{tid}/agent_result.json"
            if p.exists():
                d = json.load(open(p))
                t = d.get("transcript", [])
                transcript = json.dumps(t, ensure_ascii=False, indent=2)
                transcript_path = str(p)

        if len(transcript) > MAX_TRANSCRIPT_LEN:
            transcript = transcript[:MAX_TRANSCRIPT_LEN] + "\n...[truncated]"

        task_prompt = task_info.get("prompt", "")
        rubric = task_info.get("rubric", "")

        prompt_text = (
            "You are an expert evaluator classifying agent failures into one of six categories.\n\n"
            "Classification categories:\n"
            "A. Task understanding / planning drift — The agent misunderstood the task requirements, missed constraints, or produced a plan that diverged from what was asked.\n"
            "B. Tool / environment grounding failure — The agent used tools incorrectly, called non-existent tools, passed wrong parameters, or failed to interact with the environment properly.\n"
            "C. Memory / state management failure — The agent lost track of context, forgot earlier information, or failed to maintain consistency across multi-step execution.\n"
            "D. Verification / recovery deficiency — The agent did not verify its outputs, ignored errors, or failed to recover from a mistake when given the opportunity.\n"
            "E. Long-tail procedural knowledge / skill execution deficiency — The agent lacked the specific domain knowledge or coding skill needed to complete the task correctly.\n"
            "F. 其他 — The failure does not fit the above categories, or is caused by external factors (e.g., infrastructure, timeout, unclear prompt).\n\n"
            "【Task Metadata】\n"
            f"Benchmark: {bench}\n"
            f"Task ID: {tid}\n"
            f"Execution Status: {f['status']}\n"
            f"Score: {f['score']}\n\n"
            "【Task Prompt / Instruction】\n"
            f"{task_prompt}\n\n"
            "【Agent Execution Trajectory】\n"
            f"{transcript if transcript else '(transcript not available)'}\n\n"
            "【Grading Rubric / Criteria】\n"
            f"{rubric if rubric else '(no explicit rubric available)'}\n\n"
            "---\n"
            "Based on the task prompt and the agent's execution trajectory, first analyze the failure step by step, then classify it into one of the six categories above. "
            "Output your final answer as a single uppercase letter wrapped in \\boxed{}, for example \\boxed{A} or \\boxed{F}.\n"
        )
        prompts.append({
            "bench": bench,
            "task_id": tid,
            "status": f["status"],
            "score": f["score"],
            "prompt_for_llm": prompt_text,
            "transcript_path": transcript_path,
        })

    return prompts


def main():
    print("Loading benchmark tasks...")
    task_sources = {
        "agentbench": load_agentbench_tasks(),
        "clawbench-official": load_clawbench_tasks(),
        "claweval": load_claweval_tasks(),
        "pinchbench": load_pinchbench_tasks(),
        "skillsbench": load_skillsbench_tasks(),
        "zclawbench": load_zclawbench_tasks(),
    }
    for bench, tasks in task_sources.items():
        print(f"  {bench}: {len(tasks)} tasks loaded")

    print("\nCollecting failures...")
    failures = collect_failures()
    print(f"  Total failures: {len(failures)}")

    print("\nBuilding prompts (excluding error status and high-score failures)...")
    prompts = build_prompts(failures, task_sources)
    print(f"  Prompts generated: {len(prompts)}")

    from collections import Counter
    c = Counter(p["bench"] for p in prompts)
    for bench, count in c.items():
        print(f"    {bench}: {count}")

    out_path = PROJECT_ROOT / "outputs/error_classification_prompts.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    print(f"\nSaved prompts to {out_path}")


if __name__ == "__main__":
    main()
