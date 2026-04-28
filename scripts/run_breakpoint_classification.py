#!/usr/bin/env python3
"""运行断点标注分类：对 A/B/D 类失败轨迹标注 GG/AI/OV 断裂位置。

用法：
    python scripts/run_breakpoint_classification.py --model glm-4.7
    python scripts/run_breakpoint_classification.py --model glm-4.7 --retry-unparsed
"""

import argparse
import json
import re
import signal
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from clawevalkit.config import load_env, get_model_config

# 复用 run_error_classification 的 LLM 调用
from run_error_classification import call_model

INPUT_PATH = PROJECT_ROOT / "error_analysis" / "outputs" / "breakpoint_prompts.json"
RESULTS_JSON = PROJECT_ROOT / "error_analysis" / "outputs" / "breakpoint_results.json"
RESULTS_CSV = PROJECT_ROOT / "error_analysis" / "outputs" / "breakpoint_results.csv"

# GG/AI/OV 三类断点
BREAKPOINT_RE = re.compile(r"\\boxed\{(GG|AI|OV)\}")


def extract_breakpoint(text: str) -> str:
    """从 LLM 回复中提取断点标注"""
    m = BREAKPOINT_RE.search(text)
    if m:
        return m.group(1)
    # Fallback: 匹配独立的 GG/AI/OV
    m = re.search(r"\b(GG|AI|OV)\b", text)
    if m:
        return m.group(1)
    return "UNPARSED"


def load_prompts():
    with open(INPUT_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_existing_results():
    if not RESULTS_JSON.exists():
        return {}
    with open(RESULTS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return {(r["bench"], r["task_id"], r.get("error_category", "")): r for r in data}


def save_results(results: list[dict]):
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    with open(RESULTS_CSV, "w", encoding="utf-8") as f:
        f.write("bench,task_id,error_category,breakpoint\n")
        for r in results:
            f.write(f"{r['bench']},{r['task_id']},{r.get('error_category','')},{r.get('breakpoint','')}\n")

    print(f"  已保存 {len(results)} 条结果 -> {RESULTS_JSON.name}")


def main():
    parser = argparse.ArgumentParser(description="H3 断点标注分类")
    parser.add_argument("--model", required=True, help="模型 key (如 glm-4.7)")
    parser.add_argument("--batch-size", type=int, default=10, help="每 N 条保存一次")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--retry-unparsed", action="store_true", help="重试 UNPARSED 的结果")
    args = parser.parse_args()

    load_env()
    try:
        config = get_model_config(args.model)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print("=" * 60)
    print("H3 Breakpoint Classification (GG/AI/OV)")
    print("=" * 60)

    prompts = load_prompts()
    print(f"加载 {len(prompts)} 条 prompt")

    existing = load_existing_results()
    print(f"已有 {len(existing)} 条结果")

    results = list(existing.values())
    done_keys = set(existing.keys())

    if args.retry_unparsed:
        unparsed_keys = {k for k, r in existing.items() if r.get("breakpoint") == "UNPARSED"}
        print(f"  --retry-unparsed: 重试 {len(unparsed_keys)} 条 UNPARSED")
        done_keys -= unparsed_keys
        results = [r for r in results if (r["bench"], r["task_id"], r.get("error_category", "")) not in unparsed_keys]

    todo = [p for p in prompts if (p["bench"], p["task_id"], p.get("error_category", "")) not in done_keys]
    print(f"剩余: {len(todo)} 条待标注")

    if not todo:
        print("无待处理任务。")
        return

    # Ctrl+C 优雅退出
    interrupted = False

    def _sigint(sig, frame):
        nonlocal interrupted
        if interrupted:
            print("\n强制退出")
            sys.exit(1)
        interrupted = True
        print("\n\nCtrl+C — 正在保存进度...")
        save_results(results)
        sys.exit(0)

    signal.signal(signal.SIGINT, _sigint)

    total = len(todo)
    batch_count = 0

    for i, item in enumerate(todo, 1):
        bench, tid, ecat = item["bench"], item["task_id"], item.get("error_category", "")
        prompt_text = item["prompt_for_llm"]
        print(f"[{i}/{total}] {ecat}类 {bench}/{tid} ...", end=" ", flush=True)

        messages = [{"role": "user", "content": prompt_text}]
        t0 = time.time()

        raw_response = call_model(messages, config, max_tokens=args.max_tokens, timeout=180)
        elapsed = time.time() - t0

        bp = extract_breakpoint(raw_response)
        print(f"{bp} ({elapsed:.1f}s)")

        result = {
            "bench": bench,
            "task_id": tid,
            "error_category": ecat,
            "breakpoint": bp,
            "raw_response": raw_response,
            "has_transcript": item.get("has_transcript", False),
        }
        result.pop("prompt_for_llm", None) if "prompt_for_llm" in result else None

        results.append(result)
        done_keys.add((bench, tid, ecat))
        batch_count += 1

        if batch_count >= args.batch_size:
            save_results(results)
            batch_count = 0

    if not interrupted:
        save_results(results)

        print(f"\n完成! 共 {len(results)} 条结果")
        print("\n断点分布:")
        for bp, count in sorted(Counter(r.get("breakpoint", "?") for r in results).items()):
            print(f"  {bp}: {count}")

        # 按 error_category × breakpoint 交叉统计
        print("\n交叉统计 (error_category × breakpoint):")
        cross = Counter()
        for r in results:
            cross[(r.get("error_category", "?"), r.get("breakpoint", "?"))] += 1
        for ecat in ["A", "B", "D"]:
            print(f"  {ecat}类:", end="")
            for bp in ["GG", "AI", "OV"]:
                print(f" {bp}={cross.get((ecat, bp), 0)}", end="")
            print()


if __name__ == "__main__":
    main()
