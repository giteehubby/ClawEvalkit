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
from dotenv import load_dotenv

# 加载 .env 配置
load_dotenv('/Volumes/F/Clauding/.env')

# 添加项目根目录到 Python 路径
_root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_root_dir))

from src.harness.agent.base import AgentResult, BaseAgent
from src.harness.agent.memory import MemoryConfig, WritePolicy, RetrievalPolicy
from src.harness.agent.control import ControlConfig, PlanFirstConfig, ReplanConfig, RetryConfig, ReflectionConfig
from src.harness.agent.collaboration import CollabConfig, HandoffPolicy
from src.harness.agent.procedure import ProceduralConfig
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


def create_agent(agent_type: str, model: str, api_url: str, api_key: str, workspace: Path, memory_config: MemoryConfig | None = None, control_config: ControlConfig | None = None, collab_config: CollabConfig | None = None, procedural_config: ProceduralConfig | None = None, **kwargs) -> BaseAgent:
    """创建 Agent 实例"""
    if agent_type == "nanobot":
        from src.harness.agent.nanobot import NanoBotAgent

        return NanoBotAgent(
            model=model,
            api_url=api_url,
            api_key=api_key,
            workspace=workspace,
            memory_config=memory_config,
            control_config=control_config,
            collab_config=collab_config,
            procedural_config=procedural_config,
            **kwargs,
        )
    elif agent_type == "openclaw":
        raise NotImplementedError("OpenClaw agent not implemented yet")
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


def build_memory_config(args: argparse.Namespace) -> MemoryConfig | None:
    """从 args 构建 MemoryConfig"""
    if not getattr(args, 'memory_enabled', False):
        return None
    return MemoryConfig(
        enabled=True,
        max_items=getattr(args, 'memory_max_items', 20),
        retrieval_max=getattr(args, 'memory_retrieval_max', 5),
        write_policy=WritePolicy(getattr(args, 'memory_write_policy', 'tool_result_or_error')),
        retrieval_policy=RetrievalPolicy(getattr(args, 'memory_retrieval_policy', 'recent')),
    )


def build_control_config(args: argparse.Namespace) -> ControlConfig | None:
    """从 args 构建 ControlConfig"""
    if not getattr(args, 'control_enabled', False):
        return None

    # 解析 replan_signals
    replan_signals_str = getattr(args, 'replan_signals', 'error,repeated_action')
    replan_signals = [s.strip() for s in replan_signals_str.split(',')] if replan_signals_str else ['error', 'repeated_action']

    plan_first = PlanFirstConfig(
        enabled=getattr(args, 'plan_first_enabled', False),
        trigger=getattr(args, 'plan_first_trigger', 'task_start'),
        max_plan_length=getattr(args, 'plan_max_length', 500),
        require_explicit_plan=getattr(args, 'plan_require_explicit', False),
    )

    replan = ReplanConfig(
        enabled=getattr(args, 'replan_enabled', False),
        signal_threshold=getattr(args, 'replan_signal_threshold', 3),
        signals=replan_signals,
        max_replans=getattr(args, 'replan_max_count', 2),
        min_iterations_between_replans=getattr(args, 'replan_min_interval', 2),
    )

    retry = RetryConfig(
        enabled=getattr(args, 'retry_enabled', False),
        max_retries=getattr(args, 'retry_max_count', 2),
        backoff=getattr(args, 'retry_backoff', 'exponential'),
        base_delay=getattr(args, 'retry_base_delay', 1.0),
        retryable_errors=getattr(args, 'retryable_errors', ['rate_limit', 'timeout', 'transient']),
        fatal_errors=getattr(args, 'retry_fatal_errors', ['invalid_params', 'auth_failed', 'permission_denied']),
    )

    reflection = ReflectionConfig(
        enabled=getattr(args, 'reflection_enabled', False),
        trigger=getattr(args, 'reflection_trigger', 'on_failure'),
        consecutive_failure_threshold=getattr(args, 'reflection_consecutive_threshold', 2),
        max_reflection_length=getattr(args, 'reflection_max_length', 300),
    )

    return ControlConfig(
        enabled=True,
        plan_first=plan_first,
        replan=replan,
        retry=retry,
        reflection=reflection,
        preflight_enabled=getattr(args, 'preflight_enabled', False),
        preflight_check_params=getattr(args, 'preflight_check_params', True),
        preflight_check_suitability=getattr(args, 'preflight_check_suitability', False),
    )


def build_collab_config(args: argparse.Namespace) -> CollabConfig | None:
    """从 args 构建 CollabConfig (T3)"""
    if not getattr(args, 'collab_enabled', False):
        return None

    handoff_policy = HandoffPolicy(
        trigger=getattr(args, 'collab_handoff_trigger', 'on_error'),
        max_context_length=getattr(args, 'collab_max_context_length', 2000),
        include_tool_history=getattr(args, 'collab_include_tool_history', True),
        include_memory=getattr(args, 'collab_include_memory', True),
    )

    return CollabConfig(
        enabled=True,
        mode=getattr(args, 'collab_mode', 'planner_executor'),
        critique_frequency=getattr(args, 'collab_critique_frequency', 'on_error'),
        handoff_policy=handoff_policy,
        max_handoffs=getattr(args, 'collab_max_handoffs', 3),
        planner_model=getattr(args, 'collab_planner_model', None),
        verifier_model=getattr(args, 'collab_verifier_model', None),
    )


def build_procedural_config(args: argparse.Namespace) -> ProceduralConfig | None:
    """从 args 构建 ProceduralConfig (T4)"""
    if not getattr(args, 'procedural_enabled', False):
        return None

    return ProceduralConfig(
        enabled=True,
        cards_dir=getattr(args, 'procedural_cards_dir', ''),
        max_expansions_per_iteration=getattr(args, 'procedural_max_expansions', 3),
        show_skill_list=getattr(args, 'procedural_show_skill_list', True),
        cache_triggers=getattr(args, 'procedural_cache_triggers', True),
    )


def save_transcripts_to_dir(output_dir: Path, transcript_dir: Path | None) -> None:
    """将 transcripts 复制到指定目录

    Args:
        output_dir: 原始输出目录 (包含 results 和 transcripts/)
        transcript_dir: 目标 transcripts 目录，如果为 None 则跳过
    """
    if not transcript_dir:
        return

    transcript_dir = Path(transcript_dir)
    transcript_dir.mkdir(parents=True, exist_ok=True)

    # 从 output_dir/transcripts/ 复制
    src_transcripts = output_dir / "transcripts"
    if src_transcripts.exists():
        import shutil
        for f in src_transcripts.glob("*.jsonl"):
            shutil.copy(f, transcript_dir / f.name)
        logger.info(f"Copied {len(list(src_transcripts.glob('*.jsonl')))} transcripts to {transcript_dir}")


def run_pinchbench(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    pinchbench_dir = nanopro_dir / "benchmarks" / "pinchbench"
    tasks_dir = pinchbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    workspace = Path(tempfile.gettempdir()) / "benchmarks" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "artifacts" / "runs" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
        memory_config=build_memory_config(args),
        control_config=build_control_config(args),
        collab_config=build_collab_config(args),
        procedural_config=build_procedural_config(args),
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

    # 保存 transcripts 到指定目录
    save_transcripts_to_dir(output_dir, args.transcript_dir)


def run_openclawbench(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    agentbench_dir = nanopro_dir / "benchmarks" / "agentbench-openclaw"
    tasks_dir = agentbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    workspace = Path(tempfile.gettempdir()) / "benchmarks" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "artifacts" / "runs" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
        memory_config=build_memory_config(args),
        control_config=build_control_config(args),
        collab_config=build_collab_config(args),
        procedural_config=build_procedural_config(args),
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

    # 保存 transcripts 到指定目录
    save_transcripts_to_dir(output_dir, args.transcript_dir)


def run_skillsbench(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    skillsbench_dir = nanopro_dir / "benchmarks" / "skillsbench"
    tasks_dir = skillsbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    workspace = Path(tempfile.gettempdir()) / "benchmarks" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "artifacts" / "runs" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    memory_config = build_memory_config(args)
    control_config = build_control_config(args)
    collab_config = build_collab_config(args)
    procedural_config = build_procedural_config(args)

    def make_agent(agent_workspace: Path) -> BaseAgent:
        return create_agent(
            agent_type=args.agent,
            model=args.model,
            api_url=args.api_url,
            api_key=args.api_key,
            workspace=agent_workspace,
            timeout=args.timeout,
            memory_config=memory_config,
            control_config=control_config,
            collab_config=collab_config,
            procedural_config=procedural_config,
        )

    agent = make_agent(workspace)

    adapter = SkillsBenchAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        output_dir=output_dir,
        agent_factory=make_agent if args.threads > 1 else None,
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

    # 保存 transcripts 到指定目录
    save_transcripts_to_dir(output_dir, args.transcript_dir)


def run_clawbench_official(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    clawbench_dir = nanopro_dir / "benchmarks" / "claw-bench-official"
    tasks_dir = clawbench_dir / "tasks"

    if not tasks_dir.exists():
        logger.error(f"Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    workspace = Path(tempfile.gettempdir()) / "benchmarks" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "artifacts" / "runs" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    memory_config = build_memory_config(args)
    control_config = build_control_config(args)
    collab_config = build_collab_config(args)
    procedural_config = build_procedural_config(args)

    def make_agent(agent_workspace: Path) -> BaseAgent:
        return create_agent(
            agent_type=args.agent,
            model=args.model,
            api_url=args.api_url,
            api_key=args.api_key,
            workspace=agent_workspace,
            timeout=args.timeout,
            memory_config=memory_config,
            control_config=control_config,
            collab_config=collab_config,
            procedural_config=procedural_config,
        )

    agent = make_agent(workspace)

    adapter = ClawBenchOfficialAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        output_dir=output_dir,
        agent_factory=make_agent if args.threads > 1 else None,
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

    # 保存 transcripts 到指定目录
    save_transcripts_to_dir(output_dir, args.transcript_dir)


def run_claw_bench_tribe(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    benchmark_dir = nanopro_dir / "benchmarks" / "claw-bench-tribe"

    if not benchmark_dir.exists():
        logger.error(f"Benchmark directory not found: {benchmark_dir}")
        sys.exit(1)
    workspace = Path(tempfile.gettempdir()) / "benchmarks" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "artifacts" / "runs" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
        memory_config=build_memory_config(args),
        control_config=build_control_config(args),
        collab_config=build_collab_config(args),
        procedural_config=build_procedural_config(args),
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

    # 保存 transcripts 到指定目录
    save_transcripts_to_dir(output_dir, args.transcript_dir)


def run_skillbench(args: argparse.Namespace) -> None:
    nanopro_dir = get_nanopro_dir()
    skillbench_dir = nanopro_dir / "benchmarks" / "skillbench"
    workspace = Path("/tmp/benchmarks/workspace")
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir) if args.output_dir else nanopro_dir / "artifacts" / "runs" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = create_agent(
        agent_type=args.agent,
        model=args.model,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=workspace,
        timeout=args.timeout,
        memory_config=build_memory_config(args),
        control_config=build_control_config(args),
        collab_config=build_collab_config(args),
        procedural_config=build_procedural_config(args),
    )

    adapter = SkillBenchAdapter(
        agent=agent,
        skillbench_dir=skillbench_dir,
        output_dir=output_dir,
        threads=args.threads,
    )
    results = adapter.run()

    logger.info("\nBenchmark completed!")
    logger.info(f"Overall Score: {results['overall_score']:.1f}%")
    logger.info(f"Passed: {results['passed_tasks']}/{results['total_tasks']} tasks")
    logger.info(f"Results saved to: {output_dir}")

    # 保存 transcripts 到指定目录
    save_transcripts_to_dir(output_dir, args.transcript_dir)

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

    # Transcript directory
    parser.add_argument("--transcript-dir", type=str, default=None, help="轨迹文件保存目录 (默认: output_dir/transcripts/)")

    # Memory arguments (Recipe T1)
    parser.add_argument("--memory-enabled", action="store_true", help="启用 episodic memory")
    parser.add_argument("--memory-max-items", type=int, default=20, help="最大 memory items 数量 (默认: 20)")
    parser.add_argument("--memory-retrieval-max", type=int, default=5, help="每次检索最大 items 数量 (默认: 5)")
    parser.add_argument(
        "--memory-write-policy",
        type=str,
        default="tool_result_or_error",
        choices=["always", "never", "tool_result", "error", "tool_result_or_error", "long_content"],
        help="Memory 写入策略 (默认: tool_result_or_error)",
    )
    parser.add_argument(
        "--memory-retrieval-policy",
        type=str,
        default="recent",
        choices=["recent", "frequency", "hybrid"],
        help="Memory 检索策略 (默认: recent)",
    )

    # Control arguments (Recipe T2)
    parser.add_argument("--control-enabled", action="store_true", help="启用 control 模块 (Recipe T2)")
    # Plan-first
    parser.add_argument("--plan-first-enabled", action="store_true", help="启用 plan-first")
    parser.add_argument("--plan-first-trigger", type=str, default="task_start", choices=["always", "task_start", "on_failure"], help="Plan-first 触发时机 (默认: task_start)")
    parser.add_argument("--plan-max-length", type=int, default=500, help="计划最大长度 (默认: 500)")
    # Replan
    parser.add_argument("--replan-enabled", action="store_true", help="启用 replan trigger")
    parser.add_argument("--replan-signal-threshold", type=int, default=3, help="触发重规划的信号阈值 (默认: 3)")
    parser.add_argument("--replan-signals", type=str, default="error,repeated_action", help="重规划信号类型，逗号分隔")
    parser.add_argument("--replan-max-count", type=int, default=2, help="最大重规划次数 (默认: 2)")
    # Retry
    parser.add_argument("--retry-enabled", action="store_true", help="启用 retry policy")
    parser.add_argument("--retry-max-count", type=int, default=2, help="最大重试次数 (默认: 2)")
    parser.add_argument("--retry-backoff", type=str, default="exponential", choices=["constant", "exponential"], help="重试退避策略 (默认: exponential)")
    # Reflection
    parser.add_argument("--reflection-enabled", action="store_true", help="启用 failure reflection")
    parser.add_argument("--reflection-trigger", type=str, default="on_failure", choices=["on_failure", "on_consecutive_failures", "manual"], help="Reflection 触发时机 (默认: on_failure)")
    # Preflight
    parser.add_argument("--preflight-enabled", action="store_true", help="启用 preflight check")
    parser.add_argument("--preflight-check-params", action="store_true", default=True, help="Preflight 检查参数")
    parser.add_argument("--preflight-check-suitability", action="store_true", help="Preflight 检查工具适用性")

    # Recipe T5 convenience flag (enables T1 + T2)
    parser.add_argument("--recipe-t5", action="store_true", help="启用 T5 (Memory + Control) = --memory-enabled --control-enabled --plan-first-enabled --replan-enabled --reflection-enabled")

    # Collaboration arguments (Recipe T3)
    parser.add_argument("--collab-enabled", action="store_true", help="启用 collaboration 模块 (Recipe T3)")
    parser.add_argument("--collab-mode", type=str, default="planner_executor", choices=["planner_executor", "executor_verifier"], help="Collaboration 模式 (默认: planner_executor)")
    parser.add_argument("--collab-critique-frequency", type=str, default="on_error", choices=["on_error", "every_step", "never"], help="Critique 频率 (默认: on_error)")
    parser.add_argument("--collab-max-handoffs", type=int, default=3, help="最大 handoff 次数 (默认: 3)")
    parser.add_argument("--collab-handoff-trigger", type=str, default="on_error", choices=["always", "on_error", "on_success", "manual"], help="Handoff 触发时机 (默认: on_error)")
    parser.add_argument("--collab-max-context-length", type=int, default=2000, help="Handoff 最大上下文长度 (默认: 2000)")
    parser.add_argument("--collab-include-tool-history", action="store_true", default=True, help="Handoff 时包含工具历史")
    parser.add_argument("--collab-include-memory", action="store_true", default=True, help="Handoff 时包含 memory")
    parser.add_argument("--collab-planner-model", type=str, default=None, help="Planner 使用的模型 (默认: 与主 agent 相同)")
    parser.add_argument("--collab-verifier-model", type=str, default=None, help="Verifier 使用的模型 (默认: 与主 agent 相同)")

    # Procedural arguments (Recipe T4)
    parser.add_argument("--procedural-enabled", action="store_true", help="启用 procedural 模块 (Recipe T4)")
    parser.add_argument("--procedural-cards-dir", type=str, default="", help="Skill cards 目录路径")
    parser.add_argument("--procedural-max-expansions", type=int, default=3, help="每次迭代最大展开的 cards 数量 (默认: 3)")
    parser.add_argument("--procedural-show-skill-list", action="store_true", default=True, help="在 prompt 中显示 skill 列表")
    parser.add_argument("--procedural-cache-triggers", action="store_true", default=True, help="缓存已触发的 skills")

    args = parser.parse_args()

    # Handle --recipe-t5 convenience flag
    if getattr(args, 'recipe_t5', False):
        args.memory_enabled = True
        args.control_enabled = True
        args.plan_first_enabled = True
        args.replan_enabled = True
        args.reflection_enabled = True

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
