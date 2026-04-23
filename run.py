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

  # 从文件加载任务列表 (同一 bench 的 task 会批量执行)
  python3 run.py --task task_list.csv
  python3 run.py --task task_list.txt --model claude-opus

任务列表文件格式:
  # CSV 格式 (推荐)
  bench_id,task_id
  zclawbench,01_Productivity_Flow_task_6_calendar_scheduling
  tribe,tribe_task_001

  # 纯文本格式
  zclawbench:01_Productivity_Flow_task_6_calendar_scheduling
  tribe:tribe_task_001

Benchmarks:
  zclawbench        ZClawBench Subset     116 tasks  NanoBotAgent + Judge (0~1)
  clawbench-official ClawBench Official    250 tasks  ReAct + Pytest (0~100)
  pinchbench        PinchBench             23 tasks   Rule-based (0~100)
  agentbench        AgentBench             40 tasks   L0+L1 (0~100)
  skillsbench       SkillsBench            56 tasks   LLM + Pytest (%)
  tribe             TribeBench             8 tasks    ReAct + Judge (0~100)
  claweval          ClawEval               300 tasks  LLM + Judge (0~100)
"""
import argparse
import os
import sys
from pathlib import Path

# 确保包可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))
openclawpro_dir = Path(os.environ.get("OPENCLAWPRO_DIR", str(Path(__file__).resolve().parent / "OpenClawPro")))
if openclawpro_dir.exists():
    sys.path.insert(0, str(openclawpro_dir))

from clawevalkit.config import load_env, list_models, MODELS
from clawevalkit.dataset import BENCHMARKS, list_benchmarks
from clawevalkit.inference import infer_all
from clawevalkit.summarizer import Summarizer
from clawevalkit.utils.log import log, setup_logging


def load_task_list_from_file(file_path: str) -> dict:
    """从文件加载任务列表，返回 {bench_key: [task_ids]} 字典。

    支持两种格式:
    1. CSV格式 (推荐): bench_id,task_id
    2. 纯文本格式: bench_id:task_id

    同一 bench 的 task 会聚合在一起，便于批量执行。
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Task list file not found: {file_path}")

    tasks_by_bench = {}
    content = path.read_text(encoding="utf-8").strip()

    if content.startswith("bench_id,") or content.startswith("bench_id,task_id"):
        # CSV 格式
        import csv
        import io
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        # 找到 bench_id 和 task_id 列
        bench_col = None
        task_col = None
        for i, col in enumerate(header):
            col_lower = col.lower().strip()
            if col_lower == "bench_id" or col_lower == "bench":
                bench_col = i
            elif col_lower == "task_id" or col_lower == "task":
                task_col = i
            elif col_lower == "id" and bench_col is None:
                bench_col = i

        if bench_col is None or task_col is None:
            raise ValueError(f"CSV header must contain 'bench_id' and 'task_id' columns. Got: {header}")

        for row in reader:
            if len(row) <= max(bench_col, task_col):
                continue
            bench_key = row[bench_col].strip()
            task_id = row[task_col].strip()
            if not bench_key or not task_id:
                continue
            if bench_key.startswith("#"):
                continue
            if bench_key not in tasks_by_bench:
                tasks_by_bench[bench_key] = []
            tasks_by_bench[bench_key].append(task_id)
    else:
        # 纯文本格式: bench_id:task_id 或 bench_id task_id
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 支持 bench_id:task_id 或 bench_id task_id 格式
            if ":" in line:
                parts = line.split(":", 1)
            elif " " in line:
                parts = line.split(None, 1)
            else:
                continue
            if len(parts) != 2:
                continue
            bench_key, task_id = parts[0].strip(), parts[1].strip()
            if not bench_key or not task_id:
                continue
            if bench_key not in tasks_by_bench:
                tasks_by_bench[bench_key] = []
            tasks_by_bench[bench_key].append(task_id)

    return tasks_by_bench


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
    parser.add_argument("--max-turns", type=int, default=None, help="Max retry turns (default: task-specific)")
    parser.add_argument("--task", "-t", help="指定特定任务ID，或指定任务列表文件路径 (自动识别)")
    parser.add_argument("--category", "-c", help="指定任务类别 (如 01_Productivity_Flow)")
    parser.add_argument("--reuse-container", action="store_true", help="Reuse existing containers (skip rebuild, preserves pip installs)")
    parser.add_argument("--judge-model", help="Judge model for scoring (e.g., minimax/claude-3.5-sonnet, claude-sonnet-4.6)")
    parser.add_argument("--include-multimodal", action="store_true", help="Include multimodal tasks (for ClawEval only, default: excluded)")
    parser.add_argument("--harness", choices=["collaboration", "control", "memory", "procedure"],
                        help="Enable a harness recipe for NanoBotAgent (collaboration/control/memory/procedure)")
    args = parser.parse_args()

    # Only set transcripts_dir if explicitly provided; otherwise let each bench
    # derive it from output_dir (e.g. output_dir/claweval/transcripts for claweval)
    transcripts_dir_provided = args.transcripts_dir is not None

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

    # 检查 --task 是否为文件路径
    tasks_by_bench = None
    if args.task:
        task_path = Path(args.task)
        if task_path.exists() and task_path.is_file():
            log(f"从文件加载任务列表: {args.task}")
            tasks_by_bench = load_task_list_from_file(args.task)
            # 验证所有 bench_key 都有效
            for bk in tasks_by_bench:
                if bk not in BENCHMARKS:
                    print(f"Unknown benchmark in task file: {bk}. Use --list to see available benchmarks.")
                    sys.exit(1)
            # 打印加载的任务概览
            for bk, tids in tasks_by_bench.items():
                log(f"  {bk}: {len(tids)} tasks")
            bench_keys = list(tasks_by_bench.keys())
        else:
            # 文件不存在，回退到逗号分隔的直接指定模式
            task_ids_override = [t.strip() for t in args.task.split(",")]
    else:
        task_ids_override = None

    log(f"Config: bench={bench_keys}, models={model_keys}, sample={args.sample or 'all'}")

    # 执行评测
    bench_kwargs = {"force": args.force}
    if task_ids_override:
        bench_kwargs["task_ids"] = task_ids_override
    if args.max_turns is not None:
        bench_kwargs["max_turns"] = args.max_turns
    if args.docker:
        bench_kwargs["use_docker"] = True
    if args.reuse_container:
        bench_kwargs["reuse_container"] = True
    if args.parallel > 1:
        bench_kwargs["parallel"] = args.parallel
    if args.category:
        bench_kwargs["category"] = args.category
    if not args.include_multimodal:
        bench_kwargs["exclude_multimodal"] = True
    if args.harness:
        bench_kwargs["harness"] = args.harness
        if not args.output_dir:
            args.output_dir = f"outputs/harness/{args.harness}"
    # 默认 transcripts_dir = output_dir / "claweval" / "transcripts" (for claweval bench)
    if args.output_dir and not transcripts_dir_provided:
        default_transcripts_dir = f"{args.output_dir}/claweval/transcripts"
    else:
        default_transcripts_dir = None

    # 如果从文件加载任务，需要按 bench 分批执行
    if tasks_by_bench:
        results = {}
        for bk in bench_keys:
            task_ids = tasks_by_bench.get(bk, [])
            if not task_ids:
                continue
            log(f"\n{'=' * 60}")
            log(f"BENCHMARK: {bk} ({len(task_ids)} tasks from file)")
            log(f"{'=' * 60}")
            for mk in model_keys:
                bk_kwargs = dict(bench_kwargs)
                bk_kwargs["task_ids"] = task_ids
                from clawevalkit.inference import infer_data_job
                result = infer_data_job(bk, mk, sample=0,
                                        output_dir=args.output_dir,
                                        transcripts_dir=args.transcripts_dir if transcripts_dir_provided else default_transcripts_dir,
                                        **bk_kwargs)
                results[(bk, mk)] = result
                log(f"  [{bk}×{mk}] done: score={result.get('score', 0)}, scored={result.get('scored', 0)}/{result.get('total', 0)}")
    else:
        # 原有逻辑：直接调用 infer_all
        infer_all(bench_keys, model_keys, sample=args.sample,
                  output_dir=args.output_dir,
                  transcripts_dir=args.transcripts_dir if transcripts_dir_provided else default_transcripts_dir,
                  **bench_kwargs)

    # 打印汇总
    log("\n")
    summarizer.summary()


if __name__ == "__main__":
    main()
