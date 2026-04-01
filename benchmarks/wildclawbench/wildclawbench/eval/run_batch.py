from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
import time
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.task_parser import parse_task_md
from utils.docker_utils import (
    remove_container,
    start_container,
    setup_workspace,
    setup_skills,
    inject_openclaw_models,
    inject_lobster_workspace,
    run_warmup,
    run_background,
    close_proc_log,
    collect_output_from_container,
    TMP_WORKSPACE,
)
from utils.grading import run_grading, format_scores, print_summary, print_global_summary, extract_usage_from_jsonl

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

GATEWAY_PORT     = int(os.environ.get("GATEWAY_PORT", "18789"))

ROOT_DIR         = Path(__file__).resolve().parent.parent
TASKS_DIR        = ROOT_DIR / os.environ.get("TASKS_SUBDIR",  "tasks")
OUTPUT_DIR       = ROOT_DIR / os.environ.get("OUTPUT_SUBDIR", "output")

DEFAULT_MODEL    = os.environ.get("DEFAULT_MODEL",    "openrouter/anthropic/claude-sonnet-4.6")
DEFAULT_PARALLEL = int(os.environ.get("DEFAULT_PARALLEL", "1"))

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODELS_API_KEY_PLACEHOLDER = "${MY_PROXY_API_KEY}"

ALL_CATEGORIES = [
    "01_Productivity_Flow",
    "02_Code_Intelligence",
    "03_Social_Interaction",
    "04_Search_Retrieval",
    "05_Creative_Synthesis",
    "06_Safety_Alignment",
]

def grade_the_task(task_id: str, workspace_path: str, output_dir: Path, task: dict, result: dict):
    gt_host = os.path.join(workspace_path, "gt")
    if os.path.isdir(gt_host):
        r_gt = subprocess.run(
            ["docker", "cp", gt_host, f"{task_id}:{TMP_WORKSPACE}/gt"],
            capture_output=True, text=True,
        )
        if r_gt.returncode != 0:
            logger.warning("[%s] gt directory copy failed: %s", task_id, r_gt.stderr)
        else:
            logger.info("[%s] gt directory copied to container %s/gt", task_id, TMP_WORKSPACE)

    if not result.get("error") and task.get("automated_checks"):
        try:
            scores = run_grading(
                task_id=task_id,
                automated_checks=task["automated_checks"],
                output_dir=output_dir,
            )
            result["scores"] = scores
            print(format_scores(task_id, scores))
            logger.info("[%s] Grading complete", task_id)
        except Exception as exc:
            logger.error("[%s] Grading failed: %s", task_id, exc)
            result["scores"] = {"error": str(exc)}
    elif not task.get("automated_checks"):
        logger.info("[%s] No Automated Checks, skipping grading", task_id)

    return result

def cal_cost(task_id: str, output_dir: Path, result: dict, elapsed_time: float):
    transcript_container = "/root/.openclaw/agents/main/sessions/chat.jsonl"
    transcript_host = output_dir / "chat.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    r_cp = subprocess.run(
        ["docker", "cp", f"{task_id}:{transcript_container}", str(transcript_host)],
        capture_output=True, text=True,
    )
    if r_cp.returncode == 0 and transcript_host.exists():
        usage = extract_usage_from_jsonl(transcript_host)
    else:
        logger.warning("[%s] Transcript copy failed: %s", task_id, r_cp.stderr.strip())
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
                    "cache_write_tokens": 0, "total_tokens": 0,
                    "cost_usd": 0.0, "request_count": 0}
    usage["elapsed_time"] = round(elapsed_time, 2)
    result["usage"] = usage
    if usage["request_count"] > 0:
        logger.info(
            "[%s] Token usage — input:%d output:%d cache_read:%d total:%d cost:$%.4f",
            task_id,
            usage["input_tokens"], usage["output_tokens"],
            usage["cache_read_tokens"], usage["total_tokens"],
            usage["cost_usd"],
        )
    usage_path = output_dir / "usage.json"
    usage_path.write_text(
        json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("[%s] Usage written to → %s", task_id, usage_path)
    return result

def collect_task_output(task_id: str, output_dir: Path) -> None:
    """Collect task output files from the container to output_dir/task_output/."""
    try:
        collect_output_from_container(task_id, output_dir)
    except Exception as exc:
        logger.warning("[%s] Failed to collect task output: %s", task_id, exc)


def set_model(task_id: str, model: str) -> None:
    r = subprocess.run(
        ["docker", "exec", task_id, "/bin/bash", "-c", f"openclaw models set '{model}'"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Model setup failed:\n{r.stderr}")
    logger.info("[%s] Model set: %s", task_id, model)


def load_models_config(models_config_path: Path) -> dict:
    raw_config = models_config_path.read_text(encoding="utf-8")
    proxy_api_key = os.environ.get("MY_PROXY_API_KEY")
    if MODELS_API_KEY_PLACEHOLDER in raw_config and not proxy_api_key:
        raise ValueError(
            "MY_PROXY_API_KEY must be set to a non-empty value when models config uses ${MY_PROXY_API_KEY}"
        )

    expanded_config = raw_config.replace(
        MODELS_API_KEY_PLACEHOLDER,
        proxy_api_key or "",
    )
    parsed_models_config = json.loads(expanded_config)
    if not isinstance(parsed_models_config, dict):
        raise ValueError(f"Models config must be a JSON object: {models_config_path}")
    return parsed_models_config


def run_single_task(task: dict, model: str, lobster: dict | None = None, thinking: str | None = None,
                    models_config: dict | None = None) -> dict:
    """
    Execute a single task, returning a {"task_id", "scores", "error"} dict.
    Thread-safe: each task has its own container name and log directory.

    lobster: optional dict with keys "name", "workspace", "env".
    """
    task_id_ori     = task["task_id"]
    workspace_path  = task["workspace_path"]
    prompt          = task["prompt"]
    timeout_seconds = task["timeout_seconds"]
    env             = task["env"]
    skills          = task["skills"]
    skills_path     = task["skills_path"]
    system_prompt = f"You are an expert in a restricted, non-interactive environment. Solve the task efficiently before the timeout ({timeout_seconds}s). Run all processes in the foreground without user input or background services. Provide a complete, functional solution in a single pass with no placeholders. \n"
    prompt = system_prompt + prompt

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    run_id = uuid.uuid4().hex[:6]
    _m = re.match(r"(\d+)_.*?(task_\d+)", task_id_ori)
    short_task_id = f"{_m.group(1)}_{_m.group(2)}" if _m else task_id_ori
    short_model = re.sub(r'[^a-zA-Z0-9.\-_]', '_', model.rsplit('/', 1)[-1])
    lobster_prefix = f"{lobster['name']}_" if lobster else ""
    suffix = f"{lobster_prefix}{short_model}_{timestamp}_{run_id}"
    task_id = f"{short_task_id}_{lobster_prefix}{short_model}_{timestamp}_{run_id}"

    output_dir = OUTPUT_DIR / task["category"] / f"{task_id_ori}" / f"{suffix}"
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {"task_id": task_id, "scores": {}, "error": None}

    gateway_proc = None
    agent_proc = None
    elapsed_time = float(timeout_seconds)

    try:
        exec_path = os.path.join(workspace_path, "exec")
        tmp_path = os.path.join(workspace_path, "tmp")
        os.makedirs(exec_path, exist_ok=True)
        start_container(task_id, exec_path, extra_env=task.get("env", ""),
                        tmp_path=tmp_path,
                        lobster_env=lobster.get("env") if lobster else None)
        if lobster:
            inject_lobster_workspace(task_id, lobster["workspace"])
        setup_workspace(task_id,thinking=thinking)
        setup_skills(task_id, skills, skills_path)
        run_warmup(task_id, task.get("warmup", ""))
        if models_config:
            inject_openclaw_models(task_id, models_config)
        set_model(task_id, model)

        if OPENROUTER_API_KEY:
            auth_profile_path = "/root/.openclaw/agents/main/agent/auth-profiles.json"
            inject_cmd = (
                f"python3 -c \""
                f"import json, pathlib; "
                f"p = pathlib.Path('{auth_profile_path}'); "
                f"d = json.loads(p.read_text()) if p.exists() else {{'version':1,'profiles':{{}}}}; "
                f"d.setdefault('profiles',{{}})['openrouter:default'] = "
                f"{{'type':'api_key','provider':'openrouter','key':'{OPENROUTER_API_KEY}'}}; "
                f"p.write_text(json.dumps(d, indent=2))\""
            )
            subprocess.run(
                ["docker", "exec", task_id, "/bin/bash", "-c", inject_cmd],
                capture_output=True, text=True,
            )
            logger.info("[%s] Injected OPENROUTER_API_KEY into auth-profiles.json", task_id)

        # Enable the image tool by configuring imageModel to use the same model
        subprocess.run(
            ["docker", "exec", task_id, "/bin/bash", "-c",
             f"openclaw config set agents.defaults.imageModel.primary '{model}'"],
            capture_output=True, text=True,
        )
        logger.info("[%s] imageModel set: %s", task_id, model)

        gateway_proc = run_background(
            task_id,
            bash_cmd=(
                f"export OPENROUTER_API_KEY='{OPENROUTER_API_KEY}' && "
                f"openclaw gateway --port {GATEWAY_PORT}"
            ),
            log_path=output_dir / "gateway.log",
        )
        logger.info("[%s] Waiting for gateway to be ready (2s)...", task_id)
        time.sleep(2)

        safe_prompt  = prompt.replace("'", "'\\''")
        
        start_time = time.perf_counter()
        agent_proc   = run_background(
            task_id,
            bash_cmd=f"openclaw agent --session-id chat --timeout {timeout_seconds} --message '{safe_prompt}'",
            log_path=output_dir / "agent.log",
        )

        logger.info("[%s] Waiting for agent to finish...", task_id)
        try:
            agent_proc.wait(timeout=timeout_seconds)
            elapsed_time = time.perf_counter() - start_time
            logger.info("[%s] Agent finished successfully, elapsed: %.2f seconds", task_id, elapsed_time)
        except subprocess.TimeoutExpired:
            logger.info("[%s] Agent timed out...", task_id)
            elapsed_time = timeout_seconds
            agent_proc.kill()
            agent_proc.wait()
        logger.info("[%s] Agent exit code: %s", task_id, agent_proc.returncode)

    except Exception as exc:
        logger.error("[%s] Execution error: %s", task_id, exc)
        elapsed_time = timeout_seconds
        result["error"] = str(exc)

    finally:
        result = grade_the_task(task_id, workspace_path, output_dir, task, result)
        result = cal_cost(task_id, output_dir, result, elapsed_time)

        try:
            collect_task_output(task_id, output_dir)
        except Exception as exc:
            logger.warning("[%s] Failed to collect task output: %s", task_id, exc)

        if gateway_proc is not None:
            try:
                gateway_proc.terminate()
            except Exception:
                pass
        else:
            logger.warning("[%s] Gateway not started, task incomplete — likely missing required result files, check %s", task_id, output_dir)

        for _proc in [gateway_proc, agent_proc]:
            if _proc is not None:
                try:
                    close_proc_log(_proc)
                except Exception:
                    pass

        remove_container(task_id)
        logger.info("[%s] Container cleaned up", task_id)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ClawBench evaluation entry point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single task
  python eval/run.py --task tasks/01_Productivity_Flow/task_23_arxiv_digest.md

  # Entire category (sequential)
  python eval/run.py --category 01_Productivity_Flow

  # Entire category (4 containers in parallel)
  python eval/run.py --category 01_Productivity_Flow --parallel 4

  # Specify model
  python eval/run.py --category 01_Productivity_Flow -m openrouter/google/gemini-2-5-pro
        """,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--task",     "-t", help="Path to a single task.md file")
    mode.add_argument("--category", "-c", help="Category name, e.g. 01_Productivity_Flow, 02_Code_Intelligence, 03_Social_Interaction, 04_Search_Retrieval, 05_Creative_Synthesis, 06_Safety_Alignment")

    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"Model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--parallel", "-p",
        type=int,
        default=DEFAULT_PARALLEL,
        metavar="N",
        help="Number of parallel containers (default: 1, i.e. sequential)",
    )
    parser.add_argument(
        "--lobster-name",
        default=None,
        help="Lobster name (used in output directory for comparison)",
    )
    parser.add_argument(
        "--lobster-workspace",
        default=None,
        help="Path to a personal OpenClaw workspace (contains SOUL.md, USER.md, etc.)",
    )
    parser.add_argument(
        "--lobster-env",
        default=None,
        help="Comma-separated env var names for skills that need API keys (e.g. GEMINI_API_KEY,FIRECRAWL_API_KEY)",
    )
    parser.add_argument(
        "--models-config",
        default=None,
        help="Path to a JSON file that will replace the top-level models field in ~/.openclaw/openclaw.json before each task",
    )
    parser.add_argument(
        "--thinking",
        default=None,
        help="Thinking/reasoning level for the model (default: high)",
    )

    args = parser.parse_args()
    models_config = None
    if args.models_config:
        models_config_path = Path(args.models_config).expanduser()
        if not models_config_path.is_file():
            logger.error("Models config not found: %s", models_config_path)
            sys.exit(1)
        try:
            models_config = load_models_config(models_config_path.resolve())
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("Invalid models config: %s", exc)
            sys.exit(1)

    lobster = None
    if args.lobster_workspace:
        if not args.lobster_name:
            logger.error("--lobster-workspace requires --lobster-name")
            sys.exit(1)
        workspace = Path(args.lobster_workspace).expanduser()
        if not workspace.is_dir():
            logger.error("Lobster workspace not found: %s", workspace)
            sys.exit(1)
        env_keys = [k.strip() for k in args.lobster_env.split(",") if k.strip()] if args.lobster_env else []
        lobster = {
            "name": args.lobster_name,
            "workspace": str(workspace.resolve()),
            "env": env_keys,
        }
        logger.info("Lobster mode: %s (workspace=%s, env_keys=%s)",
                     lobster["name"], lobster["workspace"], lobster["env"])

    if args.task:
        task_file = Path(args.task)
        if not task_file.exists():
            logger.error("File not found: %s", task_file)
            sys.exit(1)
        task = parse_task_md(task_file)
        logger.info("Single task mode: %s", task["task_id"])
        run_single_task(task, args.model, lobster=lobster, models_config=models_config,thinking=args.thinking)
        return
    if args.category.lower() == "all":
        categories = ALL_CATEGORIES
    else:
        categories = [args.category]

    all_results: list[dict] = []
    safe_model_name = re.sub(r'[^a-zA-Z0-9.\-_]', '_', args.model)

    for category in categories:
        category_dir = TASKS_DIR / category
        if not category_dir.exists():
            logger.error("Category directory not found: %s", category_dir)
            continue

        task_files = sorted(category_dir.glob("*task_*.md"))
        if not task_files:
            logger.error("No task_*.md files found in: %s", category_dir)
            continue

        logger.info("Category: %s, %d tasks, parallelism: %d",
                    category, len(task_files), args.parallel)

        tasks = []
        for tf in task_files:
            try:
                tasks.append(parse_task_md(tf))
            except Exception as exc:
                logger.error("Parse failed %s: %s", tf, exc)

        if not tasks:
            continue

        results: list[dict] = []
        if args.parallel <= 1:
            for task in tasks:
                results.append(run_single_task(task, args.model, lobster=lobster, models_config=models_config,thinking=args.thinking))
        else:
            with ThreadPoolExecutor(max_workers=args.parallel) as pool:
                futures = {
                    pool.submit(run_single_task, task, args.model, lobster, args.thinking,models_config): task["task_id"]
                    for task in tasks
                }
                for future in as_completed(futures):
                    tid = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        logger.error("[%s] Thread exception: %s", tid, exc)
                        results.append({"task_id": tid, "scores": {}, "error": str(exc)})

        summary_label = f"{lobster['name']}_{safe_model_name}" if lobster else safe_model_name
        print_summary(results, category, OUTPUT_DIR, summary_label)
        all_results.extend(results)

    if len(categories) > 1 and all_results:
        summary_label = f"{lobster['name']}_{safe_model_name}" if lobster else safe_model_name
        print_global_summary(all_results, OUTPUT_DIR, summary_label)

if __name__ == "__main__":
    main()