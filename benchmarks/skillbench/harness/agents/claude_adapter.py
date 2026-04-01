#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import subprocess
import sys


def _read_file(path: pathlib.Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def build_prompt() -> str:
    task_path = os.environ.get("SKILLBENCH_TASK_PATH")
    skill_path = os.environ.get("SKILLBENCH_SKILL_PATH")
    skill_name = os.environ.get("SKILLBENCH_SKILL_NAME")
    skill_desc = os.environ.get("SKILLBENCH_SKILL_DESCRIPTION")

    task_text = ""
    if task_path:
        task_md = pathlib.Path(task_path) / "TASK.md"
        task_text = _read_file(task_md)

    skill_text = ""
    if skill_path:
        skill_md = pathlib.Path(skill_path) / "SKILL.md"
        skill_text = _read_file(skill_md)

    prompt_parts = [
        "You are an autonomous code agent.",
        "Work in the current repository. Make minimal changes to satisfy the task.",
        "Run the test command described in the task instructions.",
    ]
    if task_text:
        prompt_parts.append("\nTASK:\n" + task_text)
    if skill_name and skill_desc:
        prompt_parts.append(f"\nSKILL METADATA:\nname: {skill_name}\ndescription: {skill_desc}")
        prompt_parts.append(
            "\nThe skill is installed at .claude/skills; load SKILL.md or other files only if needed."
        )
    if skill_text and os.environ.get("SKILLBENCH_INCLUDE_SKILL_BODY") == "1":
        prompt_parts.append("\nSKILL CONTEXT:\n" + skill_text)
    return "\n".join(prompt_parts)


def main() -> int:
    prompt = build_prompt()
    model = os.environ.get("SKILLBENCH_AGENT_MODEL")

    cmd = [
        "claude",
        "--print",
        "--permission-mode",
        "bypassPermissions",
        "--add-dir",
        ".",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)

    try:
        completed = subprocess.run(cmd, check=False)
        return completed.returncode
    except FileNotFoundError:
        print("claude CLI not found in PATH", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main())
