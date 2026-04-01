#!/usr/bin/env python3
"""
SkillBench CLI (prototype)

Mirrors SWE-bench's workflow: load task pack, set up environment, run baseline and augmented
evaluations, then emit structured reports.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import sys

from harness.runners import docker_runner
from harness.task_pack import load_task_pack, TaskPack


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Load environment variables from .env file if it exists."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Remove surrounding quotes if present
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        # Don't override existing env vars
        if key not in os.environ:
            os.environ[key] = value


# Load .env file at import time
_load_dotenv()


@dataclass
class RunConfig:
    task_pack: str
    skill_path: Optional[pathlib.Path]
    mode: str  # "baseline" or "augmented"
    output: pathlib.Path
    runner: str
    image: str
    agent_cmd: Optional[str]
    agent: Optional[str]
    agent_model: Optional[str]
    include_skill_body: bool
    skills: list[pathlib.Path]


def parse_args() -> tuple[str, argparse.Namespace]:
    parser = argparse.ArgumentParser(description="Agent Skills Benchmark CLI")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Combined infer + eval (legacy)")
    infer_parser = subparsers.add_parser("infer", help="Generate patches for tasks")
    eval_parser = subparsers.add_parser("eval", help="Evaluate patches with the test harness")
    compare_parser = subparsers.add_parser("compare", help="Compare two eval reports")

    for p in (run_parser, infer_parser, eval_parser):
        p.add_argument(
            "--pack",
            required=True,
            help="Task pack id or path (e.g., coding/swe-lite or packs/coding/swe-lite)",
        )
        p.add_argument("--runner", choices=["docker", "local"], default="docker")
        p.add_argument("--image", default="skillbench/base:0.1.0")

    for p in (run_parser, infer_parser):
        p.add_argument("--skill", help="Path or repo for the skill to test (optional for baseline)")
        p.add_argument("--skills", help="Comma-separated list of skill paths (composability)")
        p.add_argument("--mode", choices=["baseline", "augmented", "both"], default="both")
        p.add_argument("--agent-cmd", help="Command to run as agent")
        p.add_argument("--agent", choices=["mock", "claude", "anthropic", "openai", "agentic"], help="Named agent adapter")
        p.add_argument("--agent-model", help="Model name for agent adapter (if supported)")
        p.add_argument("--include-skill-body", action="store_true", help="Inline SKILL.md into prompt for API agents")

    run_parser.add_argument("--output", default=str(REPO_ROOT / "reports" / "latest.json"))
    infer_parser.add_argument("--predictions", default=str(REPO_ROOT / "predictions"))

    eval_parser.add_argument("--predictions", required=True, help="Path to predictions directory")
    eval_parser.add_argument("--predictions-file", help="Optional predictions JSONL file")
    eval_parser.add_argument("--mode", choices=["baseline", "augmented"], required=True)
    eval_parser.add_argument("--output", default=str(REPO_ROOT / "reports" / "latest.json"))

    compare_parser.add_argument("--baseline", required=True, help="Baseline report JSON")
    compare_parser.add_argument("--augmented", required=True, help="Augmented report JSON")
    compare_parser.add_argument("--output", default=str(REPO_ROOT / "reports" / "delta.json"))
    compare_parser.add_argument("--profile-output", help="Optional profile-only JSON output")
    compare_parser.add_argument("--robustness-baseline", help="Robustness JSON for baseline (single)")
    compare_parser.add_argument("--robustness-augmented", help="Robustness JSON for augmented (single)")
    compare_parser.add_argument("--robustness-dir", help="Directory containing robustness JSON files")

    argv = None
    if len(sys.argv) > 1 and sys.argv[1] not in {"run", "infer", "eval", "compare"}:
        argv = ["run", *sys.argv[1:]]
    args = parser.parse_args(argv)
    command = args.command or "run"
    return command, args


def _resolve_run_config(args: argparse.Namespace) -> RunConfig:
    skill_path = pathlib.Path(args.skill).resolve() if getattr(args, "skill", None) else None
    skills_list = []
    skills_raw = getattr(args, "skills", None)
    if skills_raw:
        for part in skills_raw.split(","):
            part = part.strip()
            if part:
                skills_list.append(pathlib.Path(part).resolve())
    agent = getattr(args, "agent", None)
    agent_cmd = getattr(args, "agent_cmd", None)
    if not agent_cmd and agent == "mock":
        agent_cmd = "python3 -m harness.agents.mock_solver"
    if not agent_cmd and agent == "claude":
        agent_cmd = "python3 -m harness.agents.claude_adapter"
    if not agent_cmd and agent == "anthropic":
        agent_cmd = "python3 -m harness.agents.anthropic_adapter"
    if not agent_cmd and agent == "openai":
        agent_cmd = "python3 -m harness.agents.openai_adapter"
    if not agent_cmd and agent == "agentic":
        agent_cmd = "python3 -m harness.agents.agentic_adapter"

    return RunConfig(
        task_pack=args.pack,
        skill_path=skill_path,
        mode=args.mode,
        output=pathlib.Path(getattr(args, "output", REPO_ROOT / "reports" / "latest.json")).resolve(),
        runner=args.runner,
        image=args.image,
        agent_cmd=agent_cmd,
        agent=agent,
        agent_model=getattr(args, "agent_model", None),
        include_skill_body=getattr(args, "include_skill_body", False),
        skills=skills_list,
    )


def _aggregate(results: list[dict]) -> dict:
    total = len(results)
    executed = sum(1 for r in results if r.get("status") == "executed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    skipped = total - executed - failed
    passed = 0
    task_failed = 0
    runtimes = []
    for r in results:
        payload = r.get("result") or {}
        status = payload.get("status")
        if status == "passed":
            passed += 1
        elif status == "failed":
            task_failed += 1
        runtime = payload.get("runtime_s")
        if isinstance(runtime, (int, float)):
            runtimes.append(runtime)

    avg_runtime = round(sum(runtimes) / len(runtimes), 3) if runtimes else None
    success_rate = round(passed / total, 3) if total else None
    return {
        "total": total,
        "executed": executed,
        "failed": failed,
        "skipped": skipped,
        "passed": passed,
        "task_failed": task_failed,
        "success_rate": success_rate,
        "avg_runtime_s": avg_runtime,
    }


def _run_mode(
    *,
    pack: TaskPack,
    mode: str,
    skill_path: Optional[pathlib.Path],
    extra_skills: list[pathlib.Path],
    image: str,
    agent_cmd: Optional[str],
    agent_model: Optional[str],
    runner: str,
    include_skill_body: bool,
) -> dict:
    results = []
    output_dir = REPO_ROOT / "reports" / "tasks" / mode
    for task in pack.tasks:
        if runner == "docker":
            results.append(
                docker_runner.run_task(
                    pack=pack,
                    task=task,
                    mode=mode,
                    skill_path=skill_path,
                    skills=extra_skills,
                    output_dir=output_dir,
                    image=image,
                    agent_cmd=agent_cmd,
                    agent_model=agent_model,
                    include_skill_body=include_skill_body,
                )
            )
        else:
            from harness.runners import local_runner

            results.append(
                local_runner.run_task(
                    pack=pack,
                    task=task,
                    mode=mode,
                    skill_path=skill_path,
                    skills=extra_skills,
                    output_dir=output_dir,
                    agent_cmd=agent_cmd,
                    agent_model=agent_model,
                    include_skill_body=include_skill_body,
                )
            )
    return {"aggregate": _aggregate(results), "tasks": results}


def _delta(baseline: dict, augmented: dict) -> dict:
    if not baseline or not augmented:
        return {}
    base = baseline.get("aggregate") or {}
    aug = augmented.get("aggregate") or {}
    def _diff(key: str):
        if base.get(key) is None or aug.get(key) is None:
            return None
        return round(aug[key] - base[key], 3)
    return {
        "success_rate": _diff("success_rate"),
        "avg_runtime_s": _diff("avg_runtime_s"),
        "passed": _diff("passed"),
        "task_failed": _diff("task_failed"),
    }


def _profile(baseline: dict, augmented: dict, robustness: Optional[dict] = None) -> dict:
    base = baseline.get("aggregate") or {}
    aug = augmented.get("aggregate") or {}
    def _val(key: str):
        return {"baseline": base.get(key), "augmented": aug.get(key), "delta": _delta(baseline, augmented).get(key)}

    def _legibility(section: dict) -> dict:
        tasks = section.get("tasks") or []
        failures = 0
        explicit = 0
        silent = 0
        for t in tasks:
            payload = t.get("result") or {}
            status = payload.get("status")
            if status and status != "passed":
                failures += 1
                has_signal = any(payload.get(k) for k in ("stderr", "agent_stderr", "error"))
                if has_signal:
                    explicit += 1
                else:
                    silent += 1
        explicit_rate = round(explicit / failures, 3) if failures else None
        silent_rate = round(silent / failures, 3) if failures else None
        return {"explicit_error_rate": explicit_rate, "silent_failure_rate": silent_rate}

    def _skill_count(section: dict) -> dict:
        tasks = section.get("tasks") or []
        counts = []
        for t in tasks:
            payload = t.get("result") or {}
            count = payload.get("skill_count")
            if isinstance(count, int):
                counts.append(count)
        avg = round(sum(counts) / len(counts), 3) if counts else None
        max_count = max(counts) if counts else None
        return {"avg_skill_count": avg, "max_skill_count": max_count}

    base_leg = _legibility(baseline)
    aug_leg = _legibility(augmented)
    base_comp = _skill_count(baseline)
    aug_comp = _skill_count(augmented)

    profile = {
        "reliability": {
            "success_rate": _val("success_rate"),
            "passed": _val("passed"),
            "task_failed": _val("task_failed"),
        },
        "efficiency": {
            "avg_runtime_s": _val("avg_runtime_s"),
        },
        "robustness": robustness or {},
        "composability": {
            "avg_skill_count": {
                "baseline": base_comp.get("avg_skill_count"),
                "augmented": aug_comp.get("avg_skill_count"),
                "delta": None if base_comp.get("avg_skill_count") is None or aug_comp.get("avg_skill_count") is None
                else round(aug_comp["avg_skill_count"] - base_comp["avg_skill_count"], 3),
            },
            "max_skill_count": {
                "baseline": base_comp.get("max_skill_count"),
                "augmented": aug_comp.get("max_skill_count"),
                "delta": None if base_comp.get("max_skill_count") is None or aug_comp.get("max_skill_count") is None
                else aug_comp["max_skill_count"] - base_comp["max_skill_count"],
            },
            "multi_skill": {
                "baseline": bool(base_comp.get("max_skill_count") and base_comp["max_skill_count"] > 1),
                "augmented": bool(aug_comp.get("max_skill_count") and aug_comp["max_skill_count"] > 1),
                "delta": None,
            },
        },
        "failure_legibility": {
            "explicit_error_rate": {
                "baseline": base_leg.get("explicit_error_rate"),
                "augmented": aug_leg.get("explicit_error_rate"),
                "delta": None if base_leg.get("explicit_error_rate") is None or aug_leg.get("explicit_error_rate") is None
                else round(aug_leg["explicit_error_rate"] - base_leg["explicit_error_rate"], 3),
            },
            "silent_failure_rate": {
                "baseline": base_leg.get("silent_failure_rate"),
                "augmented": aug_leg.get("silent_failure_rate"),
                "delta": None if base_leg.get("silent_failure_rate") is None or aug_leg.get("silent_failure_rate") is None
                else round(aug_leg["silent_failure_rate"] - base_leg["silent_failure_rate"], 3),
            },
        },
    }
    return profile


def _resolve_pack_path(pack_arg: str) -> pathlib.Path:
    candidate = pathlib.Path(pack_arg)
    if candidate.is_absolute() and candidate.exists():
        resolved = candidate.resolve()
        if REPO_ROOT in resolved.parents or resolved == REPO_ROOT:
            return resolved
        raise FileNotFoundError(f"Task pack must live under repo root: {pack_arg}")

    rel_candidate = REPO_ROOT / candidate
    if rel_candidate.exists():
        return rel_candidate.resolve()

    packs_candidate = REPO_ROOT / "packs" / pack_arg
    if packs_candidate.exists():
        return packs_candidate.resolve()

    raise FileNotFoundError(f"Task pack not found: {pack_arg}")


def _split_skill_paths(config: RunConfig) -> tuple[Optional[pathlib.Path], list[pathlib.Path]]:
    primary = config.skill_path
    extras = list(config.skills or [])
    if primary is None and extras:
        primary = extras[0]
        extras = extras[1:]
    return primary, extras


def run_benchmark(config: RunConfig) -> dict:
    pack_path = _resolve_pack_path(config.task_pack)
    pack = load_task_pack(pack_path)

    report = {
        "task_pack": f"{pack.name}@{pack.version}",
        "description": pack.description,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline": None,
        "augmented": None,
        "delta": None,
    }

    if config.mode in ("baseline", "both"):
        report["baseline"] = _run_mode(
            pack=pack,
            mode="baseline",
            skill_path=None,
            extra_skills=[],
            image=config.image,
            agent_cmd=config.agent_cmd,
            agent_model=config.agent_model,
            runner=config.runner,
            include_skill_body=False,
        )

    if config.mode in ("augmented", "both"):
        primary_skill, extra_skills = _split_skill_paths(config)
        if not primary_skill and not extra_skills:
            report["augmented"] = {
                "aggregate": {"total": len(pack.tasks), "executed": 0, "failed": 0, "skipped": len(pack.tasks)},
                "tasks": [],
                "warning": "No skill provided; augmented run skipped.",
            }
        else:
            report["augmented"] = _run_mode(
                pack=pack,
                mode="augmented",
                skill_path=primary_skill,
                extra_skills=extra_skills,
                image=config.image,
                agent_cmd=config.agent_cmd,
                agent_model=config.agent_model,
                runner=config.runner,
                include_skill_body=config.include_skill_body,
            )

        if report.get("baseline") and report.get("augmented"):
            report["delta"] = _delta(report["baseline"], report["augmented"])
            report["profile"] = _profile(report["baseline"], report["augmented"])
            if config.output:
                profile_path = config.output.parent / "profile.json"
                profile_path.write_text(json.dumps(report["profile"], indent=2), encoding="utf-8")

    return report


def main() -> None:
    command, args = parse_args()
    if command == "run":
        config = _resolve_run_config(args)
        result = run_benchmark(config)
        config.output.parent.mkdir(parents=True, exist_ok=True)
        with config.output.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote report to {config.output}")
        return

    if command == "infer":
        config = _resolve_run_config(args)
        pack_path = _resolve_pack_path(config.task_pack)
        pack = load_task_pack(pack_path)
        predictions_root = pathlib.Path(args.predictions).resolve()
        predictions_root.mkdir(parents=True, exist_ok=True)

        def _infer(mode: str, skill_path: Optional[pathlib.Path], extra_skills: list[pathlib.Path]) -> dict:
            results = []
            output_dir = predictions_root / mode
            for task in pack.tasks:
                if config.runner == "docker":
                    results.append(
                        docker_runner.infer_task(
                            pack=pack,
                            task=task,
                            mode=mode,
                            skill_path=skill_path,
                            skills=extra_skills,
                            output_dir=output_dir,
                            image=config.image,
                            agent_cmd=config.agent_cmd,
                            agent_model=config.agent_model,
                            include_skill_body=config.include_skill_body,
                        )
                    )
                else:
                    from harness.runners import local_runner

                    results.append(
                        local_runner.infer_task(
                            pack=pack,
                            task=task,
                            mode=mode,
                            skill_path=skill_path,
                            skills=extra_skills,
                            output_dir=output_dir,
                            agent_cmd=config.agent_cmd,
                            agent_model=config.agent_model,
                            include_skill_body=config.include_skill_body,
                        )
                    )
            return {"aggregate": _aggregate(results), "tasks": results}

        report = {
            "task_pack": f"{pack.name}@{pack.version}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "predictions_dir": str(predictions_root),
            "baseline": None,
            "augmented": None,
        }

        def _write_jsonl(mode: str, data: dict) -> None:
            jsonl_path = predictions_root / f"{mode}.jsonl"
            lines = []
            for item in data.get("tasks", []):
                entry = {
                    "task_id": item.get("task_id"),
                    "mode": mode,
                    "status": item.get("status"),
                    "patch_path": item.get("output"),
                    "meta": item.get("result"),
                }
                lines.append(json.dumps(entry))
            jsonl_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        primary_skill, extra_skills = _split_skill_paths(config)

        if config.mode in ("baseline", "both"):
            report["baseline"] = _infer("baseline", None, [])
            _write_jsonl("baseline", report["baseline"])
        if config.mode in ("augmented", "both"):
            if primary_skill or extra_skills:
                report["augmented"] = _infer("augmented", primary_skill, extra_skills)
                _write_jsonl("augmented", report["augmented"])
            else:
                report["augmented"] = {"warning": "No skill provided; augmented skipped."}

        summary_path = predictions_root / "summary.json"
        summary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote predictions to {predictions_root}")
        return

    if command == "eval":
        pack_path = _resolve_pack_path(args.pack)
        pack = load_task_pack(pack_path)
        predictions_root = pathlib.Path(args.predictions).resolve()
        mode = args.mode
        patch_dir = predictions_root / mode
        if not patch_dir.exists():
            raise SystemExit(f"Predictions not found: {patch_dir}")

        patch_map = {}
        if args.predictions_file:
            pred_file = pathlib.Path(args.predictions_file)
            if not pred_file.exists():
                raise SystemExit(f"Predictions file not found: {pred_file}")
            for line in pred_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                patch_map[str(entry.get("task_id"))] = entry.get("patch_path")

        output_dir = REPO_ROOT / "reports" / "tasks" / mode
        results = []
        for task in pack.tasks:
            patch_path = pathlib.Path(patch_map.get(task.id, patch_dir / f"{task.id}.diff"))
            if args.runner == "docker":
                results.append(
                    docker_runner.eval_task(
                        pack=pack,
                        task=task,
                        mode=mode,
                        patch_path=patch_path,
                        output_dir=output_dir,
                        image=args.image,
                    )
                )
            else:
                from harness.runners import local_runner

                results.append(
                    local_runner.eval_task(
                        pack=pack,
                        task=task,
                        mode=mode,
                        patch_path=patch_path,
                        output_dir=output_dir,
                    )
                )

        report = {
            "task_pack": f"{pack.name}@{pack.version}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "predictions_dir": str(predictions_root),
            "aggregate": _aggregate(results),
            "tasks": results,
        }
        output_path = pathlib.Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote report to {output_path}")
        return

    if command == "compare":
        baseline = json.loads(pathlib.Path(args.baseline).read_text(encoding="utf-8"))
        augmented = json.loads(pathlib.Path(args.augmented).read_text(encoding="utf-8"))
        delta = _delta(baseline, augmented)
        robustness = {}
        if args.robustness_dir:
            rdir = pathlib.Path(args.robustness_dir)
            for rb_path in sorted(rdir.glob("robust-*baseline*.json")):
                name = rb_path.stem.replace("robust-", "").replace("-baseline", "")
                ra_path = rdir / rb_path.name.replace("baseline", "augmented")
                if not ra_path.exists():
                    continue
                rb = json.loads(rb_path.read_text(encoding="utf-8"))
                ra = json.loads(ra_path.read_text(encoding="utf-8"))
                key = rb.get("perturbation", name)
                robustness[key] = {
                    "baseline": rb.get("success_rate"),
                    "augmented": ra.get("success_rate"),
                    "delta": None if rb.get("success_rate") is None or ra.get("success_rate") is None
                    else round(ra["success_rate"] - rb["success_rate"], 3),
                }
        elif args.robustness_baseline and args.robustness_augmented:
            rb = json.loads(pathlib.Path(args.robustness_baseline).read_text(encoding="utf-8"))
            ra = json.loads(pathlib.Path(args.robustness_augmented).read_text(encoding="utf-8"))
            key = rb.get("perturbation", "tool_failure")
            robustness = {
                key: {
                    "baseline": rb.get("success_rate"),
                    "augmented": ra.get("success_rate"),
                    "delta": None if rb.get("success_rate") is None or ra.get("success_rate") is None
                    else round(ra["success_rate"] - rb["success_rate"], 3),
                }
            }
        profile = _profile(baseline, augmented, robustness=robustness)
        out = pathlib.Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"delta": delta, "profile": profile}, indent=2), encoding="utf-8")
        if args.profile_output:
            profile_path = pathlib.Path(args.profile_output).resolve()
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        print(f"Wrote delta to {out}")
        return


if __name__ == "__main__":
    main()
