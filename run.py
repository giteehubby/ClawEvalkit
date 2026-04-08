#!/usr/bin/env python3
"""
ClawEvalKit — 8-Benchmark Agent Evaluation Toolkit

Unified evaluation entry point (VLMEvalKit style).
  - clawevalkit/dataset/  每个 benchmark 独立一个文件
  - configs/models/       YAML 模型配置 (OpenCompass style)

Usage:
  python3 run.py                                    # 全量: 所有 bench × claude-sonnet
  python3 run.py --model claude-opus                   # 指定模型
  python3 run.py --bench tribe,pinchbench           # 指定 bench
  python3 run.py --bench tribe --model claude-sonnet     # 单个 bench × 单个模型
  python3 run.py --sample 5                         # 每 bench 采样 5 个任务
  python3 run.py --summary                          # 只汇总已有结果 (不重新跑)
  python3 run.py --list                             # 列出所有 bench 和模型
  python3 run.py --bench skillsbench --docker --max-turns 5  # 指定迭代次数

8 Benchmarks:
  zclawbench        ZClawBench Subset     18 tasks   NanoBotAgent + Judge (0~1)
  wildclawbench     WildClawBench         10 tasks   NanoBotAgent + Judge (0~1)
  clawbench-official ClawBench Official   250 tasks  ReAct + Pytest (0~100)
  pinchbench        PinchBench            23 tasks   Rule-based (0~100)
  agentbench        AgentBench-OpenClaw   40 tasks   L0+L1 (0~100)
  skillbench        SkillBench            22 tasks   Harness + Pytest (%)
  skillsbench       SkillsBench           56+ tasks  LLM + Pytest (%)
  tribe             Claw-Bench-Tribe      8 tasks    Pure LLM (0~100)
"""
import argparse
import sys
from pathlib import Path

# 确保包可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

from clawevalkit.config import load_env, list_models, MODELS
from clawevalkit.dataset import BENCHMARKS, list_benchmarks
from clawevalkit.inference import infer_all
from clawevalkit.summarizer import Summarizer
from clawevalkit.utils.log import log, setup_logging


def main():
    parser = argparse.ArgumentParser(
        description="ClawEvalKit — 8-Benchmark Agent Evaluation Toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python3 run.py --bench tribe --model claude-sonnet",
    )
    parser.add_argument("--bench", "-b", help="Comma-separated benchmark keys (default: all)")
    parser.add_argument("--model", "-m", default="claude-sonnet", help="Comma-separated model keys (default: claude-sonnet)")
    parser.add_argument("--sample", "-s", type=int, default=0, help="Sample N tasks per bench (0=all)")
    parser.add_argument("--summary", action="store_true", help="Only print summary of existing results")
    parser.add_argument("--list", action="store_true", help="List available benchmarks and models")
    parser.add_argument("--force", action="store_true", help="Force re-evaluation (ignore cache)")
    parser.add_argument("--docker", action="store_true", help="使用 Docker 容器运行 (wildclawbench + skillsbench per-task 模式)")
    parser.add_argument("--parallel", "-p", type=int, default=1, help="并行任务数 (Docker 模式下有效)")
    parser.add_argument("--env", help="Path to .env file (default: auto-detect)")
    parser.add_argument("--output-dir", help="Output directory for results (default: ./outputs)")
    parser.add_argument("--transcripts-dir", help="Directory to save agent transcripts (default: {output_dir}/transcripts)")
    parser.add_argument("--max-turns", type=int, default=3, help="Max retry turns for SkillsBench (default: 3)")
    parser.add_argument("--task", "-t", help="指定特定任务ID (如 01_Productivity_Flow_task_6_calendar_scheduling)")
    parser.add_argument("--category", "-c", help="指定任务类别 (如 01_Productivity_Flow)")
    parser.add_argument("--reuse-container", action="store_true", help="Reuse existing containers (skip rebuild, preserves pip installs)")
    parser.add_argument("--judge-model", help="Judge model for scoring (e.g., minimax/claude-3.5-sonnet, claude-sonnet-4.6)")
    args = parser.parse_args()

    # 设置 transcripts_dir 默认值
    if not args.transcripts_dir:
        args.transcripts_dir = str(Path(args.output_dir or "outputs") / "transcripts")

    # 加载环境变量
    load_env(args.env)

    # 设置 judge model 环境变量（如果指定）
    if args.judge_model:
        import os
        os.environ["JUDGE_MODEL"] = args.judge_model

    # 设置日志级别
    setup_logging(verbose=False)

    if args.list:
        print("\n  Available Benchmarks:")
        for key, name, count in list_benchmarks():
            print(f"    {key:22s} {name:25s} ({count} tasks)")
        print("\n  Available Models:")
        for key, name, provider in list_models():
            print(f"    {key:22s} {name:25s} [{provider}]")
        print()
        return

    summarizer = Summarizer(output_dir=args.output_dir)

    if args.summary:
        summarizer.summary()
        return

    # 解析 bench 和 model
    bench_keys = args.bench.split(",") if args.bench else list(BENCHMARKS.keys())
    model_keys = args.model.split(",") if args.model else ["claude-sonnet"]

    for bk in bench_keys:
        if bk not in BENCHMARKS:
            print(f"Unknown benchmark: {bk}. Use --list to see available benchmarks.")
            sys.exit(1)
    for mk in model_keys:
        if mk not in MODELS:
            print(f"Unknown model: {mk}. Use --list to see available models.")
            sys.exit(1)

    log(f"Config: bench={bench_keys}, models={model_keys}, sample={args.sample or 'all'}")

    # 执行评测
    bench_kwargs = {"force": args.force, "max_turns": args.max_turns}
    if args.docker:
        bench_kwargs["use_docker"] = True
    if args.reuse_container:
        bench_kwargs["reuse_container"] = True
    if args.parallel > 1:
        bench_kwargs["parallel"] = args.parallel
    if args.task:
        bench_kwargs["task_ids"] = [args.task]
    if args.category:
        bench_kwargs["category"] = args.category
    infer_all(bench_keys, model_keys, sample=args.sample,
              output_dir=args.output_dir, transcripts_dir=args.transcripts_dir, **bench_kwargs)

    # 打印汇总
    log("\n")
    summarizer.summary()


if __name__ == "__main__":
    main()
