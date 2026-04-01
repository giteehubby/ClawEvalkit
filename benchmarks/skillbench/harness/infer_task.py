#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import shlex
import subprocess
import time
import sys

from harness.task_pack import load_task_pack
from harness.skill_spec import load_skill, install_skill


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run inference to produce a patch for a task")
    parser.add_argument("--pack", required=True, help="Task pack path (relative to repo root)")
    parser.add_argument("--task-id", required=True, help="Task identifier")
    parser.add_argument("--mode", choices=["baseline", "augmented"], required=True)
    parser.add_argument("--skill", help="Skill path (optional)")
    parser.add_argument("--output", required=True, help="Output patch path")
    return parser.parse_args()


def _run_diff(pristine: pathlib.Path, modified: pathlib.Path) -> str:
    parent = pristine.parent
    proc = subprocess.run(
        ["diff", "-ruN", pristine.name, modified.name],
        cwd=parent,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return ""
    if proc.returncode == 1:
        return proc.stdout
    raise RuntimeError(proc.stderr.strip() or "diff failed")


def main() -> None:
    args = parse_args()
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    pack_path = repo_root / args.pack
    task_pack = load_task_pack(pack_path)
    task = next((t for t in task_pack.tasks if t.id == args.task_id), None)
    if task is None:
        raise SystemExit(f"Task {args.task_id} not found in {pack_path}")

    task_root = pack_path / (task.path or f"tasks/{task.id}")
    repo_src = pack_path / (task.repo_path or f"tasks/{task.id}/repo")
    if not repo_src.exists():
        raise SystemExit(f"Repo source not found: {repo_src}")

    workspace_root = pathlib.Path("/tmp/skillbench") / task.id / args.mode
    pristine_root = pathlib.Path("/tmp/skillbench") / task.id / f"{args.mode}-pristine"
    for root in (workspace_root, pristine_root):
        if root.exists():
            shutil.rmtree(root)
        shutil.copytree(repo_src, root)

    agent_cmd = os.environ.get("SKILLBENCH_AGENT_CMD")
    skill_path = os.environ.get("SKILLBENCH_SKILL_PATH") if args.skill else None

    skill_spec = None
    skill_install_path = None
    installed_skill_names = []
    if skill_path:
        try:
            skill_dir = pathlib.Path(skill_path)
            skill_spec = load_skill(skill_dir)
            skill_install_path = install_skill(
                skill_spec,
                workspace_root / ".claude" / "skills",
            )
            installed_skill_names.append(skill_spec.name)
        except Exception as exc:
            result = {
                "task_id": task.id,
                "mode": args.mode,
                "pack": task_pack.name,
                "skill": args.skill,
                "status": "skill_invalid",
                "error": str(exc),
            }
            out = pathlib.Path(args.output).with_suffix(".json")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, indent=2), encoding="utf-8")
            sys.exit(2)

    extra_skills = os.environ.get("SKILLBENCH_SKILL_PATHS")
    installed_skills = []
    if extra_skills:
        for raw in extra_skills.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                extra_spec = load_skill(pathlib.Path(raw))
                extra_path = install_skill(extra_spec, workspace_root / ".claude" / "skills")
                installed_skills.append(extra_path)
                installed_skill_names.append(extra_spec.name)
            except Exception:
                continue

    agent_status = None
    agent_stdout = ""
    agent_stderr = ""
    agent_error = None
    agent_timeout_env = os.environ.get("SKILLBENCH_AGENT_TIMEOUT")
    if agent_timeout_env:
        agent_timeout_s = int(agent_timeout_env)
    else:
        request_timeout = float(os.environ.get("SKILLBENCH_AGENT_REQUEST_TIMEOUT", "120"))
        retries = int(os.environ.get("SKILLBENCH_AGENT_RETRIES", "2"))
        backoff = float(os.environ.get("SKILLBENCH_AGENT_BACKOFF", "1.5"))
        sleep_total = sum(backoff * (2 ** i) for i in range(retries))
        agent_timeout_s = int(request_timeout * (retries + 1) + sleep_total + 10)
    if agent_cmd:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{repo_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
        env["SKILLBENCH_TASK_PATH"] = str(task_root)
        env["SKILLBENCH_REPO_PATH"] = str(workspace_root)
        if skill_spec and skill_install_path:
            env["SKILLBENCH_SKILL_PATH"] = str(skill_install_path)
            env["SKILLBENCH_SKILL_NAME"] = skill_spec.name
            env["SKILLBENCH_SKILL_DESCRIPTION"] = skill_spec.description
        if installed_skills:
            env["SKILLBENCH_SKILL_PATHS"] = ",".join(str(p) for p in installed_skills)
        if installed_skill_names:
            env["SKILLBENCH_SKILL_NAMES"] = ",".join(installed_skill_names)
            env["SKILLBENCH_SKILL_COUNT"] = str(len(installed_skill_names))
        try:
            agent_run = subprocess.run(
                shlex.split(agent_cmd),
                cwd=workspace_root,
                capture_output=True,
                text=True,
                timeout=agent_timeout_s,
                env=env,
            )
            agent_status = agent_run.returncode
            agent_stdout = agent_run.stdout[-2000:]
            agent_stderr = agent_run.stderr[-2000:]
        except subprocess.TimeoutExpired as exc:
            agent_status = "timeout"
            agent_error = f"agent_timeout after {agent_timeout_s}s"
            agent_stdout = (exc.stdout or "")[-2000:]
            agent_stderr = (exc.stderr or "")[-2000:]
        except Exception as exc:
            agent_status = "error"
            agent_error = f"agent_failed: {exc}"

    start = time.time()
    diff_text = _run_diff(pristine_root, workspace_root)
    elapsed = time.time() - start

    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(diff_text, encoding="utf-8")

    result = {
        "task_id": task.id,
        "mode": args.mode,
        "pack": task_pack.name,
        "skill": args.skill,
        "status": "ok",
        "diff_bytes": len(diff_text.encode("utf-8")),
        "runtime_s": round(elapsed, 3),
        "agent_status": agent_status,
        "agent_stdout": agent_stdout,
        "agent_stderr": agent_stderr,
        "skill_names": installed_skill_names,
        "skill_count": len(installed_skill_names),
    }
    if agent_cmd:
        result["agent_timeout_s"] = agent_timeout_s
        if agent_error:
            result["agent_error"] = agent_error
    result_path = output_path.with_suffix(".json")
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
