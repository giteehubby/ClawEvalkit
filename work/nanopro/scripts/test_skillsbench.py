#!/usr/bin/env python3
"""
测试脚本 - 验证 SkillsBench 评估流程

只运行几个简单任务来验证整个流程是否正常。
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
from src.runners.adapters.skillsbench import SkillsBenchAdapter

# API 配置 - 从环境变量获取
API_URL = os.environ.get("OPENAI_BASE_URL", "") or os.environ.get("API_URL", "")
API_KEY = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("API_KEY", "")
MODEL = os.environ.get("MODEL", "gpt-4o-mini")


def main():
    print("=" * 60)
    print("SkillsBench Test Run - Quick Validation")
    print("=" * 60)

    if not API_URL or not API_KEY:
        print("\n❌ Missing API configuration!")
        print("Please set API_URL and API_KEY environment variables:")
        print("  export OPENAI_BASE_URL=https://openrouter.ai/api/v1")
        print("  export OPENAI_API_KEY=your-api-key")
        print("  export MODEL=gpt-4o-mini")
        sys.exit(1)

    print(f"\nAPI URL: {API_URL}")
    print(f"Model: {MODEL}")

    # 路径设置
    benchmarks_dir = Path(__file__).parent.parent
    skillsbench_dir = benchmarks_dir / "skillsbench"
    tasks_dir = skillsbench_dir / "tasks"

    if not tasks_dir.exists():
        print(f"\n❌ Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    # 创建工作目录
    workspace = Path("/tmp/benchmarks/test_workspace")
    workspace.mkdir(parents=True, exist_ok=True)

    # 创建输出目录
    output_dir = benchmarks_dir / "results" / "test_skillsbench"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建 Agent
    print("\n🔧 Creating NanoBot Agent...")
    agent = NanoBotAgent(
        model=MODEL,
        api_url=API_URL,
        api_key=API_KEY,
        workspace=workspace,
        timeout=300,
    )
    print("✅ Agent created!")

    # 创建适配器
    print("\n📂 Initializing SkillsBench adapter...")
    adapter = SkillsBenchAdapter(
        agent=agent,
        tasks_dir=tasks_dir,
        output_dir=output_dir,
    )

    # 只加载 easy 难度任务测试
    adapter.load_tasks(difficulty="easy")
    print(f"✅ Loaded {len(adapter.tasks)} tasks!")

    if not adapter.tasks:
        print("\n❌ No tasks loaded!")
        sys.exit(1)

    # 显示任务列表
    print("\nTasks to run:")
    for task in adapter.tasks[:10]:
        print(f"  - {task.task_id} ({task.difficulty}, {task.category})")

    if len(adapter.tasks) > 10:
        print(f"  ... and {len(adapter.tasks) - 10} more")

    # 运行任务测试
    print("\n🚀 Running tasks...")
    results = adapter.run(
        task_ids=None,
        runs_per_task=1,
    )

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Overall Score: {results['overall_score']:.1f}%")
    print(f"Passed: {results['passed_tasks']}/{results['total_tasks']} tasks")

    if results.get('task_scores'):
        print("\nTask Scores:")
        for task_id, data in list(results['task_scores'].items())[:10]:
            status = "✅" if data['passed'] else "❌"
            print(f"  {status} {task_id}: {data['mean']:.1f}% ({data['difficulty']})")

    if results.get('category_scores'):
        print("\nCategory Scores:")
        for category, data in results['category_scores'].items():
            print(f"  {category}: {data['score']:.1f}% ({data['count']} tasks)")

    if results.get('difficulty_scores'):
        print("\nDifficulty Scores:")
        for diff, data in results['difficulty_scores'].items():
            print(f"  {diff}: {data['score']:.1f}% ({data['count']} tasks)")

    print(f"\n✅ Results saved to: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
