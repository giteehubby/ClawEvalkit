#!/usr/bin/env python3
"""
测试脚本 - 验证 pinchbench 评估流程

只运行 sanity check 任务来验证整个流程是否正常。
"""

import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 配置
load_dotenv("/Volumes/F/Clauding/.env")

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.harness.agent.nanobot import NanoBotAgent
from src.runners.adapters.pinchbench import PinchBenchAdapter

# API 配置 - 从环境变量获取
API_URL = os.environ.get("OPENAI_BASE_URL", "") or os.environ.get("API_URL", "")
API_KEY = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("API_KEY", "")
MODEL = os.environ.get("MODEL", "gpt-4o-mini")


def main():
    print("=" * 60)
    print("PinchBench Test Run - Sanity Check Only")
    print("=" * 60)

    if not API_URL or not API_KEY:
        print("\n❌ Missing API configuration!")
        print("Please set API_URL and API_KEY environment variables:")
        print("  export API_URL=https://openrouter.ai/api/v1")
        print("  export API_KEY=your-api-key")
        print("  export MODEL=gpt-4o-mini")
        sys.exit(1)

    print(f"\nAPI URL: {API_URL}")
    print(f"Model: {MODEL}")

    # 路径设置
    benchmarks_dir = Path(__file__).parent.parent
    pinchbench_dir = benchmarks_dir / "pinchbench"
    tasks_dir = pinchbench_dir / "tasks"

    if not tasks_dir.exists():
        print(f"\n❌ Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    # 创建工作目录
    workspace = Path("/tmp/benchmarks/test_workspace")
    workspace.mkdir(parents=True, exist_ok=True)

    # 创建输出目录
    output_dir = benchmarks_dir / "results" / "test"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建 Agent
    print("\n🔧 Creating NanoBot Agent...")
    agent = NanoBotAgent(
        model=MODEL,
        api_url=API_URL,
        api_key=API_KEY,
        workspace=workspace,
        timeout=120,
    )
    print("✅ Agent created!")

    # 创建适配器
    print("\n📂 Initializing PinchBench adapter...")
    adapter = PinchBenchAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        skill_dir=pinchbench_dir,
        output_dir=output_dir,
    )
    adapter.load_tasks()
    print(f"✅ Loaded {len(adapter.tasks)} tasks!")

    # 运行多个任务测试
    print("\n🚀 Running 5 tasks...")
    results = adapter.run(
        task_ids=["task_00_sanity", "task_01_calendar", "task_04_weather", "task_08_memory", "task_09_files"],
        runs_per_task=1,
    )

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Overall Score: {results['overall_score']:.1f}%")
    print(f"Total Tasks: {results['total_tasks']}")

    if results.get('task_scores'):
        print("\nTask Scores:")
        for task_id, data in results['task_scores'].items():
            print(f"  {task_id}: {data['mean']:.2f}")

    print(f"\n✅ Results saved to: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
