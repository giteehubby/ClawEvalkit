"""AgentBench-OpenClaw — 40 tasks, L0 rules (60%) + L1 metrics (40%).

Scoring: NanoBotAgent execution in Docker → check output files → rule-based scoring (0~100).

Supports two execution modes:
  - use_docker=True:  Run NanoBotAgent inside Docker container (requires wildclawbench-nanobot image)
  - use_docker=False: Run nanobot CLI on host directly (default, requires nanobot installed)
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .base import BaseBenchmark

logger = logging.getLogger(__name__)

# Docker config
DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE_NANOBOT", "wildclawbench-nanobot:v3")
TMP_WORKSPACE = "/tmp_workspace"


# ============================================================================
# Docker Execution Helpers
# ============================================================================

def _start_container(container_name: str, workspace_path: str, openclawpro_dir: Path,
                     docker_image: str, env_args: list) -> None:
    """Start Docker container with selective volume mounts."""
    exec_path = os.path.join(workspace_path, "exec")
    tmp_path = os.path.join(workspace_path, "tmp")
    workspace_inner = os.path.join(workspace_path, "workspace")

    os.makedirs(exec_path, exist_ok=True)
    os.makedirs(tmp_path, exist_ok=True)

    volume_mounts = [
        "-v", f"{exec_path}:/tmp_workspace/exec:rw",
        "-v", f"{tmp_path}:/tmp_workspace/tmp:rw",
        "-v", f"{openclawpro_dir}:/root/OpenClawPro:rw",
    ]
    if os.path.exists(workspace_inner):
        volume_mounts.extend(["-v", f"{workspace_inner}:/tmp_workspace/workspace:rw"])

    docker_run_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        *volume_mounts,
        *env_args,
        docker_image,
        "/bin/bash", "-c", "tail -f /dev/null",
    ]
    r = subprocess.run(docker_run_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Container startup failed:\n{r.stderr}")


def _build_exec_script(model_key: str, task_id: str, user_message: str, config: dict) -> str:
    """Build NanoBotAgent execution script for running inside Docker container."""
    return f"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, '/root/OpenClawPro')
from harness.agent.nanobot import NanoBotAgent

workspace = Path('/tmp_workspace')
session_id = 'eval_{model_key}_{task_id}'

agent = NanoBotAgent(
    model='{config["model"]}',
    api_url='{config["api_url"]}',
    api_key='{config["api_key"]}',
    workspace=workspace,
    timeout=300,
    disable_safety_guard=True,
)

system_prompt = \"\"\"You are an expert agent working in a restricted environment.
Solve the task efficiently. Run all processes in the foreground without user input.
Provide a complete, functional solution.\"\"\"

try:
    start_time = time.time()
    result = agent.execute(
        '''{user_message.replace("'", "\\'")}''',
        session_id=session_id,
        workspace=workspace,
        system_prompt=system_prompt,
        max_iterations=100,
        max_output_tokens=8192,
    )
    elapsed = time.time() - start_time

    transcript_file = workspace / '.sessions' / f'{{session_id}}.json'
    transcript_data = json.loads(transcript_file.read_text()) if transcript_file.exists() else (result.transcript or [])

    output = {{
        'status': result.status,
        'content': result.content,
        'transcript': transcript_data,
        'usage': result.usage or {{}},
        'execution_time': elapsed,
        'error': result.error,
    }}
except Exception as e:
    output = {{
        'status': 'error',
        'content': '',
        'transcript': [],
        'usage': {{}},
        'execution_time': 0,
        'error': str(e),
    }}

(workspace / 'agent_result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
print('DONE')
"""


def _run_agent_in_container(container_name: str, exec_script: str, timeout_seconds: int) -> tuple[subprocess.CompletedProcess, float]:
    """Execute NanoBotAgent inside container, return (process_result, elapsed_time)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(exec_script)
        script_path = f.name
    try:
        subprocess.run(["docker", "cp", script_path, f"{container_name}:/tmp/exec_nanobot.py"], check=True)
    finally:
        Path(script_path).unlink(missing_ok=True)

    start_time = time.perf_counter()
    exec_proc = subprocess.run(
        ["docker", "exec", container_name, "python3", "/tmp/exec_nanobot.py"],
        capture_output=True, text=True, timeout=timeout_seconds + 60)
    elapsed = time.perf_counter() - start_time
    return exec_proc, elapsed


def _copy_results_from_container(container_name: str, workspace_path: str, task_output_dir: Path) -> Path:
    """Copy agent result from container to host. Returns result_file path."""
    result_file_host = task_output_dir / "agent_result.json"
    subprocess.run(["docker", "cp", f"{container_name}:/tmp_workspace/agent_result.json", str(result_file_host)],
                   capture_output=True)

    # Also copy workspace contents that may have been created by agent
    results_dir = Path(workspace_path) / "results"
    if subprocess.run(["docker", "cp", f"{container_name}:/tmp_workspace", str(results_dir.parent)],
                      capture_output=True).returncode != 0:
        # Fallback: copy individual files that might exist
        for pattern in ["*.json", "*.md", "*.txt", "*.csv", "*.py"]:
            subprocess.run(
                ["docker", "exec", container_name, "find", "/tmp_workspace", "-name", pattern, "-type", "f"],
                capture_output=True, text=True
            )

    return result_file_host


# ============================================================================
# AgentBench Benchmark
# ============================================================================

class AgentBench(BaseBenchmark):
    DISPLAY_NAME = "AgentBench"
    TASK_COUNT = 40
    SCORE_RANGE = "0-100"

    def __init__(self, base_dir: Path = None, output_dir: Path = None, use_docker: bool = False):
        super().__init__(base_dir=base_dir, output_dir=output_dir)
        self._use_docker_default = use_docker

    def evaluate(
        self,
        model_key: str,
        config: dict,
        sample: int = 0,
        use_docker: bool = None,
        parallel: int = 1,
        openclawpro_dir: Path = None,
        **kwargs,
    ) -> dict:
        """Run AgentBench evaluation.

        Args:
            model_key: Model identifier
            config: Model config (model, api_url, api_key, provider)
            sample: Number of tasks to sample (0=all)
            use_docker: Run inside Docker container (default: False)
            parallel: Parallel task execution (Docker mode only)
            openclawpro_dir: OpenClawPro source for volume mount
        """
        if use_docker is None:
            use_docker = self._use_docker_default
        force = kwargs.pop("force", False)

        if use_docker:
            return self._evaluate_docker(
                model_key=model_key,
                config=config,
                sample=sample,
                parallel=parallel,
                openclawpro_dir=openclawpro_dir,
                force=force,
            )
        else:
            return self._evaluate_native(
                model_key=model_key,
                config=config,
                sample=sample,
            )

    def _evaluate_native(self, model_key: str, config: dict, sample: int = 0) -> dict:
        """Native mode: run nanobot CLI on host."""
        import yaml

        tasks_dir = self.base_dir / "benchmarks" / "agentbench-openclaw" / "tasks"
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        tasks = self._load_tasks(tasks_dir)
        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

        out_dir = self.results_dir / "agentbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []

        for task in tasks:
            tid = task["task_id"]
            result_file = out_dir / f"{tid}.json"
            if result_file.exists():
                try:
                    ex = json.loads(result_file.read_text())
                    if ex.get("status") == "success":
                        results.append(ex); continue
                except Exception: pass

            cfg = yaml.safe_load(Path(task["yaml_path"]).read_text())
            workspace = Path(tempfile.mkdtemp(prefix=f"agentbench_{tid}_"))
            try:
                # Prepare input files
                task_dir = Path(task["yaml_path"]).parent
                for inp in cfg.get("input_files", []):
                    fname = inp["name"] if isinstance(inp, dict) else inp
                    src = task_dir / fname
                    if src.exists():
                        dst = workspace / fname
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)

                config_path = self._write_config(model_key, config, workspace)
                user_msg = cfg.get("user_message", "")
                cmd = ["nanobot", "agent", "-c", str(config_path), "-w", str(workspace),
                       "-s", f"eval_{model_key}_{tid}", "-m", user_msg]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(workspace))

                expected = cfg.get("expected_outputs", [])
                if expected:
                    passed = sum(1 for e in expected if e.get("pattern") and (workspace / e["pattern"]).exists())
                    l0 = (passed / len(expected)) * 100
                else:
                    l0 = 0
                r = {"task_id": tid, "model_key": model_key, "status": "success", "scores": {"l0_score": l0, "overall_score": l0}}
            except Exception as e:
                r = {"task_id": tid, "model_key": model_key, "status": "error", "error": str(e)[:300], "scores": {}}

            result_file.write_text(json.dumps(r, indent=2, ensure_ascii=False))
            shutil.rmtree(workspace, ignore_errors=True)
            results.append(r)

        scores = [r["scores"]["overall_score"] for r in results if r.get("status") == "success" and r.get("scores")]
        avg = round(sum(scores) / len(scores), 1) if scores else 0
        return {"score": avg, "passed": len(scores), "total": len(tasks), "details": results}

    def _evaluate_docker(
        self,
        model_key: str,
        config: dict,
        sample: int = 0,
        parallel: int = 1,
        openclawpro_dir: Path = None,
        force: bool = False,
    ) -> dict:
        """Docker mode: run NanoBotAgent inside Docker container."""
        import yaml

        if openclawpro_dir is None:
            openclawpro_dir = Path(os.getenv("OPENCLAWPRO_DIR",
                str(Path(__file__).parent.parent.parent / "OpenClawPro")))
        if not openclawpro_dir.exists():
            raise FileNotFoundError(f"OpenClawPro directory not found: {openclawpro_dir}")

        tasks_dir = self.base_dir / "benchmarks" / "agentbench-openclaw" / "tasks"
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        tasks = self._load_tasks(tasks_dir)
        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

        out_dir = self.results_dir / "agentbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")

        def run_single_task_docker(task: dict, model: str, force: bool = False) -> dict:
            """Execute a single task inside Docker container."""
            tid = task["task_id"]
            yaml_path = task["yaml_path"]

            # Check cache
            task_output_dir = out_dir / tid
            task_output_dir.mkdir(parents=True, exist_ok=True)
            result_file = task_output_dir / "result.json"
            if not force and result_file.exists():
                try:
                    cached = json.loads(result_file.read_text())
                    if cached.get("status") == "success":
                        logger.info("[%s] Found cached result, skipping", tid)
                        return {**cached, "_from_cache": True}
                except Exception: pass

            # Generate container name
            timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
            short_model = re.sub(r"[^a-zA-Z0-9.\-_]", "_", model.rsplit("/", 1)[-1])
            container_name = f"agent_{tid}_{short_model}_{timestamp}"

            result = {"task_id": tid, "model_key": model_key, "status": "error", "scores": {}, "error": None}

            try:
                # Prepare workspace on host
                workspace_path = tempfile.mkdtemp(prefix=f"agentbench_docker_{tid}_")
                tmp_workspace = Path(workspace_path) / "tmp_workspace"
                tmp_workspace.mkdir(parents=True, exist_ok=True)

                # Copy input files to workspace
                cfg = yaml.safe_load(Path(yaml_path).read_text())
                task_dir = Path(yaml_path).parent
                for inp in cfg.get("input_files", []):
                    fname = inp["name"] if isinstance(inp, dict) else inp
                    src = task_dir / fname
                    if src.exists():
                        dst = tmp_workspace / fname
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)

                # Write nanobot config to workspace
                config_path = tmp_workspace / ".nanobot_config.json"
                config_path.write_text(json.dumps({
                    "providers": {"custom": {
                        "apiKey": openrouter_api_key,
                        "apiBase": config.get("api_url", "https://openrouter.ai/api/v1")
                    }},
                    "agents": {"defaults": {
                        "model": config["model"],
                        "workspace": str(tmp_workspace),
                        "maxToolIterations": 25
                    }}
                }, indent=2))

                # Build env args
                proxy_http = os.environ.get('HTTP_PROXY_INNER', '')
                proxy_https = os.environ.get('HTTPS_PROXY_INNER', '')
                env_args = [
                    "-e", f"http_proxy={proxy_http}",
                    "-e", f"https_proxy={proxy_https}",
                    "-e", f"HTTPS_PROXY={proxy_https}",
                    "-e", f"OPENROUTER_API_KEY={openrouter_api_key}",
                ]

                # Start container
                _start_container(container_name, workspace_path, openclawpro_dir, DOCKER_IMAGE, env_args)
                logger.info("[%s] Container started", container_name)

                # Copy workspace to container
                subprocess.run(["docker", "exec", container_name, "mkdir", "-p", "/tmp_workspace"],
                             capture_output=True)
                subprocess.run(["docker", "cp", f"{tmp_workspace}/.", f"{container_name}:/tmp_workspace/"],
                             capture_output=True)

                # Build and run agent
                user_msg = cfg.get("user_message", "")
                exec_script = _build_exec_script(model_key, tid, user_msg, config)
                exec_proc, elapsed_time = _run_agent_in_container(container_name, exec_script, 300)
                logger.info("[%s] Agent finished in %.2fs", container_name, elapsed_time)

                # Copy results back
                result_file_host = _copy_results_from_container(container_name, workspace_path, task_output_dir)

                # Load agent result
                if result_file_host.exists():
                    agent_result = json.loads(result_file_host.read_text())
                    result["status"] = agent_result.get("status", "error")
                    result["error"] = agent_result.get("error", "")
                    result["usage"] = {**agent_result.get("usage", {}), "elapsed_time": round(elapsed_time, 2)}

                # Score based on expected outputs
                expected = cfg.get("expected_outputs", [])
                if expected:
                    passed = 0
                    for e in expected:
                        pattern = e.get("pattern", "")
                        if pattern:
                            # Check if file exists in container's workspace
                            check_proc = subprocess.run(
                                ["docker", "exec", container_name, "test", "-f", f"/tmp_workspace/{pattern}"],
                                capture_output=True)
                            if check_proc.returncode == 0:
                                passed += 1
                    l0 = (passed / len(expected)) * 100 if expected else 0
                else:
                    l0 = 0

                result["scores"] = {"l0_score": l0, "overall_score": l0}

            except subprocess.TimeoutExpired:
                result["error"] = "Timeout after 300 seconds"
            except Exception as exc:
                logger.error("[%s] Execution error: %s", container_name, exc)
                result["error"] = str(exc)
            finally:
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
                shutil.rmtree(workspace_path, ignore_errors=True)

            # Save cache
            if result.get("status") == "success":
                result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))

            return result

        # Execute tasks
        results = []
        if parallel <= 1:
            for task in tasks:
                results.append(run_single_task_docker(task, config["model"], force=force))
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {
                    pool.submit(run_single_task_docker, task, config["model"], force): task["task_id"]
                    for task in tasks
                }
                for future in as_completed(futures):
                    tid = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        logger.error("[%s] Thread exception: %s", tid, exc)
                        results.append({"task_id": tid, "scores": {}, "error": str(exc)})

        scores = [r["scores"]["overall_score"] for r in results if r.get("status") == "success" and r.get("scores")]
        avg = round(sum(scores) / len(scores), 1) if scores else 0
        return {"score": avg, "passed": len(scores), "total": len(tasks), "details": results}

    def collect(self, model_key: str) -> dict | None:
        result_dir = self._find_result_dir("agentbench")
        if not result_dir:
            return None

        for key_variant in [model_key, self._legacy_key(model_key)]:
            d = result_dir / key_variant
            if not d.exists():
                continue

            # Check for results.json first
            full = d / "results.json"
            if full.exists():
                try:
                    data = json.loads(full.read_text())
                    if "overall_score" in data:
                        return {"score": round(float(data["overall_score"]), 1), "total": 40}
                except Exception: pass

            # Collect per-task scores
            scores = []
            for f in d.glob("*.json"):
                if f.name == "results.json":
                    continue
                try:
                    r = json.loads(f.read_text())
                    if r.get("status") == "success" and r.get("scores", {}).get("overall_score") is not None:
                        scores.append(float(r["scores"]["overall_score"]))
                except Exception: pass

            if scores:
                return {"score": round(sum(scores) / len(scores), 1), "total": len(scores)}

        return None

    def _legacy_key(self, key):
        m = {"claude-sonnet": "claude-sonnet-4.6",
             "claude-opus": "claude-opus-4.6", "gemini-3.1-pro": "gemini-3-pro-preview-new"}
        return m.get(key, key)

    def _load_tasks(self, tasks_dir):
        import yaml
        tasks = []
        for cat_dir in sorted(tasks_dir.iterdir()):
            if not cat_dir.is_dir():
                continue
            for task_dir in sorted(cat_dir.iterdir()):
                yaml_f = task_dir / "task.yaml"
                if yaml_f.exists():
                    tasks.append({"task_id": task_dir.name, "category": cat_dir.name, "yaml_path": str(yaml_f)})
        return tasks

    def _write_config(self, model_key, config, workspace):
        ark_key = os.getenv("OPENROUTER_API_KEY", "")
        or_key = os.getenv("OPENROUTER_API_KEY", "")
        if config["provider"] == "openrouter":
            cfg = {"providers": {"openrouter": {"apiKey": or_key}},
                   "agents": {"defaults": {"model": config["model"], "workspace": str(workspace), "maxToolIterations": 25}}}
        elif config["provider"] == "ark":
            cfg = {"providers": {"custom": {"apiKey": ark_key, "apiBase": config["api_url"]}},
                   "agents": {"defaults": {"model": config["model"], "workspace": str(workspace), "maxToolIterations": 25}}}
        else:
            cfg = {"providers": {"custom": {"apiKey": config["api_key"], "apiBase": config["api_url"]}},
                   "agents": {"defaults": {"model": config["model"], "workspace": str(workspace), "maxToolIterations": 25}}}
        p = workspace / ".nanobot_config.json"
        p.write_text(json.dumps(cfg, indent=2))
        return p
