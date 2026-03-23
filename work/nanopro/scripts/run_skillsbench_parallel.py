#!/usr/bin/env python3
"""
SkillsBench 并行测试脚本
"""

import os
import sys
import logging
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('/Volumes/F/Clauding/.env')

# 添加当前目录到 Python 路径
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from agent.nanobot import NanoBotAgent
from adapters.skillsbench import SkillsBenchAdapter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("benchmark")

def main():
    api_url = os.environ.get('OPENAI_BASE_URL', '')
    api_key = os.environ.get('OPENAI_API_KEY', '')
    model = os.environ.get('MODEL', 'gpt-4o-mini')
    threads = int(os.environ.get('THREADS', '10'))

    print(f'API URL: {api_url}')
    print(f'Model: {model}')
    print(f'Threads: {threads}')

    nanopro_dir = script_dir.parent
    skillsbench_dir = nanopro_dir / 'benchmarks' / 'skillsbench'
    tasks_dir = skillsbench_dir / 'tasks'

    workspace = Path('/tmp/benchmarks/workspace')
    workspace.mkdir(parents=True, exist_ok=True)

    output_dir = nanopro_dir / 'assets' / 'results'
    output_dir.mkdir(parents=True, exist_ok=True)

    agent = NanoBotAgent(
        model=model,
        api_url=api_url,
        api_key=api_key,
        workspace=workspace,
        timeout=120,
    )

    adapter = SkillsBenchAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        output_dir=output_dir,
    )

    adapter.load_tasks()
    print(f'Loaded {len(adapter.tasks)} tasks')

    start_time = time.time()
    results = adapter.run(
        task_ids=None,
        runs_per_task=1,
        threads=threads,
    )

    elapsed = time.time() - start_time

    print('')
    print('=' * 60)
    print('BENCHMARK COMPLETED')
    print('=' * 60)
    print(f'Time elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)')
    print(f'Overall Score: {results["overall_score"]:.1f}%')
    print(f'Passed: {results["passed_tasks"]}/{results["total_tasks"]} tasks')
    print(f'Results saved to: {output_dir}')
    print('=' * 60)

if __name__ == '__main__':
    main()
