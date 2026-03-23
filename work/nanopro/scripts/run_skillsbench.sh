#!/bin/bash
# 运行 SkillsBench 并行测试

cd "$(dirname "$0")"

export PYTHONPATH="$(pwd):$PYTHONPATH"

python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('/Volumes/F/Clauding/.env')

import sys
import logging
import time
from pathlib import Path

sys.path.insert(0, str(Path('.').absolute()))

from agent.nanobot import NanoBotAgent
from adapters.skillsbench import SkillsBenchAdapter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)

api_url = os.environ.get('OPENAI_BASE_URL', '')
api_key = os.environ.get('OPENAI_API_KEY', '')
model = os.environ.get('MODEL', 'gpt-4o-mini')
threads = int(os.environ.get('THREADS', '10'))

print(f'API URL: {api_url}')
print(f'Model: {model}')
print(f'Threads: {threads}')

benchmarks_dir = Path(__file__).parent.parent
skillsbench_dir = benchmarks_dir / 'skillsbench'
tasks_dir = skillsbench_dir / 'tasks'

workspace = Path('/tmp/benchmarks/workspace')
workspace.mkdir(parents=True, exist_ok=True)

output_dir = benchmarks_dir / 'results'
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
print(f'Overall Score: {results[\"overall_score\"]:.1f}%')
print(f'Passed: {results[\"passed_tasks\"]}/{results[\"total_tasks\"]} tasks')
print(f'Results saved to: {output_dir}')
print('=' * 60)
"
