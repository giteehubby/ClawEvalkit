"""Docker 容器运行器，封装常用操作"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .retry import with_retry

logger = logging.getLogger(__name__)


class DockerRunner:
    """Docker 容器运行器，封装常用操作，支持上下文管理器"""

    WORK_DIR = "/tmp_workspace"

    def __init__(self, image: str, openclawpro_dir: Path):
        self.image = image
        self.openclawpro_dir = openclawpro_dir
        self.container_name: Optional[str] = None

    def _generate_container_name(self, task_id: str, model: str) -> str:
        """生成唯一的容器名"""
        return task_id

    def start(
        self,
        workspace_path: str,
        task_id: str,
        model: str,
        env_vars: dict = None,
        extra_env: list = None,
    ) -> str:
        """启动容器

        Args:
            workspace_path: 任务工作空间路径
            task_id: 任务 ID
            model: 模型名称
            env_vars: 环境变量字典
            extra_env: 额外的环境变量列表 (格式: ["KEY=VALUE", ...])

        Returns:
            容器名称
        """
        self.container_name = self._generate_container_name(task_id, model)

        # 准备目录
        exec_path = os.path.join(workspace_path, "exec")
        tmp_path = os.path.join(workspace_path, "tmp")
        results_path = os.path.join(workspace_path, "results")
        skills_path = os.path.join(workspace_path, "skills")
        workspace_inner = os.path.join(workspace_path, "workspace")
        gt_dir = os.path.join(workspace_path, "gt")

        for p in [exec_path, tmp_path, results_path]:
            os.makedirs(p, exist_ok=True)

        # Volume mounts
        mounts = [
            "-v", f"{exec_path}:{self.WORK_DIR}/exec:rw",
            "-v", f"{tmp_path}:{self.WORK_DIR}/tmp:rw",
            "-v", f"{results_path}:{self.WORK_DIR}/results:rw",
            "-v", f"{self.openclawpro_dir}:/root/OpenClawPro:rw",
        ]
        if os.path.exists(skills_path):
            mounts.extend(["-v", f"{skills_path}:{self.WORK_DIR}/skills:rw"])
        if os.path.exists(workspace_inner):
            mounts.extend(["-v", f"{workspace_inner}:{self.WORK_DIR}/workspace:rw"])
        # Ground truth mounted readonly for grading only
        mounts.extend(["-v", f"{gt_dir}:{self.WORK_DIR}/gt:ro"])

        # Environment args from dict
        env_args = []
        for k, v in (env_vars or {}).items():
            env_args.extend(["-e", f"{k}={v}"])

        # Extra env args (already formatted as ["KEY=VALUE", ...])
        for kv in (extra_env or []):
            env_args.extend(["-e", kv])

        cmd = [
            "docker", "run", "-d",
            "--name", self.container_name,
            "--network=host",
            "--entrypoint", "/bin/bash",
            *mounts,
            *env_args,
            self.image,
            "-c", "tail -f /dev/null",
        ]

        # Retry logic for container startup
        max_retries = 3
        for attempt in range(max_retries):
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=60)
                if r.returncode == 0:
                    logger.info("[%s] ✅ Container created successfully", self.container_name)
                    logger.info("[%s]    - Image: %s", self.container_name, self.image)
                    logger.info("[%s]    - Workspace: %s", self.container_name, workspace_path)
                    logger.info("[%s]    - Model: %s", self.container_name, model)
                    logger.info("[%s]    - OpenClawPro: %s", self.container_name, self.openclawpro_dir)
                    return self.container_name
                logger.warning(
                    "[%s] Container startup failed (attempt %d): %s",
                    self.container_name, attempt + 1, r.stderr.decode()[:500]
                )
            except subprocess.TimeoutExpired:
                logger.warning("[%s] Container startup timeout (attempt %d)", self.container_name, attempt + 1)

            if attempt < max_retries - 1:
                subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True)
                time.sleep(2 ** attempt)

        raise RuntimeError(f"Container startup failed after {max_retries} attempts")

    @with_retry(max_retries=3, base_delay=1.0)
    def exec(self, cmd: list, timeout: int = 30) -> subprocess.CompletedProcess:
        """在容器内执行命令"""
        return subprocess.run(
            ["docker", "exec", self.container_name] + cmd,
            capture_output=True, text=True, timeout=timeout
        )

    @with_retry(max_retries=3, base_delay=1.0)
    def copy_to(self, src: str, dst: str) -> bool:
        """复制文件到容器"""
        result = subprocess.run(
            ["docker", "cp", src, f"{self.container_name}:{dst}"],
            capture_output=True, timeout=30
        )
        return result.returncode == 0

    @with_retry(max_retries=3, base_delay=1.0)
    def copy_from(self, src: str, dst: str) -> bool:
        """从容器复制文件"""
        result = subprocess.run(
            ["docker", "cp", f"{self.container_name}:{src}", dst],
            capture_output=True, timeout=30
        )
        return result.returncode == 0

    def setup_workspace(self, workspace_path: str, skills: str = "", skills_path: str = "", warmup: str = "") -> None:
        """设置工作空间：复制文件、运行 warmup

        Args:
            workspace_path: 任务工作空间路径
            skills: 技能列表（换行分隔）
            skills_path: 技能文件路径
            warmup: warmup 命令（换行分隔）
        """
        logger.info("[%s] 📁 Setting up workspace...", self.container_name)
        tmp_path = os.path.join(workspace_path, "tmp")
        exec_path = os.path.join(workspace_path, "exec")

        # Copy tmp files
        if os.path.exists(tmp_path):
            self.exec(["mkdir", "-p", f"{self.WORK_DIR}/tmp"])
            self.copy_to(f"{tmp_path}/.", f"{self.WORK_DIR}/tmp/")

        # Copy exec files to /tmp_workspace root
        if os.path.exists(exec_path):
            self.exec(["mkdir", "-p", self.WORK_DIR])
            self.copy_to(f"{exec_path}/.", f"{self.WORK_DIR}/")

        # Setup skills
        if skills and skills_path:
            for line in skills.splitlines():
                line = line.strip()
                if not line:
                    continue
                self.exec(["mkdir", "-p", f"{self.WORK_DIR}/skills/{line}"])
                self.copy_to(f"{skills_path}/{line}", f"{self.WORK_DIR}/skills")

        # Run warmup
        if warmup:
            warmup_cmds = [l.strip() for l in warmup.splitlines() if l.strip() and not l.strip().startswith("#")]
            logger.info("[%s] 🔧 Running %d warmup commands...", self.container_name, len(warmup_cmds))
            for cmd_line in warmup_cmds:
                logger.debug("[%s]    Warmup: %s", self.container_name, cmd_line[:80])
                r = self.exec(["/bin/bash", "-c", cmd_line], timeout=60)
                if r is None or r.returncode != 0:
                    logger.warning("[%s] Warmup command failed: %s", self.container_name, cmd_line)
        logger.info("[%s] ✅ Workspace setup complete", self.container_name)

    def run_agent(self, exec_script: str, timeout_seconds: int) -> tuple[dict, float]:
        """运行 agent 并返回 (result, elapsed_time)

        Args:
            exec_script: 执行脚本内容
            timeout_seconds: 超时时间

        Returns:
            (agent_result_dict, elapsed_time)
        """
        logger.info("[%s] 🤖 Running agent script...", self.container_name)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(exec_script)
            script_path = f.name

        try:
            # Copy script to container with retry
            copy_success = False
            for attempt in range(3):
                try:
                    cp_result = subprocess.run(
                        ["docker", "cp", script_path, f"{self.container_name}:/tmp/exec_nanobot.py"],
                        capture_output=True, timeout=30
                    )
                    if cp_result.returncode == 0:
                        copy_success = True
                        break
                    logger.warning(
                        "[%s] Failed to copy exec script (attempt %d): %s",
                        self.container_name, attempt + 1, cp_result.stderr.decode()[:200]
                    )
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                except subprocess.TimeoutExpired:
                    if attempt < 2:
                        time.sleep(2 ** attempt)

            if not copy_success:
                raise RuntimeError(f"Failed to copy exec script to container after 3 attempts")

            # Execute agent
            start = time.perf_counter()
            try:
                exec_proc = subprocess.run(
                    ["docker", "exec", self.container_name, "python3", "/tmp/exec_nanobot.py"],
                    capture_output=True, text=True, timeout=timeout_seconds + 120
                )
                elapsed = time.perf_counter() - start

                logger.info(
                    "[%s] Agent execution completed in %.2fs, returncode=%d",
                    self.container_name, elapsed, exec_proc.returncode
                )

                # 🆔 打印容器内的输出
                if exec_proc.stdout:
                    for line in exec_proc.stdout.strip().split('\n'):
                        if line:
                            logger.info("[%s] [CONTAINER] %s", self.container_name, line)

                if exec_proc.returncode != 0:
                    logger.error(
                        "[%s] Agent execution failed: stdout=%s, stderr=%s",
                        self.container_name, exec_proc.stdout[:500], exec_proc.stderr[:500]
                    )
            except subprocess.TimeoutExpired:
                elapsed = time.perf_counter() - start
                logger.error("[%s] Agent execution timeout after %.2fs", self.container_name, elapsed)
                raise

            # Get agent_result.json
            with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
                result_file = f.name

            try:
                if self.copy_from(f"{self.WORK_DIR}/agent_result.json", result_file):
                    agent_result = json.loads(Path(result_file).read_text())
                else:
                    agent_result = {"status": "error", "error": "Failed to get agent result"}
            finally:
                Path(result_file).unlink(missing_ok=True)

            return agent_result, elapsed
        finally:
            Path(script_path).unlink(missing_ok=True)

    def run_grading(
        self,
        grading_script: str,
        env: dict = None,
    ) -> dict:
        """在容器内运行评分脚本

        Args:
            grading_script: 评分脚本内容
            env: 环境变量字典

        Returns:
            评分结果字典
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(grading_script)
            script_path = f.name

        try:
            subprocess.run(
                ["docker", "cp", script_path, f"{self.container_name}:/tmp/exec_grading.py"],
                check=True, capture_output=True, timeout=30
            )

            env_args = []
            for k, v in (env or {}).items():
                env_args.extend(["-e", f"{k}={v}"])

            result = subprocess.run(
                ["docker", "exec", *env_args, self.container_name, "python3", "/tmp/exec_grading.py"],
                capture_output=True, text=True, timeout=600
            )

            if result.returncode == 0:
                try:
                    stdout = result.stdout.strip()
                    logger.info("[%s] Grading stdout (first 500): %s", self.container_name, stdout[:500])
                    return json.loads(stdout)
                except json.JSONDecodeError as e:
                    logger.error(
                        "[%s] Failed to parse grading result: %s, stdout: %s",
                        self.container_name, e, result.stdout[:500]
                    )
                    return {"error": f"JSON parse error: {result.stdout[:200]}"}
            else:
                logger.error("[%s] Grading failed: %s", self.container_name, result.stderr[:500])
                return {"error": result.stderr[:500]}
        except Exception as exc:
            logger.error("[%s] Grading failed: %s", self.container_name, exc)
            return {"error": str(exc)}
        finally:
            Path(script_path).unlink(missing_ok=True)

    def copy_results(
        self,
        workspace_path: str,
        output_dir: Path,
        session_file: str,
    ) -> tuple[Path, Path]:
        """复制结果文件到输出目录

        Args:
            workspace_path: 任务工作空间路径
            output_dir: 输出目录
            session_file: session 文件名 (如 eval_model_task.json)

        Returns:
            (result_file, transcript_file)
        """
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        result_file = output_dir / "agent_result.json"
        transcript_file = output_dir / "transcript.json"

        # Retry logic for docker cp
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Copy agent_result.json
                r1 = subprocess.run(
                    ["docker", "cp", f"{self.container_name}:{self.WORK_DIR}/agent_result.json", str(result_file)],
                    capture_output=True, timeout=30
                )
                if r1.returncode != 0:
                    logger.warning(
                        "[%s] Failed to copy agent_result.json (attempt %d): %s",
                        self.container_name, attempt + 1, r1.stderr.decode()[:200]
                    )

                # Copy transcript from .sessions
                r2 = subprocess.run(
                    ["docker", "cp", f"{self.container_name}:{self.WORK_DIR}/.sessions/{session_file}", str(transcript_file)],
                    capture_output=True, timeout=30
                )
                if r2.returncode != 0:
                    logger.warning(
                        "[%s] Failed to copy transcript (attempt %d): %s",
                        self.container_name, attempt + 1, r2.stderr.decode()[:200]
                    )

                # Copy results dir
                results_on_host = Path(workspace_path) / "results"
                r3 = subprocess.run(
                    ["docker", "cp", f"{self.container_name}:{self.WORK_DIR}/results", str(results_on_host.parent)],
                    capture_output=True, timeout=30
                )
                if r3.returncode != 0:
                    # Try individual files
                    for fname in ["transcript_en.txt", "transcript_zh.txt", "output.mp4", "predictions.json"]:
                        src = f"{self.container_name}:{self.WORK_DIR}/results/{fname}"
                        dst = results_on_host / fname
                        subprocess.run(["docker", "cp", src, str(dst)], capture_output=True, timeout=10)

                break
            except subprocess.TimeoutExpired:
                logger.warning("[%s] docker cp timeout (attempt %d/%d)", self.container_name, attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                logger.error("[%s] Error copying results (attempt %d): %s", self.container_name, attempt + 1, e)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

        return result_file, transcript_file

    def cleanup(self) -> None:
        """清理容器"""
        if self.container_name:
            subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True)
            self.container_name = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()
