"""ZClawBench Subset — 18 个可无 Docker 运行的任务。

评分方式: NanoBotAgent 执行 + LLM Judge 评分 (0~1)。
数据来源: HuggingFace zai-org/ZClawBench。

依赖:
  - 推理框架: OpenClawPro (提供 NanoBotAgent)
  - 评分逻辑: clawevalkit.grading (提供 run_judge_eval)

Supports two execution modes:
  - use_docker=True:  Run NanoBotAgent inside Docker container
  - use_docker=False: Run NanoBotAgent directly on host
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ..utils.log import log
from ..utils.nanobot import import_nanobot_agent
from ..config import get_judge_config
from .base import BaseBenchmark

DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE_NANOBOT", "wildclawbench-nanobot:v3")
TMP_WORKSPACE = "/tmp/zclawbench_workspace"

# 18个可无Docker运行的任务子集（非Docker模式使用）
RUNNABLE_IDS_SUBSET = [
    "zcb_107", "zcb_108", "zcb_109", "zcb_110", "zcb_111",
    "zcb_112", "zcb_113", "zcb_114", "zcb_115", "zcb_116",
    "zcb_076", "zcb_078", "zcb_082", "zcb_083",
    "zcb_053", "zcb_055", "zcb_066", "zcb_088",
]

# 全部116个任务（Docker模式使用）
RUNNABLE_IDS_ALL = [f"zcb_{i:03d}" for i in range(1, 117)]

# 默认使用子集（向后兼容）
RUNNABLE_IDS = RUNNABLE_IDS_SUBSET


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
        "-v", f"{exec_path}:/tmp/zclawbench_workspace/exec:rw",
        "-v", f"{tmp_path}:/tmp/zclawbench_workspace/tmp:rw",
        "-v", f"{openclawpro_dir}:/root/OpenClawPro:rw",
    ]
    if os.path.exists(workspace_inner):
        volume_mounts.extend(["-v", f"{workspace_inner}:/tmp/zclawbench_workspace/workspace:rw"])

    docker_run_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--network", "host",
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
    # Determine API key env var based on provider
    provider = config.get("provider", "openrouter")
    if provider == "minimax":
        api_key_env = "MINIMAX_API_KEY"
    elif provider == "openrouter":
        api_key_env = "OPENROUTER_API_KEY"
    else:
        api_key_env = "OPENROUTER_API_KEY"

    return f"""
import sys
import json
import time
import os
from pathlib import Path

sys.path.insert(0, '/root/OpenClawPro')
from harness.agent.nanobot import NanoBotAgent

workspace = Path('/tmp/zclawbench_workspace/workspace')
session_id = 'eval_{model_key}_{task_id}'

# Get API key from environment variable
api_key = os.environ.get('{api_key_env}', '')

agent = NanoBotAgent(
    model='{config["model"]}',
    api_url='{config["api_url"]}',
    api_key=api_key,
    workspace=workspace,
    timeout=3600,
    disable_safety_guard=True,
)

system_prompt = \"\"\"You are an expert agent working in a restricted Docker environment.

Available tools:
- exec: Execute any shell command (bash, python3, curl, etc.)
- read_file / write_file / edit_file / list_dir: File operations
- web_search: Search the web (DuckDuckGo)
- web_fetch: Fetch and read web pages

IMPORTANT:
- You do NOT have access to Gmail API, Google Calendar API, or other cloud services.
- If a task requires email/calendar/search functionality, use the exec tool to simulate the workflow:
  - Create mock data files with realistic content, then process them.
  - Use web_search for real-time information gathering.
- Solve the task efficiently. Run all processes in the foreground without user input.
- Provide a complete, functional solution.\"\"\"

try:
    start_time = time.time()
    result = agent.execute(
        '''{user_message.replace("'", "\\'")}''',
        session_id=session_id,
        workspace=workspace,
        system_prompt=system_prompt,
        max_iterations=100,
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
    subprocess.run(["docker", "cp", f"{container_name}:/tmp/zclawbench_workspace/workspace/agent_result.json", str(result_file_host)],
                   capture_output=True)
    return result_file_host


# ============================================================================
# ZClawBench Benchmark
# ============================================================================

class ZClawBench(BaseBenchmark):
    DISPLAY_NAME = "ZClawBench"
    TASK_COUNT = 116  # 完整任务数（docker模式），非docker模式实际跑18个
    SCORE_RANGE = "0-1"

    def __init__(self, base_dir: Path = None, output_dir: Path = None, use_docker: bool = False):
        super().__init__(base_dir=base_dir, output_dir=output_dir)
        self._use_docker_default = use_docker

    @property
    def task_count(self) -> int:
        """根据模式返回任务数"""
        return 116 if self._use_docker_default else 18

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """运行 ZClawBench 评测: 加载 HF 数据 → NanoBotAgent 执行 → Judge 评分。

        Supports two execution modes:
          - use_docker=True: Run NanoBotAgent inside Docker container (116 tasks)
          - use_docker=False: Run NanoBotAgent directly on host (18 tasks)

        流程:
        1. 从 HuggingFace 加载 ZClawBench 数据集
        2. 对每个任务，使用 NanoBotAgent（来自 OpenClawPro）执行 agent 推理
        3. 使用 Judge Model 对执行轨迹进行评分
        4. 汇总所有任务的评分，返回平均分
        """
        use_docker = kwargs.get("use_docker", self._use_docker_default)
        parallel = kwargs.get("parallel", 1)
        openclawpro_dir = kwargs.get("openclawpro_dir")
        force = kwargs.get("force", False)
        task_ids = kwargs.get("task_ids")  # 指定特定任务

        if use_docker:
            return self._evaluate_docker(
                model_key=model_key,
                config=config,
                sample=sample,
                parallel=parallel,
                openclawpro_dir=openclawpro_dir,
                force=force,
                task_ids=task_ids,
            )
        else:
            return self._evaluate_native(
                model_key=model_key,
                config=config,
                sample=sample,
                force=force,
            )

    def _evaluate_native(self, model_key: str, config: dict, sample: int = 0, force: bool = False) -> dict:
        """Native mode: run NanoBotAgent directly on host (18 tasks)."""
        NanoBotAgent = import_nanobot_agent()
        from clawevalkit.grading import run_judge_eval

        tasks = self._load_tasks(use_docker=False)
        all_task_ids = [t["task_id"] for t in tasks]

        # 先基于已有缓存生成初始汇总（sample 前）
        self._build_and_save_summary(
            "zclawbench", model_key, all_task_ids,
            compute_summary_fn=lambda r: self._compute_summary(model_key, all_task_ids, r)
        )

        task_list = tasks
        if not force:
            # Pre-filter cached tasks
            uncached_tasks = []
            for task in task_list:
                tid = task["task_id"]
                result_file = self.results_dir / "zclawbench" / model_key / tid / "result.json"
                if not result_file.exists():
                    uncached_tasks.append(task)
                else:
                    try:
                        cached = json.loads(result_file.read_text())
                        if cached.get("status") != "success":
                            uncached_tasks.append(task)  # Incomplete
                    except Exception:
                        uncached_tasks.append(task)  # Corrupted
            log(f"[zclawbench] {len(task_list) - len(uncached_tasks)} tasks cached, {len(uncached_tasks)} remaining")
            task_list = uncached_tasks

        if sample and sample < len(task_list):
            random.seed(42)
            task_list = random.sample(task_list, sample)

        judge_key, judge_base, judge_model = get_judge_config(
            os.getenv("JUDGE_MODEL", "glm-4.7")
        )

        out_dir = self.results_dir / "zclawbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []

        for i, task in enumerate(task_list):
            tid = task["task_id"]
            log(f"[zclawbench] Running task {i+1}/{len(task_list)}: {tid}")

            workspace = Path(f"/tmp/eval_zclaw_{model_key}/{tid}")
            if workspace.exists():
                shutil.rmtree(workspace)
            workspace.mkdir(parents=True, exist_ok=True)

            r = {"task_id": tid, "model_key": model_key, "status": "error", "scores": {}}
            try:
                agent = NanoBotAgent(model=config["model"], api_url=config["api_url"],
                                     api_key=config["api_key"], workspace=workspace, timeout=3600)
                result = agent.execute(task["prompt"], session_id=f"eval_{model_key}_{tid}", workspace=workspace)
                if result.transcript:
                    normalized = [e["message"] if isinstance(e, dict) and "message" in e else e for e in result.transcript]
                    score = run_judge_eval(trajectory=normalized, task_id=tid, category=task["category"],
                                           task_prompt=task["prompt"], judge_model=judge_model,
                                           api_key=judge_key, base_url=judge_base, model_name=config["name"])
                    r["status"] = "success"
                    r["scores"] = {"overall_score": score.overall_score}
                    log(f"[{tid}] Judge score: {score.overall_score:.3f}")
            except Exception as e:
                r["error"] = str(e)[:300]
                log(f"[{tid}] Error: {r['error']}")

            # Save per-task result
            self._save_task_result("zclawbench", model_key, tid, r)
            shutil.rmtree(workspace, ignore_errors=True)
            results.append(r)

            # Update summary after each task
            self._build_and_save_summary(
                "zclawbench", model_key, all_task_ids,
                new_results=results,
                compute_summary_fn=lambda res: self._compute_summary(model_key, all_task_ids, res)
            )

        return self._load_summary("zclawbench", model_key)

    def _compute_summary(self, model_key: str, all_task_ids: list, results: list) -> dict:
        """Compute summary for ZClawBench."""
        scores = [r["scores"]["overall_score"] for r in results
                  if r.get("status") == "success" and r.get("scores")]
        avg = round(sum(scores) / len(scores), 3) if scores else 0
        total = len(all_task_ids)
        scored = len(results)
        return {
            "model": model_key,
            "score": avg,
            "passed": len(scores),
            "scored": scored,
            "pending": total - scored,
            "total": total,
            "details": results
        }

    def _load_summary(self, bench_key: str, model_key: str) -> dict:
        """Load saved summary file."""
        result_f = self.results_dir / bench_key / f"{model_key}.json"
        if result_f.exists():
            try:
                data = json.loads(result_f.read_text())
                return {"score": data["score"], "passed": data.get("passed", data.get("scored", 0)),
                        "total": data["total"]}
            except Exception:
                pass
        return {"score": 0, "passed": 0, "total": 0}

    def _evaluate_docker(
        self,
        model_key: str,
        config: dict,
        sample: int = 0,
        parallel: int = 1,
        openclawpro_dir: Path = None,
        force: bool = False,
        task_ids: list = None,
    ) -> dict:
        """Docker mode: run NanoBotAgent inside Docker container with Judge scoring."""
        if openclawpro_dir is None:
            openclawpro_dir = Path(os.getenv("OPENCLAWPRO_DIR",
                str(Path(__file__).parent.parent.parent / "OpenClawPro")))
        if not openclawpro_dir.exists():
            raise FileNotFoundError(f"OpenClawPro directory not found: {openclawpro_dir}")

        # Check if OpenClawPro is empty (submodule not initialized)
        if not any(openclawpro_dir.iterdir()):
            raise FileNotFoundError(
                f"OpenClawPro directory is empty. Please run:\n"
                f"  git submodule update --init --recursive\n"
                f"in the project root directory."
            )

        from clawevalkit.grading import run_judge_eval

        tasks = self._load_tasks(use_docker=True)  # Docker模式加载全部116个任务
        all_task_ids = [t["task_id"] for t in tasks]

        # Filter by specific task_ids if provided
        if task_ids:
            tasks = [t for t in tasks if t["task_id"] in task_ids]
            all_task_ids = [t["task_id"] for t in tasks]

        # 先基于已有缓存生成初始汇总（sample 前）
        self._build_and_save_summary(
            "zclawbench", model_key, all_task_ids,
            compute_summary_fn=lambda r: self._compute_summary(model_key, all_task_ids, r)
        )

        task_list = tasks
        if not force:
            # Pre-filter cached tasks
            uncached_tasks = []
            for task in task_list:
                tid = task["task_id"]
                result_file = self.results_dir / "zclawbench" / model_key / tid / "result.json"
                if not result_file.exists():
                    uncached_tasks.append(task)
                else:
                    try:
                        cached = json.loads(result_file.read_text())
                        if cached.get("status") != "success" or "scores" not in cached:
                            uncached_tasks.append(task)  # Incomplete
                    except Exception:
                        uncached_tasks.append(task)  # Corrupted
            log(f"[zclawbench] {len(task_list) - len(uncached_tasks)} tasks cached, {len(uncached_tasks)} remaining")
            task_list = uncached_tasks

        if sample and sample < len(task_list):
            random.seed(42)
            task_list = random.sample(task_list, sample)

        out_dir = self.results_dir / "zclawbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)

        judge_key, judge_base, judge_model = get_judge_config(
            os.getenv("JUDGE_MODEL", "glm-4.7")
        )

        def run_single_task_docker(task: dict, model: str, force: bool = False) -> dict:
            """Execute a single task inside Docker container with Judge scoring."""
            tid = task["task_id"]
            prompt = task["prompt"]
            category = task["category"]

            # Check cache
            task_output_dir = out_dir / tid
            task_output_dir.mkdir(parents=True, exist_ok=True)
            result_file = task_output_dir / "result.json"
            if not force and result_file.exists():
                try:
                    cached = json.loads(result_file.read_text())
                    if cached.get("status") == "success" and "scores" in cached:
                        log(f"[{tid}] Found cached result, skipping")
                        return {**cached, "_from_cache": True}
                except Exception:
                    pass

            # Generate container name
            timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
            short_model = re.sub(r"[^a-zA-Z0.\-_]", "_", model.rsplit("/", 1)[-1])
            container_name = f"zclaw_{tid}_{short_model}_{timestamp}"

            result = {
                "task_id": tid,
                "model_key": model_key,
                "status": "error",
                "scores": {},
                "error": None
            }

            try:
                # Prepare workspace on host
                workspace_path = tempfile.mkdtemp(prefix=f"zclawbench_docker_{tid}_")
                host_workspace = Path(workspace_path) / "workspace"
                host_workspace.mkdir(parents=True, exist_ok=True)

                # Build env args
                provider = config.get("provider", "openrouter")
                env_args = []

                # Pass correct API key based on provider
                if provider == "minimax":
                    minimax_api_key = os.getenv("MINIMAX_API_KEY", "")
                    env_args.extend(["-e", f"MINIMAX_API_KEY={minimax_api_key}"])
                else:
                    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
                    env_args.extend(["-e", f"OPENROUTER_API_KEY={openrouter_api_key}"])

                # Start container
                _start_container(container_name, workspace_path, openclawpro_dir, DOCKER_IMAGE, env_args)
                log(f"[{tid}] Container started")

                # Build and run agent
                exec_script = _build_exec_script(model_key, tid, prompt, config)
                exec_proc, elapsed_time = _run_agent_in_container(container_name, exec_script, 3600)
                log(f"[{tid}] Agent finished in {elapsed_time:.2f}s, returncode={exec_proc.returncode}")

                # Copy results back
                result_file_host = _copy_results_from_container(container_name, workspace_path, task_output_dir)

                # Load agent result
                transcript = []
                if result_file_host.exists():
                    try:
                        agent_result = json.loads(result_file_host.read_text())
                        result["status"] = agent_result.get("status", "error")
                        result["error"] = agent_result.get("error", "")
                        result["usage"] = {**agent_result.get("usage", {}), "elapsed_time": round(elapsed_time, 2)}
                        transcript = agent_result.get("transcript", [])
                        log(f"[{tid}] Agent result loaded: status={result['status']}, transcript_len={len(transcript)}")
                    except Exception as e:
                        log(f"[{tid}] Failed to load agent result: {e}")
                        result["error"] = f"Failed to load agent result: {e}"
                else:
                    log(f"[{tid}] agent_result.json not found at {result_file_host}")
                    result["error"] = "agent_result.json not found"

                # Run Judge scoring
                if transcript and result["status"] == "success":
                    try:
                        normalized = [e["message"] if isinstance(e, dict) and "message" in e else e for e in transcript]
                        score = run_judge_eval(
                            trajectory=normalized,
                            task_id=tid,
                            category=category,
                            task_prompt=prompt,
                            judge_model=judge_model,
                            api_key=judge_key,
                            base_url=judge_base,
                            model_name=config.get("name", model_key)
                        )
                        result["scores"] = {"overall_score": score.overall_score}
                        log(f"[{tid}] Judge score: {score.overall_score:.3f}")
                    except Exception as e:
                        log(f"[{tid}] Judge evaluation failed: {e}")
                        result["error"] = f"Judge evaluation failed: {e}"
                else:
                    result["scores"] = {"overall_score": 0.0}

            except subprocess.TimeoutExpired:
                result["error"] = "Timeout after 3600 seconds"
            except Exception as exc:
                log(f"[{tid}] Execution error: {exc}")
                result["error"] = str(exc)
            finally:
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
                shutil.rmtree(workspace_path, ignore_errors=True)

            # Save cache
            try:
                self._save_task_result("zclawbench", model_key, tid, result)
                log(f"[{tid}] Result saved to outputs/zclawbench/{model_key}/{tid}/result.json")
            except Exception as e:
                log(f"[{tid}] Failed to save result: {e}")

            return result

        # Execute tasks
        results = []
        if parallel <= 1:
            for i, task in enumerate(task_list):
                log(f"[zclawbench] Running task {i+1}/{len(task_list)}: {task['task_id']}")
                result = run_single_task_docker(task, config["model"], force=force)
                results.append(result)
                # Update summary after each task
                self._build_and_save_summary(
                    "zclawbench", model_key, all_task_ids,
                    new_results=results,
                    compute_summary_fn=lambda r: self._compute_summary(model_key, all_task_ids, r)
                )
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {
                    pool.submit(run_single_task_docker, task, config["model"], force): task["task_id"]
                    for task in task_list
                }
                for future in as_completed(futures):
                    tid = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        # Update summary after each task
                        self._build_and_save_summary(
                            "zclawbench", model_key, all_task_ids,
                            new_results=results,
                            compute_summary_fn=lambda r: self._compute_summary(model_key, all_task_ids, r)
                        )
                    except Exception as exc:
                        log(f"[{tid}] Thread exception: {exc}")
                        results.append({"task_id": tid, "scores": {}, "error": str(exc)})

        return self._load_summary("zclawbench", model_key)

    def collect(self, model_key: str) -> dict | None:
        result_dir = self._find_result_dir("zclawbench")
        if not result_dir:
            return None
        # Try model-level summary file first (aligned with SkillsBench)
        summary_file = result_dir / f"{model_key}.json"
        if summary_file.exists():
            try:
                data = json.loads(summary_file.read_text())
                # 未跑完时不返回缓存，让 inference 继续跑剩余任务
                if data.get("passed", 0) < data.get("total", 0):
                    return None
                return {"score": data["score"], "passed": data["passed"], "total": data["total"]}
            except Exception:
                pass
        # Fallback: scan task-level results (unified structure: {model_key}/{task_id}/result.json)
        out_dir = result_dir / model_key
        if not out_dir.exists():
            return None
        scores = []
        for task_dir in out_dir.iterdir():
            if task_dir.is_dir():
                result_file = task_dir / "result.json"
                if result_file.exists():
                    try:
                        r = json.loads(result_file.read_text())
                        if r.get("status") == "success":
                            scores.append(r["scores"]["overall_score"])
                    except Exception:
                        pass
        if not scores:
            return None
        # 动态检测任务数：如果结果数量 > 18，说明是docker模式跑的116个任务
        total_tasks = 116 if len(scores) > 18 else 18
        # 未跑完时不返回缓存，让 inference 继续跑剩余任务（逐任务缓存会自动跳过已完成的）
        if len(scores) < total_tasks:
            return None
        return {"score": round(sum(scores) / len(scores), 3), "passed": len(scores), "total": total_tasks}

    def _load_tasks(self, use_docker: bool = False):
        """加载 ZClawBench 数据集，解析出可运行任务的 prompt。

        优先从本地 benchmarks/zclawbench/zclawbench.jsonl 加载，
        如不存在则从 HuggingFace 下载。

        Args:
            use_docker: 如果为 True，加载全部 116 个任务；否则加载 18 个任务子集
        """
        # 根据模式选择任务列表
        runnable_ids = RUNNABLE_IDS_ALL if use_docker else RUNNABLE_IDS_SUBSET
        task_count = 116 if use_docker else 18

        local_data_path = self.base_dir / "benchmarks" / "zclawbench" / "zclawbench.jsonl"

        if local_data_path.exists():
            log(f"Loading ZClawBench from local: {local_data_path} (docker={use_docker}, tasks={task_count})")
            rows = []
            with open(local_data_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        else:
            log(f"Loading ZClawBench from HuggingFace: zai-org/ZClawBench (docker={use_docker}, tasks={task_count})")
            from datasets import load_dataset
            ds = load_dataset("zai-org/ZClawBench", split="train")
            rows = list(ds)

        task_map = {}
        for row in rows:
            tid = row["task_id"]
            if tid not in runnable_ids or tid in task_map:
                continue
            traj_str = row.get("trajectory", "[]")
            try:
                traj = json.loads(traj_str) if isinstance(traj_str, str) else traj_str
            except Exception:
                traj = []
            prompt = ""
            for msg in traj:
                if isinstance(msg, dict) and msg.get("role") == "user":
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                prompt = c.get("text", "")
                                break
                    elif isinstance(content, str):
                        prompt = content
                    break
            task_map[tid] = {"task_id": tid, "category": row.get("task_category", "unknown"), "prompt": prompt}
        return [task_map[t] for t in sorted(task_map)]
