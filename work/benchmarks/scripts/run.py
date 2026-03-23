#!/usr/bin/env python3
"""
统一评估框架入口脚本。

用法:
    python run.py --benchmark pinchbench --api-url <url> --api-key <key> --model <model>

示例:
    python run.py --benchmark pinchbench \
        --api-url https://openrouter.ai/api/v1 \
        --api-key sk-xxx \
        --model anthropic/claude-sonnet-4-20250514
"""

import argparse
import logging
import sys
from pathlib import Path

# 添加当前目录到 Python 路径
_scripts_dir = Path(__file__).parent
sys.path.insert(0, str(_scripts_dir))

from agent.base import AgentResult, BaseAgent
from agent.nanobot import NanoBotAgent
from adapters.pinchbench import PinchBenchAdapter
from adapters.openclawbench import OpenClawBenchAdapter
from adapters.skillsbench import SkillsBenchAdapter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("benchmark")


def create_agent(agent_type: str, model: str, api_url: str, api_key: str, workspace: Path, **kwargs) -> BaseAgent:
    """创建 Agent 实例

    Args:
        agent_type: Agent 类型 (nanobot, openclaw)
        model: 模型 ID
        api_url: API 基础 URL
        api_key: API 密钥
        workspace: 工作目录

    Returns:
        BaseAgent: Agent 实例
    """
    if agent_type == "nanobot":
        return NanoBotAgent(
            model=model,
            api_url=api_url,
            api_key=api_key,
            workspace=workspace,
            **kwargs,
        )
    elif agent_type == "openclaw":
        # TODO: 实现 OpenClaw Agent
        raise NotImplementedError("OpenClaw agent not implemented yet")
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


def run_pinchbench(args: argparse.Namespace) -> None:
    """运行 PinchBench 评估

    Args:
        args: 命令行参数
    """
    # 路径设置
    benchmarks_dir = Path(__file__).parent.parent
    pinchbench_dir = benchmarks_dir / "pinchbench"
    tasks_dir = pinchbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    # 创建工作目录
    workspace = Path("/tmp/benchmarks/workspace")
    workspace.mkdir(parents=True, exist_ok=True)

    # 创建输出目录
    output_dir = Path(args.output_dir) if args.output_dir else benchmarks_dir / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建 Agent
    logger.info(f"Creating {args.agent} agent with model: {args.model}")
    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
    )

    # 创建适配器
    adapter = PinchBenchAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        skill_dir=pinchbench_dir,
        output_dir=output_dir,
    )

    # 加载任务
    adapter.load_tasks()

    # 运行评估
    task_ids = None
    if args.tasks:
        task_ids = [t.strip() for t in args.tasks.split(",")]

    results = adapter.run(
        task_ids=task_ids,
        runs_per_task=args.runs,
    )

    logger.info("\nBenchmark completed!")
    logger.info(f"Overall Score: {results['overall_score']:.1f}%")
    logger.info(f"Total Tasks: {results['total_tasks']}")
    logger.info(f"Results saved to: {output_dir}")


def run_openclawbench(args: argparse.Namespace) -> None:
    """运行 OpenClawBench 评估

    Args:
        args: 命令行参数
    """
    # 路径设置
    benchmarks_dir = Path(__file__).parent.parent
    agentbench_dir = benchmarks_dir / "agentbench-openclaw"
    tasks_dir = agentbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    # 创建工作目录
    workspace = Path("/tmp/benchmarks/workspace")
    workspace.mkdir(parents=True, exist_ok=True)

    # 创建输出目录
    output_dir = Path(args.output_dir) if args.output_dir else benchmarks_dir / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建 Agent
    logger.info(f"Creating {args.agent} agent with model: {args.model}")
    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
    )

    # 创建适配器
    adapter = OpenClawBenchAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        output_dir=output_dir,
    )

    # 加载任务
    suite = getattr(args, 'suite', None)
    difficulty = getattr(args, 'difficulty', None)
    adapter.load_tasks(suite=suite, difficulty=difficulty)

    # 运行评估
    task_ids = None
    if args.tasks:
        task_ids = [t.strip() for t in args.tasks.split(",")]

    results = adapter.run(
        task_ids=task_ids,
        runs_per_task=args.runs,
    )

    logger.info("\nBenchmark completed!")
    logger.info(f"Overall Score: {results['overall_score']:.1f}%")
    logger.info(f"Total Tasks: {results['total_tasks']}")
    logger.info(f"Results saved to: {output_dir}")


def run_skillsbench(args: argparse.Namespace) -> None:
    """运行 SkillsBench 评估

    Args:
        args: 命令行参数
    """
    # 路径设置
    benchmarks_dir = Path(__file__).parent.parent
    skillsbench_dir = benchmarks_dir / "skillsbench"
    tasks_dir = skillsbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    # 创建工作目录
    workspace = Path("/tmp/benchmarks/workspace")
    workspace.mkdir(parents=True, exist_ok=True)

    # 创建输出目录
    output_dir = Path(args.output_dir) if args.output_dir else benchmarks_dir / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建 Agent
    logger.info(f"Creating {args.agent} agent with model: {args.model}")
    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
    )

    # 创建适配器
    adapter = SkillsBenchAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        output_dir=output_dir,
    )

    # 加载任务
    difficulty = getattr(args, 'difficulty', None)
    category = getattr(args, 'category', None)
    adapter.load_tasks(difficulty=difficulty, category=category)

    # 运行评估
    task_ids = None
    if args.tasks:
        task_ids = [t.strip() for t in args.tasks.split(",")]

    results = adapter.run(
        task_ids=task_ids,
        runs_per_task=args.runs,
        threads=args.threads,
    )

    logger.info("\nBenchmark completed!")
    logger.info(f"Overall Score: {results['overall_score']:.1f}%")
    logger.info(f"Passed: {results['passed_tasks']}/{results['total_tasks']} tasks")
    logger.info(f"Results saved to: {output_dir}")


def run_benchmark(benchmark_name: str, args: argparse.Namespace) -> None:
    """运行指定的 benchmark

    Args:
        benchmark_name: Benchmark 名称
        args: 命令行参数
    """
    if benchmark_name == "pinchbench":
        run_pinchbench(args)
    elif benchmark_name == "openclawbench":
        run_openclawbench(args)
    elif benchmark_name == "skillsbench":
        run_skillsbench(args)
    else:
        logger.error(f"Unknown benchmark: {benchmark_name}")
        logger.info(f"Available benchmarks: pinchbench, openclawbench, skillsbench")
        sys.exit(1)


def list_benchmarks() -> None:
    """列出所有可用的 benchmarks"""
    benchmarks_dir = Path(__file__).parent.parent
    print("Available benchmarks:")
    for d in sorted(benchmarks_dir.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and d.name not in ["nanobot", "claw-bench-tribe", "claw-bench-official"]:
            print(f"  - {d.name}")


def main():
    parser = argparse.ArgumentParser(
        description="统一评估框架 - 运行多个 benchmark 评估",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行 pinchbench
  python run.py --benchmark pinchbench --api-url https://openrouter.ai/api/v1 --api-key sk-xxx --model anthropic/claude-sonnet-4-20250514

  # 只运行特定任务
  python run.py --benchmark pinchbench --api-url https://openrouter.ai/api/v1 --api-key sk-xxx --model anthropic/claude-sonnet-4 --tasks task_01_calendar,task_02_stock

  # 列出所有 benchmark
  python run.py --list
        """,
    )

    parser.add_argument(
        "--benchmark", "-b",
        type=str,
        help="Benchmark 名称 (如 pinchbench)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有可用的 benchmarks",
    )

    # Agent 配置
    parser.add_argument(
        "--agent",
        type=str,
        default="nanobot",
        choices=["nanobot", "openclaw"],
        help="使用的 Agent 类型 (默认: nanobot)",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        help="模型 ID (如 anthropic/claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        help="API 基础 URL (如 https://openrouter.ai/api/v1)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="API 密钥",
    )

    # 评估配置
    parser.add_argument(
        "--tasks",
        type=str,
        help="要运行的任务 ID，用逗号分隔 (如 task_01_calendar,task_02_stock)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="每个任务运行次数 (默认: 1)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="单个任务超时时间（秒）(默认: 300)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="结果输出目录",
    )

    # OpenClawBench 特定参数
    parser.add_argument(
        "--suite",
        type=str,
        help="OpenClawBench: 指定 suite (file-creation, research, data-analysis, multi-step, memory, error-handling, tool-efficiency)",
    )
    parser.add_argument(
        "--difficulty",
        type=str,
        help="OpenClawBench/SkillsBench: 指定难度 (easy, medium, hard) 或 'fast' (easy+medium)",
    )

    # SkillsBench 特定参数
    parser.add_argument(
        "--category",
        type=str,
        help="SkillsBench: 指定类别",
    )
    parser.add_argument(
        "--threads", "-t",
        type=int,
        default=1,
        help="并行线程数（默认: 1，用于加速执行）",
    )

    args = parser.parse_args()

    # 列出 benchmarks
    if args.list:
        list_benchmarks()
        return

    # 检查必需参数
    if not args.benchmark:
        parser.error("--benchmark is required (unless using --list)")

    if args.benchmark:
        if not args.api_url:
            parser.error("--api-url is required")
        if not args.api_key:
            parser.error("--api-key is required")
        if not args.model:
            parser.error("--model is required")

    # 运行 benchmark
    run_benchmark(args.benchmark, args)


if __name__ == "__main__":
    main()
