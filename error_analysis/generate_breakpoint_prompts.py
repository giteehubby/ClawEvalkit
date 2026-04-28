#!/usr/bin/env python3
"""
生成 H3 断点标注 prompt：对 A/B/D 类失败轨迹标注控制闭环断裂位置。

控制闭环三段：
  - Goal Grounding (GG)：任务目标理解/规划阶段
  - Action Instantiation (AI)：工具调用/参数/路径落地阶段
  - Outcome Verification (OV)：结果验证/错误恢复阶段

输出：error_analysis/outputs/breakpoint_prompts.json
用法：
  python error_analysis/generate_breakpoint_prompts.py
  python scripts/run_error_classification.py --input error_analysis/outputs/breakpoint_prompts.json --output error_analysis/outputs/breakpoint_results.json
"""

import json
import os
import re
import glob
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "error_analysis" / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)
MODEL_DIR = "glm-4.7"

MAX_TRANSCRIPT_LEN = 30000

# ── 断点定义 ──────────────────────────────────────────────

BREAKPOINT_DEFINITIONS = """
## Breakpoint Definitions (Control Loop)

The agent control loop has three stages. Identify where the **first critical break** occurs:

**GG — Goal Grounding Break**
The agent fundamentally misunderstood the task goal, misinterpreted constraints, or produced a plan that diverges from what was asked. The failure originates *before* any tool is called — the agent never had the right intention.

Diagnostic signals:
- Task prompt mentions constraint X, but agent never acknowledges it
- Agent's first action is already targeting a wrong sub-goal
- Agent plan omits a key requirement stated in the prompt

**AI — Action Instantiation Break**
The agent correctly understood *what* to do, but failed to translate that intention into the right tool call, parameters, file path, or output format. The failure is at the *execution interface*, not at the planning level.

Diagnostic signals:
- Agent states correct intent ("I need to read config.json") but calls wrong path/tool
- Agent uses correct tool but with malformed parameters
- Agent produces right logic but wrong output format (e.g., CSV vs JSON)

**OV — Outcome Verification Break**
The agent executed actions correctly, but after encountering an error or producing output, it failed to verify, diagnose, or recover. The agent continued with a wrong result or repeated the same failed approach.

Diagnostic signals:
- Tool returned error, agent ignored it and continued
- Agent produced output but never checked if it matched requirements
- Agent repeated same failed action >2 times without diagnosis
- Agent could have self-corrected with a simple verification step but didn't

---

## Decision Rules

1. **Causal chain priority**: If the root cause is in GG and it cascades to AI/OV errors, annotate GG.
2. **Earliest break wins**: If GG is fine but AI fails (and OV never gets a chance), annotate AI.
3. **GG + AI both fine, but no verification**: annotate OV.
4. **If truly ambiguous between two stages**, choose the earlier one.
"""

PROMPT_TEMPLATE = """You are an expert evaluator annotating **where** in the agent control loop a failure first breaks.

{BREAKPOINT_DEFINITIONS}

---

## Task Metadata

- **Benchmark**: {bench}
- **Original Error Category**: {error_category} ({error_category_name})
- **Task ID**: {task_id}
- **Description**: {description}

## Task Prompt / Instruction

{task_prompt}

---

## Agent Execution Trajectory

{transcript}

---

## Annotation Task

Analyze the agent's trajectory step by step:

1. **Goal check**: Did the agent correctly understand the task? What was the task asking, and what did the agent think it should do?
2. **Action check**: When the agent started executing, were tool calls, parameters, and paths correct given its stated intention?
3. **Verification check**: After actions, did the agent verify results and recover from errors?

Then identify the **earliest critical break** in the control loop.

**Important**:
- Focus on the FIRST point where things went wrong structurally
- If the agent misunderstood the task from the start → GG
- If the agent understood the task but executed incorrectly → AI
- If the agent executed correctly but never verified/recovered → OV

Output: \\boxed{{X}} where X is GG, AI, or OV

Also provide a brief rationale (1-2 sentences) after the boxed answer."""


# ── 数据加载 ──────────────────────────────────────────────

def load_failure_categories():
    """从现有分类结果加载 A/B/D 类失败任务"""
    path = OUTPUT_DIR / "failure_categories_by_group.json"
    if not path.exists():
        print(f"Error: {path} not found. Run error classification first.")
        return {}

    with open(path) as f:
        data = json.load(f)

    result = {}
    for cat in ["A", "B", "D"]:
        items = data["by_category"].get(cat, [])
        result[cat] = items

    return result


def load_task_source(bench, task_id):
    """加载任务的原始 prompt/描述"""
    source = {"prompt": "", "description": "", "category": ""}

    if bench == "agentbench":
        yaml_path = PROJECT_ROOT / f"benchmarks/agentbench-openclaw/tasks/**/{task_id}/task.yaml"
        matches = list(PROJECT_ROOT.glob(f"benchmarks/agentbench-openclaw/tasks/**/{task_id}/task.yaml"))
        if matches:
            import yaml
            data = yaml.safe_load(open(matches[0]))
            source["prompt"] = (data.get("user_message") or "").strip()
            if not source["prompt"] and data.get("turns"):
                msgs = [t["message"].strip() for t in data["turns"] if t.get("role") == "user" and t.get("message")]
                source["prompt"] = "\n\n".join(msgs)
            source["description"] = (data.get("description") or "").strip()
            source["category"] = matches[0].parent.parent.name

    elif bench == "clawbench":
        # clawbench 实际路径：benchmarks/claw-bench/tasks/{domain}/{task_id}/
        # task_id 可能是短 ID（eml-017）或长 ID（eml-017-out-of-office-responder）
        # 1. 精确匹配
        matches = list(PROJECT_ROOT.glob(f"benchmarks/claw-bench/tasks/*/{task_id}"))
        # 2. 前缀匹配（短 ID）
        if not matches:
            matches = list(PROJECT_ROOT.glob(f"benchmarks/claw-bench/tasks/*/{task_id}-*"))
        # 3. 后缀匹配（短 ID 在尾部）
        if not matches:
            matches = list(PROJECT_ROOT.glob(f"benchmarks/claw-bench/tasks/*/{task_id}"))
        if matches:
            task_dir = matches[0]
            inst = task_dir / "instruction.md"
            if inst.exists():
                source["prompt"] = inst.read_text(encoding="utf-8").strip()
            source["description"] = source["prompt"][:200]
            source["category"] = task_dir.parent.name  # domain 名

    elif bench == "claweval":
        # claweval 实际路径：benchmarks/claw-eval/tasks/{task_id}/
        task_dir = PROJECT_ROOT / f"benchmarks/claw-eval/tasks/{task_id}"
        if not task_dir.exists():
            matches = list(PROJECT_ROOT.glob(f"benchmarks/claw-eval/tasks/*{task_id}*"))
            if matches:
                task_dir = matches[0]
        if task_dir.exists():
            # 优先读 instruction.md
            inst = task_dir / "instruction.md"
            if inst.exists():
                source["prompt"] = inst.read_text(encoding="utf-8").strip()
            # 从 task.yaml 读取 prompt 和元数据
            yaml_path = task_dir / "task.yaml"
            if yaml_path.exists() and not source["prompt"]:
                try:
                    import yaml
                    data = yaml.safe_load(open(yaml_path))
                    prompt_data = data.get("prompt", {})
                    if isinstance(prompt_data, dict):
                        source["prompt"] = prompt_data.get("text", "")
                    elif isinstance(prompt_data, str):
                        source["prompt"] = prompt_data
                    source["description"] = data.get("task_name", "")
                    source["category"] = data.get("category", "")
                except Exception:
                    pass

    return source


def load_transcript(bench, task_id):
    """加载 baseline 轨迹"""
    transcript_str = ""

    if bench == "agentbench":
        path = PROJECT_ROOT / f"outputs/agentbench/{MODEL_DIR}/{task_id}/agent_result.json"
        if path.exists():
            try:
                d = json.load(open(path))
                transcript_str = json.dumps(d.get("transcript", []), ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"  Warning: Failed to load transcript for {task_id}: {e}")

    elif bench == "clawbench":
        path = PROJECT_ROOT / f"outputs/clawbench-official/transcripts/{MODEL_DIR}/{task_id}/transcript.json"
        if path.exists():
            try:
                transcript_str = path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  Warning: Failed to load transcript for {task_id}: {e}")

    elif bench == "claweval":
        path = PROJECT_ROOT / f"outputs/claweval/transcripts/{MODEL_DIR}/{task_id}/transcript.json"
        if path.exists():
            try:
                transcript_str = path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  Warning: Failed to load transcript for {task_id}: {e}")

    if len(transcript_str) > MAX_TRANSCRIPT_LEN:
        transcript_str = transcript_str[:MAX_TRANSCRIPT_LEN] + "\n...[transcript truncated]"

    return transcript_str


# ── 主流程 ──────────────────────────────────────────────

CATEGORY_NAMES = {
    "A": "Task Understanding / Planning Drift",
    "B": "Tool / Environment Grounding Failure",
    "D": "Verification / Recovery Deficiency",
}


def main():
    print("=" * 60)
    print("H3 Breakpoint Annotation Prompt Generator")
    print("Annotating GG/AI/OV breakpoints for A/B/D category failures")
    print("=" * 60)

    # 加载 A/B/D 类失败
    print("\n[1/4] Loading failure categories (A/B/D)...")
    categories = load_failure_categories()
    total = sum(len(v) for v in categories.values())
    for cat in ["A", "B", "D"]:
        print(f"  {cat}类: {len(categories[cat])} 条")
    print(f"  总计: {total} 条")

    # 生成 prompts
    print(f"\n[2/4] Loading task sources and transcripts...")
    prompts = []
    missing_transcript = []
    missing_source = []

    for cat in ["A", "B", "D"]:
        for item in categories[cat]:
            bench = item["bench"]
            task_id = item["task_id"]

            # 加载任务来源
            source = load_task_source(bench, task_id)
            if not source["prompt"]:
                missing_source.append(f"{bench}:{task_id}")

            # 加载轨迹
            transcript = load_transcript(bench, task_id)
            if not transcript:
                missing_transcript.append(f"{bench}:{task_id}")

            prompt_text = PROMPT_TEMPLATE.format(
                BREAKPOINT_DEFINITIONS=BREAKPOINT_DEFINITIONS.strip(),
                bench=bench,
                error_category=cat,
                error_category_name=CATEGORY_NAMES[cat],
                task_id=task_id,
                description=source.get("description") or "N/A",
                task_prompt=source.get("prompt") or "(task prompt not available)",
                transcript=transcript or "(transcript not available)",
            )

            prompts.append({
                "bench": bench,
                "task_id": task_id,
                "error_category": cat,
                "prompt_for_llm": prompt_text,
                "has_transcript": bool(transcript),
                "has_source": bool(source.get("prompt")),
            })

    print(f"  Missing transcripts: {len(missing_transcript)}")
    for m in missing_transcript[:10]:
        print(f"    - {m}")
    if len(missing_transcript) > 10:
        print(f"    ... and {len(missing_transcript) - 10} more")

    print(f"  Missing task sources: {len(missing_source)}")
    for m in missing_source[:10]:
        print(f"    - {m}")

    # 统计
    print(f"\n[3/4] Summary:")
    stats = Counter()
    for p in prompts:
        stats[f"{p['error_category']}_total"] += 1
        if p["has_transcript"]:
            stats[f"{p['error_category']}_has_transcript"] += 1
    for cat in ["A", "B", "D"]:
        total_cat = stats.get(f"{cat}_total", 0)
        has_t = stats.get(f"{cat}_has_transcript", 0)
        print(f"  {cat}类: {total_cat} total, {has_t} with transcript ({has_t/total_cat*100:.0f}%)" if total_cat else f"  {cat}类: 0")

    # 保存
    print(f"\n[4/4] Saving prompts...")
    out_path = OUTPUT_DIR / "breakpoint_prompts.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    print(f"  Saved {len(prompts)} prompts to: {out_path}")

    # CSV 摘要
    csv_path = OUTPUT_DIR / "breakpoint_summary.csv"
    with open(csv_path, "w") as f:
        f.write("bench,task_id,error_category,has_transcript,has_source\n")
        for p in prompts:
            f.write(f"{p['bench']},{p['task_id']},{p['error_category']},{p['has_transcript']},{p['has_source']}\n")
    print(f"  Saved summary to: {csv_path}")

    print("\n" + "=" * 60)
    print("Next step: run breakpoint classification via LLM")
    print("  python scripts/run_breakpoint_classification.py")
    print("  (or reuse run_error_classification.py with --input/--output)")
    print("=" * 60)


if __name__ == "__main__":
    main()
