"""PinchBench — 23 个任务，NanoBotAgent 执行 + 内嵌规则评分。

评分方式: 解析 task markdown → NanoBotAgent 执行 → 内嵌 grade() 函数评分 (0~100)。
部分模型有官方已跑出的分数，直接使用。

任务格式: 每个 task 是一个 markdown 文件，包含:
  - YAML frontmatter (id, category, timeout)
  - ## Prompt (给 agent 的指令)
  - ## Automated Checks (内嵌 Python grade() 函数)

支持两种执行模式:
  - use_docker=True:  Run NanoBotAgent inside Docker container
  - use_docker=False: Run NanoBotAgent on host directly (默认)
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
from typing import Any

from ..utils.nanobot import import_nanobot_agent
from .base import BaseBenchmark

logger = logging.getLogger(__name__)

OFFICIAL_SCORES = {
    "claude-sonnet": 86.9,
    "claude-opus": 86.3,
    "gemini-2.5-pro": 61.4,
    "gpt-4o": 64.7,
}

# Docker 配置 - 使用 wildclawbench-nanobot 镜像（包含 OpenClawPro 和 NanoBotAgent）
DOCKER_IMAGE = os.environ.get("PINCHBENCH_DOCKER_IMAGE", "wildclawbench-nanobot:v3")
TMP_WORKSPACE = "/tmp/pinchbench_workspace"


class PinchBench(BaseBenchmark):
    DISPLAY_NAME = "PinchBench"
    TASK_COUNT = 23
    SCORE_RANGE = "0-100"

    def __init__(self, base_dir: Path = None, output_dir: Path = None, use_docker: bool = False):
        super().__init__(base_dir=base_dir, output_dir=output_dir)
        self._use_docker_default = use_docker

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """运行 PinchBench 评测: 解析任务 → NanoBotAgent 执行 → grade() 评分。

        流程:
        1. 若模型有官方分数，直接返回
        2. 解析 tasks/ 目录下的 markdown 文件，提取 prompt 和 grade 函数
        3. 对每个任务：创建隔离 workspace → NanoBotAgent 执行 → 调用 grade() 评分
        4. 汇总所有任务的平均分
        """
        if model_key in OFFICIAL_SCORES:
            return {"score": OFFICIAL_SCORES[model_key], "passed": 0, "total": 23, "source": "official"}

        use_docker = kwargs.get("use_docker", self._use_docker_default)
        parallel = kwargs.get("parallel", 1)

        if use_docker:
            return self._evaluate_docker(
                model_key=model_key,
                config=config,
                sample=sample,
                parallel=parallel,
                **kwargs
            )
        else:
            return self._evaluate_native(
                model_key=model_key,
                config=config,
                sample=sample,
                **kwargs
            )

    def _evaluate_native(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """Native mode: run NanoBotAgent on host directly."""
        NanoBotAgent = import_nanobot_agent()
        tasks = self._load_tasks()
        if not tasks:
            return {"score": 0, "total": 0, "error": "no tasks found"}

        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

        out_dir = self.results_dir / "pinchbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []

        for task in tasks:
            tid = task["id"]
            result_file = out_dir / f"{tid}.json"

            # 跳过已完成的任务
            if result_file.exists():
                try:
                    ex = json.loads(result_file.read_text())
                    if ex.get("status") == "success":
                        results.append(ex)
                        continue
                except Exception:
                    pass

            workspace = Path(f"/tmp/eval_pinch_{model_key}/{tid}")
            if workspace.exists():
                shutil.rmtree(workspace)
            workspace.mkdir(parents=True, exist_ok=True)

            r = {"task_id": tid, "model_key": model_key, "status": "error", "scores": {}, "mean": 0.0}

            try:
                agent = NanoBotAgent(
                    model=config["model"], api_url=config["api_url"],
                    api_key=config["api_key"], workspace=workspace,
                    timeout=task.get("timeout", 120),
                )
                result = agent.execute(
                    task["prompt"],
                    session_id=f"pinch_{model_key}_{tid}",
                )
                transcript = result.transcript if result.transcript else []

                # 执行内嵌的 grade() 函数
                if task.get("grade_code"):
                    scores = self._run_grade(task["grade_code"], transcript, str(workspace))
                    mean_score = sum(scores.values()) / len(scores) if scores else 0
                    r["status"] = "success"
                    r["scores"] = scores
                    r["mean"] = round(mean_score, 4)
                else:
                    # 无 grade 函数时，检查 agent 是否成功执行
                    r["status"] = "success" if result.status == "success" else "error"
                    r["mean"] = 1.0 if result.status == "success" else 0.0

            except Exception as e:
                r["error"] = str(e)[:300]

            result_file.write_text(json.dumps(r, indent=2, ensure_ascii=False))
            shutil.rmtree(workspace, ignore_errors=True)
            results.append(r)

        # 汇总：所有任务的平均分 × 100
        means = [r["mean"] for r in results if r.get("status") == "success"]
        overall = round(sum(means) / len(means) * 100, 1) if means else 0
        final = {"score": overall, "passed": len(means), "total": len(tasks), "details": results}
        self.save_result("pinchbench", model_key, final, "result.json")
        return final

    def _save_transcript(self, model_key: str, task_id: str, transcript: list):
        """保存 agent 轨迹到文件。

        保存到: outputs/pinchbench/transcripts/{model}/{task}/transcript.json
        """
        try:
            trans_path = self.results_dir / "pinchbench" / "transcripts" / model_key / task_id
            trans_path.mkdir(parents=True, exist_ok=True)
            (trans_path / "transcript.json").write_text(
                json.dumps(transcript, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("[%s] Saved transcript to %s", task_id, trans_path / "transcript.json")
        except Exception:
            pass  # transcript 保存失败不影响主流程

    def _evaluate_docker(
        self,
        model_key: str,
        config: dict,
        sample: int = 0,
        parallel: int = 1,
        **kwargs
    ) -> dict:
        """Docker mode: run NanoBotAgent inside Docker container."""
        tasks = self._load_tasks()
        if not tasks:
            return {"score": 0, "total": 0, "error": "no tasks found"}

        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

        out_dir = self.results_dir / "pinchbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)
        transcripts_dir = kwargs.get("transcripts_dir")

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        openclawpro_dir = kwargs.get("openclawpro_dir") or Path(
            os.getenv("OPENCLAWPRO_DIR", str(self.base_dir / "OpenClawPro"))
        )

        def run_single_task_docker(task: dict) -> dict:
            """Execute a single task inside Docker container."""
            tid = task["id"]
            result_file = out_dir / f"{tid}.json"

            # Check cache
            if result_file.exists():
                try:
                    cached = json.loads(result_file.read_text())
                    if cached.get("status") == "success":
                        logger.info("[%s] Found cached result, skipping", tid)
                        return cached
                except Exception:
                    pass

            # Generate container name
            timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
            short_model = re.sub(r"[^a-zA-Z0-9.\-_]", "_", config["model"].rsplit("/", 1)[-1])
            container_name = f"pinch_{tid}_{short_model}_{timestamp}"

            result = {
                "task_id": tid,
                "model_key": model_key,
                "status": "error",
                "scores": {},
                "mean": 0.0,
                "error": None
            }

            workspace_path = None

            try:
                # Prepare workspace on host
                workspace_path = tempfile.mkdtemp(prefix=f"pinchbench_docker_{tid}_")
                host_workspace = Path(workspace_path) / "workspace"
                host_workspace.mkdir(parents=True, exist_ok=True)

                # Copy workspace files if specified in task
                self._prepare_workspace_files(task, host_workspace)

                # Build env args
                proxy_http = os.environ.get('HTTP_PROXY', '')
                proxy_https = os.environ.get('HTTPS_PROXY', '')
                env_args = [
                    "-e", f"http_proxy={proxy_http}",
                    "-e", f"https_proxy={proxy_https}",
                    "-e", f"HTTP_PROXY={proxy_http}",
                    "-e", f"HTTPS_PROXY={proxy_https}",
                ]

                # Pass correct API key based on provider
                provider = config.get("provider", "openrouter")
                if provider == "minimax":
                    minimax_api_key = os.getenv("MINIMAX_API_KEY", "")
                    env_args.extend(["-e", f"MINIMAX_API_KEY={minimax_api_key}"])
                else:
                    env_args.extend(["-e", f"OPENROUTER_API_KEY={openrouter_api_key}"])

                # Start container
                self._start_container(container_name, workspace_path, openclawpro_dir, env_args)
                logger.info("[%s] Container started", container_name)

                # Build and run agent
                exec_script = self._build_exec_script(model_key, tid, task["prompt"], config, task.get("timeout", 120))
                exec_proc, elapsed_time = self._run_agent_in_container(container_name, exec_script, task.get("timeout", 120))
                logger.info("[%s] Agent finished in %.2fs, returncode=%d", container_name, elapsed_time, exec_proc.returncode)

                # Copy results back
                transcript = []
                try:
                    result_json = self._copy_result_from_container(container_name, workspace_path)
                    if result_json.exists():
                        agent_result = json.loads(result_json.read_text())
                        result["status"] = agent_result.get("status", "error")
                        result["error"] = agent_result.get("error", "")
                        transcript = agent_result.get("transcript", [])
                        logger.info("[%s] Agent result loaded: status=%s, transcript_len=%d",
                                   container_name, result["status"], len(transcript))
                except Exception as e:
                    logger.error("[%s] Failed to load agent result: %s", container_name, e)

                # Run grading
                if task.get("grade_code"):
                    scores = self._run_grade_in_container(container_name, task["grade_code"], transcript)
                    mean_score = sum(scores.values()) / len(scores) if scores else 0
                    result["scores"] = scores
                    result["mean"] = round(mean_score, 4)
                else:
                    result["mean"] = 1.0 if result["status"] == "success" else 0.0

            except subprocess.TimeoutExpired:
                result["error"] = f"Timeout after {task.get('timeout', 120)} seconds"
            except Exception as exc:
                logger.error("[%s] Execution error: %s", container_name if 'container_name' in dir() else tid, exc)
                result["error"] = str(exc)
            finally:
                # Cleanup
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
                if workspace_path:
                    shutil.rmtree(workspace_path, ignore_errors=True)

            # Save transcript
            if transcripts_dir and transcript:
                self._save_transcript(model_key, tid, transcript)

            # Save result
            try:
                result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            except Exception as e:
                logger.error("[%s] Failed to save result: %s", tid, e)

            return result

        # Execute tasks
        results = []
        if parallel <= 1:
            for task in tasks:
                results.append(run_single_task_docker(task))
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {pool.submit(run_single_task_docker, task): task["id"] for task in tasks}
                for future in futures:
                    tid = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        logger.error("[%s] Thread exception: %s", tid, exc)
                        results.append({"task_id": tid, "status": "error", "error": str(exc)})

        # 汇总：所有任务的平均分 × 100
        means = [r["mean"] for r in results if r.get("status") == "success"]
        overall = round(sum(means) / len(means) * 100, 1) if means else 0
        final = {"score": overall, "passed": len(means), "total": len(tasks), "details": results}
        self.save_result("pinchbench", model_key, final, "result.json")
        return final

    def _start_container(
        self,
        container_name: str,
        workspace_path: str,
        openclawpro_dir: Path,
        env_args: list
    ) -> None:
        """Start Docker container with volume mounts."""
        workspace_inner = os.path.join(workspace_path, "workspace")

        volume_mounts = [
            "-v", f"{workspace_inner}:{TMP_WORKSPACE}:rw",
        ]

        # Mount OpenClawPro if available
        if openclawpro_dir and openclawpro_dir.exists():
            volume_mounts.extend(["-v", f"{openclawpro_dir}:/root/OpenClawPro:rw"])

        docker_run_cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            *volume_mounts,
            *env_args,
            DOCKER_IMAGE,
            "/bin/bash", "-c", "tail -f /dev/null",
        ]
        r = subprocess.run(docker_run_cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Container startup failed:\n{r.stderr}")

    def _build_exec_script(self, model_key: str, task_id: str, prompt: str, config: dict, timeout: int) -> str:
        """Build NanoBotAgent execution script for running inside Docker container."""
        # Determine API key env var based on provider
        provider = config.get("provider", "openrouter")
        if provider == "minimax":
            api_key_env = "MINIMAX_API_KEY"
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

workspace = Path('{TMP_WORKSPACE}')
session_id = 'pinch_{model_key}_{task_id}'

api_key = os.environ.get('{api_key_env}', '')

agent = NanoBotAgent(
    model='{config["model"]}',
    api_url='{config["api_url"]}',
    api_key=api_key,
    workspace=workspace,
    timeout={timeout},
    disable_safety_guard=True,
)

system_prompt = \"\"\"You are an expert agent working in a restricted environment.\nSolve the task efficiently. Run all processes in the foreground without user input.\nProvide a complete, functional solution.\"\"\"

try:
    start_time = time.time()
    result = agent.execute(
        '''{prompt.replace("'", "\\'")}''',
        session_id=session_id,
        workspace=workspace,
        system_prompt=system_prompt,
        max_iterations=100,
        max_output_tokens=8192,
    )
    elapsed = time.time() - start_time

    # Use result.transcript directly - it contains the properly formatted transcript
    # with "type" and "message" structure that grading functions expect
    transcript_data = result.transcript or []

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

    def _run_agent_in_container(self, container_name: str, exec_script: str, timeout: int) -> tuple:
        """Execute NanoBotAgent inside container, return (process_result, elapsed_time)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(exec_script)
            script_path = f.name

        try:
            subprocess.run(
                ["docker", "cp", script_path, f"{container_name}:/tmp/exec_nanobot.py"],
                check=True, capture_output=True
            )
        finally:
            Path(script_path).unlink(missing_ok=True)

        start_time = time.perf_counter()
        exec_proc = subprocess.run(
            ["docker", "exec", container_name, "python3", "/tmp/exec_nanobot.py"],
            capture_output=True, text=True, timeout=timeout + 60
        )
        elapsed = time.perf_counter() - start_time
        return exec_proc, elapsed

    def _copy_result_from_container(self, container_name: str, workspace_path: str) -> Path:
        """Copy agent result from container to host."""
        result_file_host = Path(workspace_path) / "agent_result.json"
        subprocess.run(
            ["docker", "cp", f"{container_name}:{TMP_WORKSPACE}/agent_result.json", str(result_file_host)],
            capture_output=True
        )
        return result_file_host

    def _run_grade_in_container(self, container_name: str, grade_code: str, transcript: list) -> dict:
        """Run grade function inside container and return scores."""
        # Write transcript to temp file and copy to container
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(transcript, f)
            transcript_path = f.name

        # Create grade script
        grade_script = f"""
import json
import os
import sys

TMP_WORKSPACE = "{TMP_WORKSPACE}"

{grade_code}

# Load transcript from file
transcript_path = os.path.join(TMP_WORKSPACE, 'transcript.json')
with open(transcript_path) as f:
    transcript = json.load(f)

# Run grading
scores = grade(transcript, TMP_WORKSPACE)
print(json.dumps(scores))
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(grade_script)
            script_path = f.name

        try:
            # Copy transcript to container
            subprocess.run(
                ["docker", "cp", transcript_path, f"{container_name}:{TMP_WORKSPACE}/transcript.json"],
                check=True, capture_output=True
            )

            # Copy script to container
            subprocess.run(
                ["docker", "cp", script_path, f"{container_name}:/tmp/grade_script.py"],
                check=True, capture_output=True
            )

            # Run grading
            result = subprocess.run(
                ["docker", "exec", container_name, "python3", "/tmp/grade_script.py"],
                capture_output=True, text=True, timeout=60
            )

            if result.returncode == 0:
                return json.loads(result.stdout.strip().split('\n')[-1])
        except Exception as e:
            logger.warning("Grading in container failed: %s", e)
        finally:
            Path(script_path).unlink(missing_ok=True)
            Path(transcript_path).unlink(missing_ok=True)

        return {}

    def _prepare_workspace_files(self, task: dict, host_workspace: Path) -> None:
        """Copy workspace files to host workspace if specified in task."""
        # PinchBench tasks may have workspace_files in frontmatter
        workspace_files = task.get("workspace_files", [])
        if not workspace_files:
            return

        tasks_dir = self.base_dir / "benchmarks" / "pinchbench" / "tasks"
        assets_dir = self.base_dir / "benchmarks" / "pinchbench" / "assets"

        for file_spec in workspace_files:
            if isinstance(file_spec, dict):
                if "content" in file_spec:
                    # Write content directly
                    dest = host_workspace / file_spec["path"]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(file_spec["content"])
                elif "source" in file_spec:
                    # Copy from assets
                    source = assets_dir / file_spec["source"]
                    dest = host_workspace / file_spec.get("dest", file_spec["source"])
                    if source.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)

    # 旧目录名 → 新 model key 映射
    LEGACY_KEYS = {
        "gemini-3.1-pro": "gemini-3-pro-preview-new",
    }

    def collect(self, model_key: str) -> dict | None:
        if model_key in OFFICIAL_SCORES:
            return {"score": OFFICIAL_SCORES[model_key], "total": 23, "source": "official"}
        result_dir = self._find_result_dir("pinchbench")
        if not result_dir:
            return None
        for key in [model_key, self.LEGACY_KEYS.get(model_key, "")]:
            if not key:
                continue
            result_f = result_dir / key / "result.json"
            if result_f.exists():
                try:
                    data = json.loads(result_f.read_text())
                    score = data.get("score")
                    if score is not None:
                        return {"score": score, "total": 23}
                except Exception:
                    pass
        return None

    def _load_tasks(self) -> list:
        """解析 tasks/*.md → [{"id", "prompt", "grade_code", "timeout", "workspace_files"}, ...]

        每个 task markdown 结构:
        - YAML frontmatter（--- ... ---）: id, timeout_seconds, workspace_files 等
        - ## Prompt 部分: 给 agent 的指令
        - ## Automated Checks 中的 ```python ... ```: grade() 函数代码
        """
        import yaml
        tasks_dir = self.base_dir / "benchmarks" / "pinchbench" / "tasks"
        if not tasks_dir.exists():
            return []

        tasks = []
        for md in sorted(tasks_dir.glob("*.md")):
            # Skip template files
            if md.name.startswith("TASK_TEMPLATE") or md.name.startswith("_"):
                continue
            content = md.read_text(encoding="utf-8")

            # 解析 YAML frontmatter
            frontmatter = {}
            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                try:
                    frontmatter = yaml.safe_load(fm_match.group(1))
                except Exception:
                    pass

            # 提取 ## Prompt 部分
            prompt = ""
            prompt_match = re.search(
                r"## Prompt\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
            )
            if prompt_match:
                prompt = prompt_match.group(1).strip()

            # 提取 ## Automated Checks 中的 Python 代码
            grade_code = ""
            checks_match = re.search(
                r"## Automated Checks.*?```python\s*\n(.*?)```", content, re.DOTALL
            )
            if checks_match:
                grade_code = checks_match.group(1).strip()

            tid = frontmatter.get("id", md.stem)
            timeout = int(frontmatter.get("timeout_seconds", 120))
            workspace_files = frontmatter.get("workspace_files", [])

            tasks.append({
                "id": tid,
                "prompt": prompt,
                "grade_code": grade_code,
                "timeout": timeout,
                "workspace_files": workspace_files,
            })

        return tasks

    def _run_grade(self, grade_code: str, transcript: list, workspace_path: str) -> dict:
        """执行内嵌的 grade(transcript, workspace_path) 函数，返回评分字典。

        grade_code 是从 task markdown 的 ```python 块中提取的代码，
        定义了一个 grade(transcript, workspace_path) → dict 函数。
        """
        namespace = {}
        try:
            exec(grade_code, namespace)
            if "grade" in namespace:
                return namespace["grade"](transcript, workspace_path)
        except Exception:
            pass
        return {}
