from __future__ import annotations

import json
import pathlib
import subprocess
from typing import Dict, Optional

from harness.task_pack import TaskSpec, TaskPack


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "version"], check=True, capture_output=True)
        return True
    except Exception:
        return False


def run_task(
    *,
    pack: TaskPack,
    task: TaskSpec,
    mode: str,
    skill_path: Optional[pathlib.Path],
    skills: list[pathlib.Path],
    output_dir: pathlib.Path,
    image: str,
    agent_cmd: Optional[str],
    agent_model: Optional[str],
    include_skill_body: bool,
) -> Dict:
    """
    Run a single task in Docker and return a result dict.
    This is a stub that assembles the docker command but does not enforce real execution yet.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if not _docker_available():
        return {
            "task_id": task.id,
            "mode": mode,
            "status": "docker_unavailable",
            "notes": "Docker not available; skipping execution.",
        }

    repo_root = pack.manifest_path.parent.parent.parent  # packs/<domain>/<pack>

    if skill_path and not skill_path.exists():
        return {
            "task_id": task.id,
            "mode": mode,
            "status": "skill_not_found",
            "notes": f"Skill path not found: {skill_path}",
        }

    volume_flags = [
        "-v",
        f"{repo_root.parent}:/bench:ro",
        "-v",
        f"{output_dir}:/output",
    ]
    if skill_path:
        volume_flags.extend(["-v", f"{skill_path}:/skill:ro"])
    extra_skill_paths = [p for p in skills if p.exists()]
    extra_mounts = []
    extra_container_paths = []
    for idx, path in enumerate(extra_skill_paths):
        container_path = f"/skills/skill-{idx}"
        extra_mounts.extend(["-v", f"{path}:{container_path}:ro"])
        extra_container_paths.append(container_path)
    volume_flags.extend(extra_mounts)

    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "-w",
        "/bench",
        *volume_flags,
    ]
    if agent_cmd:
        cmd.extend(["-e", f"SKILLBENCH_AGENT_CMD={agent_cmd}"])
    if agent_model:
        cmd.extend(["-e", f"SKILLBENCH_AGENT_MODEL={agent_model}"])
    if include_skill_body:
        cmd.extend(["-e", "SKILLBENCH_INCLUDE_SKILL_BODY=1"])
    if skill_path:
        cmd.extend(["-e", "SKILLBENCH_SKILL_PATH=/skill"])
    if extra_container_paths:
        cmd.extend(["-e", f"SKILLBENCH_SKILL_PATHS={','.join(extra_container_paths)}"])
    cmd.extend(
        [
            image,
            "python3",
            "-m",
            "harness.run_task",
            "--pack",
            f"{pack.manifest_path.parent.relative_to(repo_root.parent)}",
            "--task-id",
            task.id,
            "--mode",
            mode,
            "--output",
            f"/output/{task.id}.json",
        ]
    )

    if skill_path:
        cmd.extend(["--skill", "/skill"])

    output_path = output_dir / f"{task.id}.json"
    try:
        subprocess.run(cmd, check=True)
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


def infer_task(
    *,
    pack: TaskPack,
    task: TaskSpec,
    mode: str,
    skill_path: Optional[pathlib.Path],
    skills: list[pathlib.Path],
    output_dir: pathlib.Path,
    image: str,
    agent_cmd: Optional[str],
    agent_model: Optional[str],
    include_skill_body: bool,
) -> Dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{task.id}.diff"

    repo_root = pack.manifest_path.parent.parent.parent
    volume_flags = [
        "-v",
        f"{repo_root.parent}:/bench:ro",
        "-v",
        f"{output_dir}:/output",
    ]
    if skill_path:
        volume_flags.extend(["-v", f"{skill_path}:/skill:ro"])
    extra_skill_paths = [p for p in skills if p.exists()]
    extra_mounts = []
    extra_container_paths = []
    for idx, path in enumerate(extra_skill_paths):
        container_path = f"/skills/skill-{idx}"
        extra_mounts.extend(["-v", f"{path}:{container_path}:ro"])
        extra_container_paths.append(container_path)
    volume_flags.extend(extra_mounts)

    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "-w",
        "/bench",
        *volume_flags,
    ]
    if agent_cmd:
        cmd.extend(["-e", f"SKILLBENCH_AGENT_CMD={agent_cmd}"])
    if agent_model:
        cmd.extend(["-e", f"SKILLBENCH_AGENT_MODEL={agent_model}"])
    if include_skill_body:
        cmd.extend(["-e", "SKILLBENCH_INCLUDE_SKILL_BODY=1"])
    if skill_path:
        cmd.extend(["-e", "SKILLBENCH_SKILL_PATH=/skill"])
    if extra_container_paths:
        cmd.extend(["-e", f"SKILLBENCH_SKILL_PATHS={','.join(extra_container_paths)}"])

    cmd.extend(
        [
            image,
            "python3",
            "-m",
            "harness.infer_task",
            "--pack",
            f"{pack.manifest_path.parent.relative_to(repo_root.parent)}",
            "--task-id",
            task.id,
            "--mode",
            mode,
            "--output",
            f"/output/{task.id}.diff",
        ]
    )
    if skill_path:
        cmd.extend(["--skill", "/skill"])

    try:
        subprocess.run(cmd, check=True)
        return {
            "task_id": task.id,
            "mode": mode,
            "status": "executed",
            "output": str(output_path),
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
    image: str,
) -> Dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{task.id}.json"

    repo_root = pack.manifest_path.parent.parent.parent
    volume_flags = [
        "-v",
        f"{repo_root.parent}:/bench:ro",
        "-v",
        f"{output_dir}:/output",
        "-v",
        f"{patch_path}:/patch.diff:ro",
    ]

    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "-w",
        "/bench",
        *volume_flags,
        "-e",
        "SKILLBENCH_PATCH_PATH=/patch.diff",
        image,
        "python3",
        "-m",
        "harness.run_task",
        "--pack",
        f"{pack.manifest_path.parent.relative_to(repo_root.parent)}",
        "--task-id",
        task.id,
        "--mode",
        mode,
        "--output",
        f"/output/{task.id}.json",
    ]

    try:
        subprocess.run(cmd, check=True)
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
