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
import os
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到 Python 路径
_root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_root_dir))

from src.harness.agent.base import AgentResult, BaseAgent
from src.runners.adapters.pinchbench import PinchBenchAdapter
from src.runners.adapters.openclawbench import OpenClawBenchAdapter
from src.runners.adapters.skillsbench import SkillsBenchAdapter
from src.runners.adapters.clawbench_official import ClawBenchOfficialAdapter
from src.runners.adapters.claw_bench_tribe import ClawBenchTribeAdapter
from src.runners.adapters.skillbench import SkillBenchAdapter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("benchmark")


def env_first(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def get_nanopro_dir() -> Path:
    """获取 nanopro 根目录"""
    return Path(__file__).parent.parent


def create_agent(agent_type: str, model: str, api_url: str, api_key: str, workspace: Path, **kwargs) -> BaseAgent:
    """创建 Agent 实例"""
    if agent_type == "nanobot":
        from src.harness.agent.nanobot import NanoBotAgent

        return NanoBotAgent(
            model=model,
            api_url=api_url,
            api_key=api_key,
            workspace=workspace,
            **kwargs,
        )
    elif agent_type == "openclaw":
        raise NotImplementedError("OpenClaw agent not implemented yet")
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


def run_pinchbench(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    pinchbench_dir = nanopro_dir / "benchmarks" / "pinchbench"
    tasks_dir = pinchbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    workspace = Path(tempfile.gettempdir()) / "benchmarks" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "assets" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
    )

    adapter = PinchBenchAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        skill_dir=pinchbench_dir,
        output_dir=output_dir,
    )

    adapter.load_tasks()

    task_ids = None
    if args.tasks:
        task_ids = [t.strip() for t in args.tasks.split(",")]

    results = adapter.run(task_ids=task_ids, runs_per_task=args.runs)

    logger.info("\nBenchmark completed!")
    logger.info(f"Overall Score: {results['overall_score']:.1f}%")
    logger.info(f"Total Tasks: {results['total_tasks']}")
    logger.info(f"Results saved to: {output_dir}")


def run_openclawbench(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    agentbench_dir = nanopro_dir / "benchmarks" / "agentbench-openclaw"
    tasks_dir = agentbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    workspace = Path(tempfile.gettempdir()) / "benchmarks" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "assets" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
    )

    adapter = OpenClawBenchAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        output_dir=output_dir,
    )

    suite = getattr(args, 'suite', None)
    difficulty = getattr(args, 'difficulty', None)
    adapter.load_tasks(suite=suite, difficulty=difficulty)

    task_ids = None
    if args.tasks:
        task_ids = [t.strip() for t in args.tasks.split(",")]

    results = adapter.run(task_ids=task_ids, runs_per_task=args.runs)

    logger.info("\nBenchmark completed!")
    logger.info(f"Overall Score: {results['overall_score']:.1f}%")
    logger.info(f"Total Tasks: {results['total_tasks']}")
    logger.info(f"Results saved to: {output_dir}")


def run_skillsbench(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    skillsbench_dir = nanopro_dir / "benchmarks" / "skillsbench"
    tasks_dir = skillsbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    workspace = Path(tempfile.gettempdir()) / "benchmarks" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "assets" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
    )

    adapter = SkillsBenchAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        output_dir=output_dir,
    )

    difficulty = getattr(args, 'difficulty', None)
    category = getattr(args, 'category', None)
    adapter.load_tasks(difficulty=difficulty, category=category)

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


def run_clawbench_official(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    clawbench_dir = nanopro_dir / "benchmarks" / "claw-bench-official"
    tasks_dir = clawbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    workspace = Path(tempfile.gettempdir()) / "benchmarks" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "assets" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
    )

    adapter = ClawBenchOfficialAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        output_dir=output_dir,
    )

    level = getattr(args, 'level', None)
    domain = getattr(args, 'domain', None)
    adapter.load_tasks(level=level, domain=domain)

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


def run_claw_bench_tribe(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    benchmark_dir = nanopro_dir / "benchmarks" / "claw-bench-tribe"

    if not benchmark_dir.exists():
        logger.error(f"Benchmark directory not found: {benchmark_dir}")
        sys.exit(1)
    workspace = Path(tempfile.gettempdir()) / "benchmarks" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "assets" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
    )

    adapter = ClawBenchTribeAdapter(
        agent=agent,
        benchmark_dir=benchmark_dir,
        output_dir=output_dir,
    )
    adapter.load_tasks()

    task_ids = None
    if args.tasks:
        task_ids = [t.strip() for t in args.tasks.split(",")]

    results = adapter.run(task_ids=task_ids, runs_per_task=args.runs, smoke=args.smoke)

    logger.info("\nBenchmark completed!")
    logger.info(f"Overall Score: {results['overall_score']:.1f}%")
    logger.info(f"Passed: {results['passed_tasks']}/{results['total_tasks']} tests")
    logger.info(f"Critical failures: {results['critical_failures']}")
    logger.info(f"Results saved to: {output_dir}")
    
def run_skillbench(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    skillbench_dir = nanopro_dir / "benchmarks" / "skillbench"
    workspace = Path("/tmp/benchmarks/workspace")
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = nanopro_dir / "assets" / "results" / "skillbench"
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
    )

    adapter = SkillBenchAdapter(
        agent=agent,
        skillbench_dir=skillbench_dir,
        output_dir=output_dir,
    )
    results = adapter.run()

    logger.info("\nBenchmark completed!")
    logger.info(f"Overall Score: {results['overall_score']:.1f}%")
    logger.info(f"Passed: {results['passed_tasks']}/{results['total_tasks']} tasks")
    logger.info(f"Results saved to: {output_dir}")

    agent.cleanup()

def run_benchmark(benchmark_name: str, args: argparse.Namespace) -> None:
    if benchmark_name == "pinchbench":
        run_pinchbench(args)
    elif benchmark_name == "openclawbench":
        run_openclawbench(args)
    elif benchmark_name == "skillsbench":
        run_skillsbench(args)
    elif benchmark_name == "clawbench_official":
        run_clawbench_official(args)
    elif benchmark_name == "claw-bench-tribe":
        run_claw_bench_tribe(args)
    elif benchmark_name == "skillbench":
        run_skillbench(args)
    else:
        logger.error(f"Unknown benchmark: {benchmark_name}")
        logger.info(f"Available benchmarks: pinchbench, openclawbench, skillsbench, clawbench_official, claw-bench-tribe")
        sys.exit(1)


def list_benchmarks() -> None:
    nanopro_dir = get_nanopro_dir()
    benchmarks_dir = nanopro_dir / "benchmarks"
    print("Available benchmarks:")
    for d in sorted(benchmarks_dir.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
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

  # 并行运行 skillsbench (10线程)
  python run.py --benchmark skillsbench --threads 10 --api-url https://openrouter.ai/api/v1 --api-key sk-xxx --model gpt-4o-mini

  # 列出所有 benchmark
  python run.py --list
        """,
    )

    parser.add_argument("--benchmark", "-b", type=str, help="Benchmark 名称 (如 pinchbench)")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用的 benchmarks")

    parser.add_argument("--agent", type=str, default="nanobot", choices=["nanobot", "openclaw"], help="使用的 Agent 类型 (默认: nanobot)")
    parser.add_argument("--model", "-m", type=str, help="模型 ID (如 anthropic/claude-sonnet-4-20250514)")
    parser.add_argument("--api-url", type=str, help="API 基础 URL")
    parser.add_argument("--api-key", type=str, help="API 密钥")

    parser.add_argument("--tasks", type=str, help="要运行的任务 ID，用逗号分隔")
    parser.add_argument("--runs", type=int, default=1, help="每个任务运行次数 (默认: 1)")
    parser.add_argument("--timeout", type=int, default=300, help="单个任务超时时间（秒）(默认: 300)")
    parser.add_argument("--output-dir", type=str, help="结果输出目录")

    parser.add_argument("--suite", type=str, help="OpenClawBench: 指定 suite")
    parser.add_argument("--difficulty", type=str, help="指定难度 (easy, medium, hard)")
    parser.add_argument("--category", type=str, help="SkillsBench: 指定类别")
    parser.add_argument("--level", type=str, help="ClawBench Official: 指定级别 (L1, L2, L3, L4)")
    parser.add_argument("--domain", type=str, help="ClawBench Official: 指定领域")
    parser.add_argument("--threads", "-t", type=int, default=1, help="并行线程数（默认: 1）")
    parser.add_argument("--smoke", action="store_true", help="运行 benchmark 的最小 smoke 子集（部分 benchmark 支持）")

    args = parser.parse_args()

    args.api_url = args.api_url or env_first("OPENAI_BASE_URL", "API_URL")
    args.api_key = args.api_key or env_first("OPENAI_API_KEY", "API_KEY")
    args.model = args.model or env_first("MODEL")

    if args.list:
        list_benchmarks()
        return

    if not args.benchmark:
        parser.error("--benchmark is required (unless using --list)")

    if args.benchmark:
        if not args.api_url:
            parser.error("--api-url is required")
        if not args.api_key:
            parser.error("--api-key is required")
        if not args.model:
            parser.error("--model is required")

    run_benchmark(args.benchmark, args)


if __name__ == "__main__":
    main()
