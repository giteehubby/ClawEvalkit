from __future__ import annotations

import json
import pathlib
import os
import subprocess
from typing import Dict, Optional

from harness.task_pack import TaskSpec, TaskPack


def run_task(
    *,
    pack: TaskPack,
    task: TaskSpec,
    mode: str,
    skill_path: Optional[pathlib.Path],
    skills: list[pathlib.Path],
    output_dir: pathlib.Path,
    agent_cmd: Optional[str],
    agent_model: Optional[str],
    include_skill_body: bool,
) -> Dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{task.id}.json"

    env = None
    if agent_cmd or skill_path or agent_model or include_skill_body:
        env = os.environ.copy()
        if agent_cmd:
            env["SKILLBENCH_AGENT_CMD"] = agent_cmd
        if agent_model:
            env["SKILLBENCH_AGENT_MODEL"] = agent_model
        if include_skill_body:
            env["SKILLBENCH_INCLUDE_SKILL_BODY"] = "1"
        if skill_path:
            env["SKILLBENCH_SKILL_PATH"] = str(skill_path)
        if skills:
            env["SKILLBENCH_SKILL_PATHS"] = ",".join(str(p) for p in skills)

    repo_root = pack.manifest_path.parent.parent.parent.parent
    pack_rel = pack.manifest_path.parent.relative_to(repo_root)

    cmd = [
        "python3",
        "-m",
        "harness.run_task",
        "--pack",
        str(pack_rel),
        "--task-id",
        task.id,
        "--mode",
        mode,
        "--output",
        str(output_path),
    ]

    if skill_path:
        cmd.extend(["--skill", str(skill_path)])

    try:
        subprocess.run(cmd, check=True, env=env, cwd=repo_root)
        meta_path = output_path.with_suffix(".json")
        result_payload = None
        if meta_path.exists():
            try:
                result_payload = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                result_payload = None
        return {
            "task_id": task.id,
            "mode": mode,
            "status": "executed",
            "output": str(output_path),
            "result": result_payload,
        }
    except subprocess.CalledProcessError as exc:
        return {
            "task_id": task.id,
            "mode": mode,
            "status": "failed",
            "error": str(exc),
        }


def infer_task(
    *,
    pack: TaskPack,
    task: TaskSpec,
    mode: str,
    skill_path: Optional[pathlib.Path],
    skills: list[pathlib.Path],
    output_dir: pathlib.Path,
    agent_cmd: Optional[str],
    agent_model: Optional[str],
    include_skill_body: bool,
) -> Dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{task.id}.diff"

    env = os.environ.copy()
    if agent_cmd:
        env["SKILLBENCH_AGENT_CMD"] = agent_cmd
    if agent_model:
        env["SKILLBENCH_AGENT_MODEL"] = agent_model
    if include_skill_body:
        env["SKILLBENCH_INCLUDE_SKILL_BODY"] = "1"
    if skill_path:
        env["SKILLBENCH_SKILL_PATH"] = str(skill_path)
    if skills:
        env["SKILLBENCH_SKILL_PATHS"] = ",".join(str(p) for p in skills)

    repo_root = pack.manifest_path.parent.parent.parent.parent
    pack_rel = pack.manifest_path.parent.relative_to(repo_root)

    cmd = [
        "python3",
        "-m",
        "harness.infer_task",
        "--pack",
        str(pack_rel),
        "--task-id",
        task.id,
        "--mode",
        mode,
        "--output",
        str(output_path),
    ]
    if skill_path:
        cmd.extend(["--skill", str(skill_path)])

    try:
        subprocess.run(cmd, check=True, env=env, cwd=repo_root)
        result_payload = None
        if output_path.exists():
            try:
                result_payload = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                result_payload = None
        return {
            "task_id": task.id,
            "mode": mode,
            "status": "executed",
            "output": str(output_path),
            "result": result_payload,
        }
    except subprocess.CalledProcessError as exc:
        return {
            "task_id": task.id,
            "mode": mode,
            "status": "failed",
            "error": str(exc),
        }


def eval_task(
    *,
    pack: TaskPack,
    task: TaskSpec,
    mode: str,
    patch_path: pathlib.Path,
    output_dir: pathlib.Path,
) -> Dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{task.id}.json"

    env = os.environ.copy()
    env["SKILLBENCH_PATCH_PATH"] = str(patch_path)

    repo_root = pack.manifest_path.parent.parent.parent.parent
    pack_rel = pack.manifest_path.parent.relative_to(repo_root)

    cmd = [
        "python3",
        "-m",
        "harness.run_task",
        "--pack",
        str(pack_rel),
        "--task-id",
        task.id,
        "--mode",
        mode,
        "--output",
        str(output_path),
    ]

    try:
        subprocess.run(cmd, check=True, env=env, cwd=repo_root)
        result_payload = None
        if output_path.exists():
            try:
                result_payload = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                result_payload = None
        return {
            "task_id": task.id,
            "mode": mode,
            "status": "executed",
            "output": str(output_path),
            "result": result_payload,
        }
    except subprocess.CalledProcessError as exc:
        return {
            "task_id": task.id,
            "mode": mode,
            "status": "failed",
            "error": str(exc),
        }
