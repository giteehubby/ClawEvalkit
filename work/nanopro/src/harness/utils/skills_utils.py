"""
统一 Skills 加载工具

提供统一的接口将 benchmark 提供的 skills 复制到 workspace 的标准位置。
SkillsLoader 会从 workspace/skills/ 目录加载 skill cards。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    pass

# Benchmark -> Skills 配置映射
# global: 全局 skills 目录（所有任务共享）
# per_task: per-task skills 目录（相对于 task dir）
BENCHMARK_SKILLS_CONFIG: Dict[str, Dict[str, Optional[str]]] = {
    "pinchbench": {
        "global": "~/.openclaw/workspace/skills",
        "per_task": None,
    },
    "openclawbench": {
        "global": "~/.openclaw/workspace/skills",
        "per_task": None,
    },
    "skillsbench": {
        "global": None,
        "per_task": "environment/skills",  # 相对于 task dir
    },
    "clawbench_official": {
        "global": "skills/curated",  # 相对于 benchmark dir
        "per_task": None,
    },
    "claw-bench-tribe": {
        "global": None,  # 容器内处理
        "per_task": None,
    },
    "skillbench": {
        "global": None,  # Harbor 管理
        "per_task": None,
    },
    "wildclawbench": {
        "global": "skills",  # 相对于 benchmark dir
        "per_task": None,  # per-task 从 pool 复制
    },
    "scikillbench": {
        "global": None,  # 无 skills
        "per_task": None,
    },
}


def copy_skills_to_workspace(
    workspace: Path,
    benchmark_name: str,
    task_dir: Optional[Path] = None,
    benchmark_dir: Optional[Path] = None,
) -> bool:
    """将 skills 复制到 workspace 的标准位置

    Args:
        workspace: 任务 workspace 目录
        benchmark_name: benchmark 名称
        task_dir: 任务目录（用于 per-task skills）
        benchmark_dir: benchmark 根目录（用于全局 skills）

    Returns:
        是否成功加载了至少一个 skill
    """
    skills_dest = workspace / "skills"
    skills_dest.mkdir(parents=True, exist_ok=True)

    loaded = False
    config = BENCHMARK_SKILLS_CONFIG.get(benchmark_name, {})

    # 1. 加载全局 skills
    global_path = config.get("global")
    if global_path and benchmark_dir:
        # 支持相对路径（相对于 benchmark_dir）和绝对路径
        if Path(global_path).is_absolute():
            global_skills = Path(global_path).expanduser()
        else:
            global_skills = benchmark_dir / global_path

        if global_skills.exists():
            for skill_dir in global_skills.iterdir():
                if skill_dir.is_dir():
                    dest = skills_dest / skill_dir.name
                    if dest.exists():
                        # 已存在，不覆盖
                        continue
                    try:
                        shutil.copytree(skill_dir, dest)
                        loaded = True
                    except Exception:
                        pass

    # 2. 加载 per-task skills
    per_task_path = config.get("per_task")
    if per_task_path and task_dir:
        task_skills = task_dir / per_task_path
        if task_skills.exists():
            for skill_dir in task_skills.iterdir():
                if skill_dir.is_dir():
                    dest = skills_dest / skill_dir.name
                    if dest.exists():
                        continue
                    try:
                        shutil.copytree(skill_dir, dest)
                        loaded = True
                    except Exception:
                        pass

    return loaded


def get_skills_summary(workspace: Path) -> Optional[str]:
    """从 workspace 加载 skills 并构建 summary

    Args:
        workspace: 任务 workspace 目录

    Returns:
        XML 格式的 skills summary，如果无 skills 则返回 None
    """
    if not workspace:
        return None

    try:
        from nanobot.agent.skills import SkillsLoader

        skills_loader = SkillsLoader(workspace)
        all_skills = skills_loader.list_skills(filter_unavailable=False)

        if not all_skills:
            return None

        return skills_loader.build_skills_summary()
    except Exception:
        return None
