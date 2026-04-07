"""Simplified SkillsBench implementation without mount points.

Uses docker cp instead of volume mounts for file transfer.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

from ..utils.log import log
from .base import BaseBenchmark


class SkillsBenchSimple(BaseBenchmark):
    """Simplified SkillsBench using docker cp instead of mounts."""

    DISPLAY_NAME = "SkillsBench-Simple"
    TASK_COUNT = 56
    SCORE_RANGE = "0-100%"

    # Container work directory (fixed, no mount point needed)
    CONTAINER_WORK_DIR = "/work"

    def __init__(self, use_docker: bool = True, reuse_container: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.use_docker = use_docker
        self.reuse_container = reuse_container
        super().__init__(**kwargs)

    def _get_tasks_dir(self) -> Path:
        """Get tasks directory."""
        local = self.base_dir / "benchmarks" / "skillsbench" / "tasks"
        if local.exists():
            return local
        ext = os.getenv("SKILLSBENCH_DIR")
        if ext:
            return Path(ext) / "tasks"
        return local

    def evaluate(self, model_key: str, config: dict, sample: int = 0,
                 transcripts_dir: Path = None, **kwargs) -> dict:
        """Run SkillsBench evaluation."""
        tasks_dir = self._get_tasks_dir()
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        max_turns = kwargs.get("max_turns", 3)
        all_tasks = sorted([d.name for d in tasks_dir.iterdir() if d.is_dir()])
        task_names = all_tasks  # No skipping in simple mode

        # Filter by task_ids if specified
        task_ids = kwargs.get("task_ids")
        if task_ids:
            task_names = [t for t in task_names if t in task_ids]

        if sample and sample < len(task_names):
            import random
            random.seed(42)
            task_names = random.sample(task_names, sample)

        results = []
        passed = 0

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        proxy_http = os.environ.get('HTTP_PROXY_INNER', '')
        proxy_https = os.environ.get('HTTPS_PROXY_INNER', '')

        for task_name in task_names:
            result = self._run_single_task(
                task_name, config, tasks_dir, max_turns,
                openrouter_api_key, proxy_http, proxy_https,
                transcripts_dir=transcripts_dir, model_key=model_key
            )
            if result.get("status") == "passed":
                passed += 1
            results.append(result)

            # Save result for this task
            self.save_result("skillsbench-simple", model_key, result, filename=f"{task_name}.json")

        total = len(task_names)
        score = round(passed / total * 100, 1) if total else 0
        summary = {
            "model": model_key, "total": total, "passed": passed,
            "failed": total - passed, "score": score,
            "pass_rate": f"{passed}/{total}", "max_turns": max_turns,
            "results": results,
        }
        self.save_result("skillsbench-simple", model_key, summary)
        return summary

    def _run_single_task(self, task_name: str, config: dict, tasks_dir: Path,
                         max_turns: int, openrouter_api_key: str,
                         proxy_http: str, proxy_https: str,
                         transcripts_dir: Path = None, model_key: str = None) -> dict:
        """Run a single task using docker cp (no mounts)."""
        task_dir = tasks_dir / task_name
        instruction = (task_dir / "instruction.md").read_text(encoding="utf-8")
        env_dockerfile = task_dir / "environment" / "Dockerfile"

        if not env_dockerfile.exists():
            return {"task": task_name, "status": "skipped", "error": "no Dockerfile"}

        # Build image
        task_image = f"skillsbench-task-{task_name}:latest"
        container_name = f"sb-simple-{task_name}"

        log(f"[{task_name}] 🔨 Building image...")
        build_cmd = ["docker", "build", "-t", task_image, "-f", str(env_dockerfile),
                     str(task_dir / "environment")]
        try:
            result = subprocess.run(build_cmd, capture_output=True, text=True, timeout=1800)
            if result.returncode != 0:
                return {"task": task_name, "status": "skipped",
                        "error": f"build failed: {result.stderr[:500]}"}
        except Exception as e:
            return {"task": task_name, "status": "skipped", "error": str(e)}

        # Create host workspace
        workspace_host = Path(f"/tmp/skillsbench_simple/{task_name}")
        if workspace_host.exists():
            shutil.rmtree(workspace_host)
        workspace_host.mkdir(parents=True)

        # Copy environment files to workspace
        env_dir = task_dir / "environment"
        for f in env_dir.rglob("*"):
            if f.is_file() and f.name != "Dockerfile":
                rel = f.relative_to(env_dir)
                dst = workspace_host / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)

        # Start container (no mounts!)
        log(f"[{task_name}] 🐳 Starting container...")
        env_args = [
            "-e", f"http_proxy={proxy_http}",
            "-e", f"https_proxy={proxy_https}",
            "-e", f"OPENROUTER_API_KEY={openrouter_api_key}",
        ]

        docker_run_cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            *env_args,
            task_image,
            "/bin/bash", "-c", "tail -f /dev/null",
        ]

        try:
            result = subprocess.run(docker_run_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return {"task": task_name, "status": "error",
                        "error": f"container start failed: {result.stderr[:500]}"}
        except Exception as e:
            return {"task": task_name, "status": "error", "error": str(e)}

        # Copy files to container
        log(f"[{task_name}] 📤 Copying files to container...")
        subprocess.run(
            ["docker", "cp", f"{workspace_host}/.", f"{container_name}:{self.CONTAINER_WORK_DIR}"],
            capture_output=True, text=True, timeout=60
        )

        # Create output directory in container
        subprocess.run(
            ["docker", "exec", container_name, "mkdir", "-p", f"{self.CONTAINER_WORK_DIR}/output"],
            capture_output=True, text=True
        )

        # Run agent
        log(f"[{task_name}] 🤖 Running agent (max {max_turns} turns)...")
        result = self._run_agent_simple(
            container_name, task_name, config, instruction,
            max_turns, model_key, transcripts_dir
        )

        # Copy results back
        log(f"[{task_name}] 📥 Copying results back...")
        subprocess.run(
            ["docker", "cp", f"{container_name}:{self.CONTAINER_WORK_DIR}/output/", str(workspace_host)],
            capture_output=True, text=True, timeout=30
        )

        # Run pytest
        log(f"[{task_name}] 🧪 Running pytest...")
        passed, test_output = self._run_pytest_simple(container_name, task_dir)

        # Cleanup
        subprocess.run(["docker", "rm", "-f", container_name],
                      capture_output=True, text=True, timeout=30)

        return result

    def _run_agent_simple(self, container_name: str, task_name: str, config: dict,
                          instruction: str, max_turns: int, model_key: str,
                          transcripts_dir: Path = None) -> dict:
        """Run agent in container using docker cp (no mounts)."""
        import sys
        from pathlib import Path

        # Import HarborNanoBotAgent
        openclawpro_path = None
        candidates = [
            os.getenv("OPENCLAWPRO_DIR"),
            str(Path(__file__).parent.parent.parent / "OpenClawPro"),
        ]
        for path_str in candidates:
            if path_str and (Path(path_str) / "harness" / "agent" / "nanobot.py").exists():
                openclawpro_path = str(Path(path_str))
                break

        if not openclawpro_path:
            return {"task": task_name, "status": "error", "error": "OpenClawPro not found"}

        if openclawpro_path not in sys.path:
            sys.path.insert(0, openclawpro_path)

        from harness.agent.nanobot import HarborNanoBotAgent

        # Create agent with container_work_dir as mount_point
        agent = HarborNanoBotAgent(
            container_name=container_name,
            mount_point=self.CONTAINER_WORK_DIR,
            model=config["model"],
            api_url=config["api_url"],
            api_key=config["api_key"],
            workspace=Path(f"/tmp/skillsbench_simple/{task_name}"),
            timeout=300,
            disable_safety_guard=True,
        )

        # Modify instruction to use container path
        modified_instruction = instruction.replace("/root/", f"{self.CONTAINER_WORK_DIR}/")
        modified_instruction = modified_instruction.replace("/workspace/", f"{self.CONTAINER_WORK_DIR}/")

        prompt = (
            f"Complete this programming task in the workspace {self.CONTAINER_WORK_DIR}.\n\n"
            f"TASK INSTRUCTIONS:\n{modified_instruction}\n\n"
            f"Use the tools to write files and execute code directly in the workspace. "
            f"All output files must be created at the paths specified in the instructions."
        )

        all_transcripts = []
        test_output = ""

        for turn in range(max_turns):
            log(f"[{task_name}] 🔄 Agent turn {turn + 1}/{max_turns}")
            try:
                result = agent.execute(prompt, session_id=f"simple_{task_name}_t{turn}")
            except Exception as e:
                return {"task": task_name, "status": "error", "error": str(e)[:500], "turns": turn + 1}

            if result.transcript:
                all_transcripts.extend(result.transcript)

            # Save transcript after each turn
            if transcripts_dir and model_key and all_transcripts:
                self._save_transcript(model_key, task_name, all_transcripts, turn=turn + 1)

            # Run pytest
            log(f"[{task_name}] 🧪 Running pytest...")
            passed, test_output = self._run_pytest_simple(container_name, Path(f"/tmp/skillsbench_simple/{task_name}"))

            if passed:
                log(f"[{task_name}] ✅ Pytest passed!")
                if transcripts_dir and model_key and all_transcripts:
                    self._save_transcript(model_key, task_name, all_transcripts)
                return {"task": task_name, "status": "passed", "turns": turn + 1}

            log(f"[{task_name}] ❌ Pytest failed, preparing feedback...")
            if turn < max_turns - 1:
                prompt = (
                    f"The tests FAILED. Fix the code in the workspace {self.CONTAINER_WORK_DIR}.\n\n"
                    f"PYTEST OUTPUT:\n{test_output[-2000:]}\n\n"
                    f"Fix the code and ensure all output files are created at the correct paths."
                )

        if transcripts_dir and model_key and all_transcripts:
            self._save_transcript(model_key, task_name, all_transcripts)
        return {"task": task_name, "status": "failed", "turns": max_turns,
                "test_output": test_output[-1000:]}

    def _save_transcript(self, model_key: str, task_name: str, transcript: list, turn: int = None):
        """Save transcript to file."""
        try:
            trans_path = self.results_dir / "skillsbench_simple" / "transcripts" / model_key / task_name
            trans_path.mkdir(parents=True, exist_ok=True)
            normalized = []
            for e in transcript:
                if isinstance(e, dict) and "message" in e:
                    normalized.append(e["message"])
                else:
                    normalized.append(e)
            if turn is not None:
                (trans_path / f"transcript_turn_{turn}.json").write_text(
                    json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            else:
                (trans_path / "transcript.json").write_text(
                    json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8"
                )
        except Exception:
            pass

    def _run_pytest_simple(self, container_name: str, task_dir: Path) -> tuple:
        """Run pytest in container (no mount)."""
        # Copy test files to container
        tests_src = task_dir / "tests"
        if not tests_src.exists():
            return False, "no tests"

        subprocess.run(
            ["docker", "exec", container_name, "mkdir", "-p", f"{self.CONTAINER_WORK_DIR}/tests"],
            capture_output=True, text=True
        )

        for f in tests_src.glob("*"):
            if f.is_file():
                # Read and modify paths
                content = f.read_text(encoding="utf-8")
                content = content.replace("/root/", f"{self.CONTAINER_WORK_DIR}/")
                content = content.replace("/workspace/", f"{self.CONTAINER_WORK_DIR}/")

                # Write to temp and copy
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name

                subprocess.run(
                    ["docker", "cp", tmp_path, f"{container_name}:{self.CONTAINER_WORK_DIR}/tests/{f.name}"],
                    capture_output=True, text=True
                )
                os.unlink(tmp_path)

        # Install pytest and run
        subprocess.run(
            ["docker", "exec", container_name, "pip", "install", "-q", "pytest"],
            capture_output=True, text=True, timeout=120
        )

        result = subprocess.run(
            ["docker", "exec", "-w", self.CONTAINER_WORK_DIR, container_name,
             "python3", "-m", "pytest", f"{self.CONTAINER_WORK_DIR}/tests", "-v", "--tb=short"],
            capture_output=True, text=True, timeout=120
        )

        return result.returncode == 0, result.stdout[-1500:] + "\n" + result.stderr[-500:]
