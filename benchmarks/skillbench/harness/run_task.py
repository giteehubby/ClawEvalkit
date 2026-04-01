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
    parser = argparse.ArgumentParser(description="Run a single task inside the sandbox")
    parser.add_argument("--pack", required=True, help="Task pack path (relative to repo root)")
    parser.add_argument("--task-id", required=True, help="Task identifier")
    parser.add_argument("--mode", choices=["baseline", "augmented"], required=True)
    parser.add_argument("--skill", help="Skill path (optional)")
    parser.add_argument("--output", required=True, help="Output JSON path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    pack_path = repo_root / args.pack
    repo_root = pack_path.parent.parent.parent
    task_pack = load_task_pack(pack_path)
    task = next((t for t in task_pack.tasks if t.id == args.task_id), None)
    if task is None:
        raise SystemExit(f"Task {args.task_id} not found in {pack_path}")

    task_root = pack_path / (task.path or f"tasks/{task.id}")
    repo_src = pack_path / (task.repo_path or f"tasks/{task.id}/repo")
    if not repo_src.exists():
        raise SystemExit(f"Repo source not found: {repo_src}")

    workspace_root = pathlib.Path("/tmp/skillbench") / task.id / args.mode
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
    shutil.copytree(repo_src, workspace_root)

    agent_cmd = os.environ.get("SKILLBENCH_AGENT_CMD")
    skill_path = os.environ.get("SKILLBENCH_SKILL_PATH") if args.skill else None
    patch_path = os.environ.get("SKILLBENCH_PATCH_PATH")

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
            output_path = pathlib.Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            sys.exit(2)

    # Optional multi-skill composability support
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

    if patch_path:
        patch_file = pathlib.Path(patch_path)
        if patch_file.exists() and patch_file.read_text(encoding="utf-8").strip():
            patch_text = patch_file.read_text(encoding="utf-8")
            proc = subprocess.run(
                ["patch", "-p1"],
                input=patch_text,
                text=True,
                cwd=workspace_root,
                capture_output=True,
            )
            if proc.returncode != 0:
                proc = subprocess.run(
                    ["patch", "-p0"],
                    input=patch_text,
                    text=True,
                    cwd=workspace_root,
                    capture_output=True,
                )
            if proc.returncode != 0:
                result = {
                    "task_id": task.id,
                    "mode": args.mode,
                    "pack": task_pack.name,
                    "status": "patch_failed",
                    "stderr": proc.stderr[-2000:],
                }
                output_path = pathlib.Path(args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
                sys.exit(2)

    agent_status = None
    agent_stdout = ""
    agent_stderr = ""
    agent_error = None
    agent_trace_path = None
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
        # Set trace output path for the agent
        trace_dir = pathlib.Path(args.output).parent / "traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        agent_trace_path = trace_dir / f"{task.id}-{args.mode}-trace.json"
        env["SKILLBENCH_TRACE_OUTPUT"] = str(agent_trace_path)
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

    evaluate_sh = task_root / "evaluate.sh"
    evaluate_py = task_root / "evaluate.py"

    perturbation = os.environ.get("SKILLBENCH_PERTURBATION")
    if perturbation == "tool_failure":
        result = {
            "task_id": task.id,
            "mode": args.mode,
            "pack": task_pack.name,
            "skill": args.skill,
            "status": "failed",
            "exit_code": 2,
            "runtime_s": 0.0,
            "stdout": "",
            "stderr": "Injected tool failure",
            "perturbation": "tool_failure",
        }
        output_path = pathlib.Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return
    if perturbation == "ambiguous_instructions":
        result = {
            "task_id": task.id,
            "mode": args.mode,
            "pack": task_pack.name,
            "skill": args.skill,
            "status": "failed",
            "exit_code": 2,
            "runtime_s": 0.0,
            "stdout": "",
            "stderr": "Injected ambiguity",
            "perturbation": "ambiguous_instructions",
        }
        output_path = pathlib.Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return
    if perturbation == "missing_fields":
        result = {
            "task_id": task.id,
            "mode": args.mode,
            "pack": task_pack.name,
            "skill": args.skill,
            "status": "failed",
            "exit_code": 2,
            "runtime_s": 0.0,
            "stdout": "",
            "stderr": "Injected missing fields",
            "perturbation": "missing_fields",
        }
        output_path = pathlib.Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return

    if evaluate_sh.exists():
        cmd = ["bash", str(evaluate_sh)]
    elif evaluate_py.exists():
        cmd = ["python3", str(evaluate_py)]
    else:
        cmd = ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]

    start = time.time()
    completed = subprocess.run(
        cmd,
        cwd=workspace_root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    elapsed = time.time() - start

    result = {
        "task_id": task.id,
        "mode": args.mode,
        "pack": task_pack.name,
        "skill": args.skill,
        "agent_cmd": agent_cmd,
        "agent_status": agent_status,
        "skill_name": None if skill_spec is None else skill_spec.name,
        "skill_description": None if skill_spec is None else skill_spec.description,
        "skill_names": installed_skill_names,
        "skill_count": len(installed_skill_names),
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "runtime_s": round(elapsed, 3),
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }
    if agent_cmd:
        result["agent_timeout_s"] = agent_timeout_s
        result["agent_stdout"] = agent_stdout
        result["agent_stderr"] = agent_stderr
        if agent_error:
            result["agent_error"] = agent_error
        if agent_trace_path and agent_trace_path.exists():
            result["trace_path"] = str(agent_trace_path)
    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
