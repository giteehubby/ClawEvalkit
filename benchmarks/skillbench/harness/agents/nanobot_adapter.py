#!/usr/bin/env python3
"""NanoBotAgent adapter for SkillBench harness.

替代 ark_adapter.py。NanoBotAgent 直接在 repo workspace 中使用内置 tools
(ReadFile, EditFile, WriteFile, Exec) 修改代码，而非生成 diff patch 再 apply。

环境变量 (harness 自动设置):
  OPENAI_API_KEY          — API key
  OPENAI_API_URL          — API base URL (e.g. https://openrouter.ai/api/v1)
  SKILLBENCH_AGENT_MODEL  — model name (e.g. anthropic/claude-sonnet-4.6)
  SKILLBENCH_TASK_PATH    — task directory (auto-set by harness)
  SKILLBENCH_REPO_PATH    — workspace directory (auto-set by harness)
  SKILLBENCH_SKILL_PATH   — optional skill directory
"""
from __future__ import annotations

import os
import pathlib
import sys


def _import_nanobot_agent():
    """导入 NanoBotAgent，搜索优先级：pip 包 → env var → 仓库子目录。"""
    try:
        from openclawpro.harness.agent import NanoBotAgent
        return NanoBotAgent
    except ImportError:
        pass

    candidates = [
        os.getenv("OPENCLAWPRO_DIR"),
    ]
    # 从当前文件向上找到仓库根目录的 OpenClawPro/
    current = pathlib.Path(__file__).resolve()
    for _ in range(10):
        current = current.parent
        candidate = current / "OpenClawPro"
        if (candidate / "harness" / "agent" / "nanobot.py").exists():
            candidates.append(str(candidate))
            break

    for path_str in candidates:
        if not path_str:
            continue
        p = pathlib.Path(path_str)
        if (p / "harness" / "agent" / "nanobot.py").exists():
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            from harness.agent.nanobot import NanoBotAgent
            return NanoBotAgent

    raise ImportError("NanoBotAgent not found. Set OPENCLAWPRO_DIR env var.")


def _read_file(path: pathlib.Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def main() -> int:
    """主入口：读取任务 → 创建 NanoBotAgent → 在 repo 中直接修改代码。"""
    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_API_URL", "https://openrouter.ai/api/v1")
    model = os.environ.get("SKILLBENCH_AGENT_MODEL")

    if not api_key:
        print("OPENAI_API_KEY is required", file=sys.stderr)
        return 2
    if not model:
        print("SKILLBENCH_AGENT_MODEL is required", file=sys.stderr)
        return 2

    NanoBotAgent = _import_nanobot_agent()

    repo_path = pathlib.Path(os.environ.get("SKILLBENCH_REPO_PATH", "."))
    task_path = os.environ.get("SKILLBENCH_TASK_PATH", "")
    skill_path = os.environ.get("SKILLBENCH_SKILL_PATH", "")

    # 读取任务描述
    task_text = ""
    if task_path:
        task_md = pathlib.Path(task_path) / "TASK.md"
        task_text = _read_file(task_md)

    # 读取可选的 skill 上下文
    skill_text = ""
    if skill_path and os.environ.get("SKILLBENCH_INCLUDE_SKILL_BODY") == "1":
        skill_md = pathlib.Path(skill_path) / "SKILL.md"
        skill_text = _read_file(skill_md)

    # 构建 prompt
    prompt_parts = [
        "You are an expert code agent working in a repository.",
        f"The repository is at: {repo_path}",
        "Read the source files, understand the code, and modify files directly to fix the issue.",
        "",
        "Task instructions:",
        task_text,
    ]
    if skill_text:
        prompt_parts.extend(["", "Skill context:", skill_text])

    prompt = "\n".join(prompt_parts)

    # 创建 NanoBotAgent，workspace 指向 repo 目录
    agent = NanoBotAgent(
        model=model,
        api_url=api_base,
        api_key=api_key,
        workspace=repo_path,
        timeout=120,
    )

    try:
        result = agent.execute(prompt)
        return 0 if result.status == "success" else 2
    except Exception as exc:
        print(f"Agent execution failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
