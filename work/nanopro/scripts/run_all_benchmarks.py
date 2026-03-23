#!/usr/bin/env python3
"""
运行所有 benchmark 的脚本 (使用 google/gemini-3-flash-preview 模型)
"""

import os
import sys
import logging
import time
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('/Volumes/F/Clauding/.env')

script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from agent.nanobot import NanoBotAgent
from adapters.pinchbench import PinchBenchAdapter
from adapters.openclawbench import OpenClawBenchAdapter
from adapters.skillsbench import SkillsBenchAdapter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("benchmark")

def run_benchmark(name, adapter, task_ids_filter=None, use_threads=True):
    """运行单个 benchmark"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Starting: {name}")
    logger.info(f"{'='*60}")

    start = time.time()
    try:
        # 根据 adapter 类型选择参数
        if hasattr(adapter, '_run_parallel') and use_threads:
            results = adapter.run(task_ids=task_ids_filter, runs_per_task=1, threads=10)
        else:
            results = adapter.run(task_ids=task_ids_filter, runs_per_task=1)

        elapsed = time.time() - start
        logger.info(f"\n{name} COMPLETED in {elapsed:.1f}s ({elapsed/60:.1f} min)")
        logger.info(f"Overall Score: {results['overall_score']:.1f}%")
        if 'passed_tasks' in results:
            logger.info(f"Passed: {results['passed_tasks']}/{results['total_tasks']}")
        else:
            logger.info(f"Total Tasks: {results['total_tasks']}")
        return results, elapsed
    except Exception as e:
        logger.error(f"Error running {name}: {e}")
        import traceback
        traceback.print_exc()
        return None, time.time() - start


def main():
    api_url = os.environ.get('OPENAI_BASE_URL', '')
    api_key = os.environ.get('OPENAI_API_KEY', '')
    model = os.environ.get('MODEL', 'google/gemini-3-flash-preview')

    print(f"=" * 60)
    print(f"NanoBot Benchmark Runner")
    print(f"Model: {model}")
    print(f"API: {api_url}")
    print(f"=" * 60)

    nanopro_dir = script_dir.parent
    workspace = Path('/tmp/benchmarks/workspace_gemini')
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = nanopro_dir / 'assets' / 'results'
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # 1. SkillsBench (87 tasks)
    skillsbench_dir = nanopro_dir / 'benchmarks' / 'skillsbench'
    skills_tasks_dir = skillsbench_dir / 'tasks'
    if skills_tasks_dir.exists():
        logger.info(f"Creating new agent for SkillsBench...")
        agent = NanoBotAgent(model=model, api_url=api_url, api_key=api_key,
                            workspace=workspace, timeout=120)
        adapter = SkillsBenchAdapter(agent=agent, tasks_dir=skills_tasks_dir, output_dir=output_dir)
        adapter.load_tasks()
        logger.info(f"SkillsBench: {len(adapter.tasks)} tasks loaded")
        results['skillsbench'], t = run_benchmark('SkillsBench (87 tasks)', adapter, use_threads=True)
        if results['skillsbench']:
            results['skillsbench']['time'] = t
    else:
        logger.warning(f"SkillsBench tasks dir not found: {skills_tasks_dir}")

    # 2. PinchBench (23 tasks)
    pinchbench_dir = nanopro_dir / 'benchmarks' / 'pinchbench'
    pinch_tasks_dir = pinchbench_dir / 'tasks'
    if pinch_tasks_dir.exists():
        logger.info(f"Creating new agent for PinchBench...")
        agent = NanoBotAgent(model=model, api_url=api_url, api_key=api_key,
                            workspace=workspace, timeout=120)
        adapter = PinchBenchAdapter(agent=agent, tasks_dir=pinch_tasks_dir,
                                   skill_dir=pinchbench_dir, output_dir=output_dir)
        adapter.load_tasks()
        logger.info(f"PinchBench: {len(adapter.tasks)} tasks loaded")
        results['pinchbench'], t = run_benchmark('PinchBench (23 tasks)', adapter, use_threads=False)
        if results['pinchbench']:
            results['pinchbench']['time'] = t
    else:
        logger.warning(f"PinchBench tasks dir not found: {pinch_tasks_dir}")

    # 3. AgentBench-OpenClaw (40 tasks)
    openclawbench_dir = nanopro_dir / 'benchmarks' / 'agentbench-openclaw'
    openclaw_tasks_dir = openclawbench_dir / 'tasks'
    if openclaw_tasks_dir.exists():
        logger.info(f"Creating new agent for AgentBench-OpenClaw...")
        agent = NanoBotAgent(model=model, api_url=api_url, api_key=api_key,
                            workspace=workspace, timeout=120)
        adapter = OpenClawBenchAdapter(agent=agent, tasks_dir=openclaw_tasks_dir, output_dir=output_dir)
        adapter.load_tasks()
        logger.info(f"AgentBench-OpenClaw: {len(adapter.tasks)} tasks loaded")
        results['openclawbench'], t = run_benchmark('AgentBench-OpenClaw (40 tasks)', adapter, use_threads=False)
        if results['openclawbench']:
            results['openclawbench']['time'] = t
    else:
        logger.warning(f"AgentBench-OpenClaw tasks dir not found: {openclaw_tasks_dir}")

    # 汇总
    print("\n" + "=" * 60)
    print("ALL BENCHMARKS COMPLETED")
    print("=" * 60)
    print(f"\nModel: {model}")
    print("\nSummary:")
    for name, data in results.items():
        if data:
            score = data.get('overall_score', 'N/A')
            tasks = data.get('total_tasks', 'N/A')
            passed = data.get('passed_tasks', 'N/A')
            elapsed = data.get('time', 0)
            print(f"  {name}: {score}% ({passed}/{tasks}) - {elapsed:.0f}s")

    # 保存汇总结果
    summary = {
        'model': model,
        'timestamp': time.time(),
        'benchmarks': results
    }
    summary_path = output_dir / f'summary_gemini3_{int(time.time())}.json'
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nSummary saved to: {summary_path}")
    print("=" * 60)

if __name__ == '__main__':
    main()
