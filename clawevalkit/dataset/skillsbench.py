"""SkillsBench — 56+ 个纯 Python 任务 (无 Docker)，多轮 Agent 模式。

评分方式: NanoBotAgent 在 workspace 中自主编写代码 → pytest 验证 (pass/fail)。
支持多轮迭代: 若 pytest 失败，把错误反馈给 NanoBotAgent 让它修正，最多 MAX_TURNS 轮。

工作流: 读 instruction.md → NanoBotAgent 在 workspace 中写文件/执行代码 →
跑 pytest 验证 → 失败则反馈修正 → 最多 max_turns 轮。

Docker 支持: 使用 --docker 时，每个任务用自己的 Dockerfile 构建镜像，在容器内运行 NanoBotAgent。
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
import uuid
from datetime import datetime
from pathlib import Path

from ..utils.nanobot import import_nanobot_agent
from ..utils.log import log
from .base import BaseBenchmark

# 需要 Docker 或特殊系统依赖的任务（不使用 Docker 时跳过）
SKIP_TASKS = {
    # Docker only
    "fix-build-agentops", "fix-build-google-auto", "setup-fuzzing-py", "suricata-custom-exfil",
    # Java/SDKMAN/Maven
    "fix-druid-loophole-cve", "flink-query", "python-scala-translation", "spring-boot-jakarta-migration",
    # Erlang
    "fix-erlang-ssh-cve",
    # Go build
    "syzkaller-ppdev-syzlang",
    # Lean4
    "lean4-proof",
    # Rust
    "multilingual-video-dubbing",
    # FFmpeg/视频
    "dynamic-object-aware-egomotion", "mario-coin-counting", "pedestrian-traffic-counting",
    "pg-essay-to-audiobook", "video-filler-word-remover",
    # Node.js
    "threejs-structure-parser", "threejs-to-obj",
    # Graphviz/特殊工具
    "software-dependency-audit",
}

# 即使在 Docker 模式下也跳过的任务（环境有问题或需要 GPU 等）
SKIP_TASKS_DOCKER = {
    "jpg-ocr-stat",  # tesseract 相关问题
    # 需要 GPU 的任务可以在这里添加
}

# 依赖"容易解决"的任务（不使用 Docker 时可评测）
# pip install graphviz, pip install jax, npm install d3, pip install moviepy,
# apt install ffmpeg, npm install (Next.js), apt install gh, Gmail API
EASY_SKIP_TASKS = {
    "azure-bgp-oscillation-route-leak",  # 纯 Python
    "dialogue-parser",                   # graphviz: pip install graphviz
    "jax-computing-basics",              # JAX: pip install jax
    "data-to-d3",                        # Node.js + D3: npm install
    "video-silence-remover",              # FFmpeg + moviepy: pip install moviepy
    "video-tutorial-indexer",            # FFmpeg: apt install ffmpeg
    "fix-visual-stability",              # Next.js/React: npm install
    "react-performance-debugging",       # Next.js/React: npm install
    "gh-repo-analytics",                 # gh CLI: apt install gh
    "enterprise-information-search",     # gh CLI: apt install gh
    "scheduling-email-assistant",         # Gmail API: 纯 Python
}




def _run_pytest(workspace: Path, task_dir: Path) -> tuple:
    """运行 pytest 验证，返回 (passed: bool, output: str)。"""
    tests_src = task_dir / "tests"
    if not tests_src.exists():
        return False, "no tests/ directory"

    test_py = tests_src / "test_outputs.py"
    if not test_py.exists():
        return False, "no test_outputs.py"

    tests_workspace = workspace / "tests"
    tests_workspace.mkdir(parents=True, exist_ok=True)

    # 复制所有测试相关文件（不仅是 test_outputs.py）
    for f in tests_src.glob("*"):
        if f.is_file() and f.name != "Dockerfile":
            dst = tests_workspace / f.name
            # 对 test_outputs.py 进行路径替换（仅文本文件）
            if f.suffix in [".py", ".md", ".sh", ".txt", ".json"]:
                test_content = f.read_text(encoding="utf-8")
                if f.name == "test_outputs.py":
                    # 替换字符串中的路径
                    test_content = test_content.replace("/root/", f"{workspace}/")
                    test_content = test_content.replace("'/root'", f"'{workspace}'")
                    test_content = test_content.replace('"/root"', f'"{workspace}"')
                    # Docker 容器内路径映射
                    test_content = test_content.replace("/app/", f"{workspace}/")
                    test_content = test_content.replace("'/app/", f"'{workspace}/")
                    test_content = test_content.replace('"/app/', f'"{workspace}/')
                    # 替换 Path("/root/...") 和 Path("/app/...") 格式
                    import re
                    test_content = re.sub(r'Path\("(?:/root/|/app/)', f'Path("{workspace}/', test_content)
                    test_content = re.sub(r"Path\('(?:/root/|/app/)", f"Path('{workspace}/", test_content)
                dst.write_text(test_content, encoding="utf-8")
            else:
                # 二进制文件直接复制
                shutil.copy2(f, dst)

    env = os.environ.copy()
    env["HOME"] = str(workspace)

    try:
        proc = subprocess.run(
            ["python3", "-m", "pytest", str(tests_workspace / "test_outputs.py"), "-v", "--tb=short"],
            cwd=workspace, capture_output=True, text=True, timeout=120, env=env,
        )
        return proc.returncode == 0, proc.stdout[-1500:] + "\n" + proc.stderr[-500:]
    except subprocess.TimeoutExpired:
        return False, "pytest timeout"
    except Exception as exc:
        return False, f"pytest error: {exc}"


def _list_workspace_files(workspace: Path) -> str:
    """列出 workspace 中的文件（排除 tests/ 和 __pycache__），用于反馈给 LLM。"""
    files = []
    for f in sorted(workspace.rglob("*")):
        if f.is_file() and "__pycache__" not in str(f) and ".pytest_cache" not in str(f):
            rel = f.relative_to(workspace)
            if str(rel).startswith("tests/"):
                continue
            size = f.stat().st_size
            files.append(f"  {rel} ({size} bytes)")
    return "\n".join(files[:50])


class SkillsBench(BaseBenchmark):
    DISPLAY_NAME = "SkillsBench"
    TASK_COUNT = 56
    SCORE_RANGE = "0-100%"

    def __init__(self, use_docker: bool = True, **kwargs):
        self.use_docker = use_docker
        super().__init__(**kwargs)

    def _get_tasks_dir(self) -> Path:
        """SkillsBench 任务目录，优先 NANOPRO_DIR 环境变量。"""
        # 优先检查仓库内 benchmarks/ 目录，其次通过环境变量
        local = self.base_dir / "benchmarks" / "skillsbench" / "tasks"
        if local.exists():
            return local
        ext = os.getenv("SKILLSBENCH_DIR")
        if ext:
            return Path(ext) / "tasks"
        return local  # 返回本地路径（不存在时 evaluate 会报错）

    def evaluate(self, model_key: str, config: dict, sample: int = 0,
                 transcripts_dir: Path = None, **kwargs) -> dict:
        """运行 SkillsBench 多轮 agent 评测。

        整体流程:
        1. 扫描 tasks_dir 下的可执行任务（排除 SKIP_TASKS）
        2. 对每个任务: 读 instruction.md → 发送给 LLM → 提取代码 → 执行 → pytest
        3. 若 pytest 失败，反馈错误让 LLM 修正，最多 max_turns 轮
        4. 汇总结果并保存

        Docker 模式 (use_docker=True):
        - 每个任务用自己的 Dockerfile 构建镜像
        - 在容器内运行 NanoBotAgent
        - 挂载 OpenClawPro 实现代码热更新
        """
        use_docker = kwargs.get("use_docker", self.use_docker)

        # Docker 模式走专用路径
        if use_docker:
            return self._evaluate_docker(model_key, config, sample, transcripts_dir, **kwargs)

        tasks_dir = self._get_tasks_dir()
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        max_turns = kwargs.get("max_turns", 3)
        all_tasks = sorted([d.name for d in tasks_dir.iterdir() if d.is_dir()])
        # 根据 use_docker 决定跳过哪些任务
        if self.use_docker:
            # 使用 Docker：跳过需要特殊依赖的任务
            skip_set = SKIP_TASKS
        else:
            # 不使用 Docker：跳过 Docker 专用任务，但保留依赖容易解决的任务
            skip_set = SKIP_TASKS - EASY_SKIP_TASKS
        task_names = [t for t in all_tasks if t not in skip_set]

        # Support task_ids filter from --task argument
        task_ids = kwargs.get("task_ids")
        if task_ids:
            task_names = [t for t in task_names if t in task_ids]
            if not task_names:
                return {"score": 0, "total": 0, "error": f"no tasks match task_ids: {task_ids}"}

        if sample and sample < len(task_names):
            random.seed(42)
            task_names = random.sample(task_names, sample)

        workspace_base = Path("/tmp/skillsbench_workspace")
        results = []
        passed = 0

        for i, task_name in enumerate(task_names):
            start = time.time()
            result = self._run_single_task(task_name, config, tasks_dir, workspace_base, max_turns,
                                           transcripts_dir=transcripts_dir, model_key=model_key)
            result["elapsed_s"] = round(time.time() - start, 2)
            if result.get("status") == "passed":
                passed += 1
            results.append(result)

        total = len(task_names)
        score = round(passed / total * 100, 1) if total else 0
        summary = {
            "model": model_key, "total": total, "passed": passed,
            "failed": total - passed, "score": score,
            "pass_rate": f"{passed}/{total}", "max_turns": max_turns,
            "skipped_docker": len(SKIP_TASKS), "results": results,
        }
        self.save_result("skillsbench", model_key, summary)
        return summary

    def _run_single_task(self, task_name: str, config: dict, tasks_dir: Path,
                         workspace_base: Path, max_turns: int = 3,
                         transcripts_dir: Path = None, model_key: str = None) -> dict:
        """运行单个 SkillsBench 任务 (NanoBotAgent 多轮模式)。

        流程: 读 instruction.md → 复制 environment 文件到 workspace →
        NanoBotAgent 在 workspace 中自主写文件/执行代码 → pytest 验证 →
        失败则反馈给 agent 修正，最多 max_turns 轮。

        NanoBotAgent 内置 WriteFile、Exec 等 tools，可直接在 workspace 中操作，
        无需手动从 LLM 回复中提取代码。
        """
        NanoBotAgent = import_nanobot_agent()

        task_dir = tasks_dir / task_name
        instruction = (task_dir / "instruction.md").read_text(encoding="utf-8")

        workspace = workspace_base / task_name
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)

        # 复制 environment/ 下的文件到 workspace
        self._setup_workspace(task_dir, workspace)

        agent = NanoBotAgent(model=config["model"], api_url=config["api_url"],
                             api_key=config["api_key"], workspace=workspace, timeout=300)

        prompt = (
            f"Complete this programming task in the workspace {workspace}.\n\n"
            f"TASK INSTRUCTIONS:\n{instruction}\n\n"
            f"Use the tools to write files and execute code directly in the workspace. "
            f"All output files must be created at the paths specified in the instructions."
        )

        all_transcripts = []
        for turn in range(max_turns):
            try:
                result = agent.execute(prompt, session_id=f"skills_{task_name}_t{turn}")
            except Exception as e:
                return {"task": task_name, "status": "error", "error": str(e)[:500], "turns": turn + 1}

            # 保存 transcript
            if result and hasattr(result, "transcript") and result.transcript:
                all_transcripts.extend(result.transcript)

            # Harness 负责最终 pytest 验证
            passed, test_output = _run_pytest(workspace, task_dir)
            if passed:
                # 保存成功的 transcript
                if transcripts_dir and model_key and all_transcripts:
                    self._save_transcript(model_key, task_name, all_transcripts)
                return {"task": task_name, "status": "passed", "turns": turn + 1}

            # pytest 失败 → 反馈给 agent
            if turn < max_turns - 1:
                workspace_files = _list_workspace_files(workspace)
                prompt = (
                    f"The tests FAILED. Fix the code in the workspace.\n\n"
                    f"PYTEST OUTPUT:\n{test_output[-2000:]}\n\n"
                    f"FILES IN WORKSPACE:\n{workspace_files}"
                )

        # 保存失败的 transcript
        if transcripts_dir and model_key and all_transcripts:
            self._save_transcript(model_key, task_name, all_transcripts)
        return {"task": task_name, "status": "failed", "turns": max_turns,
                "test_output": test_output[-1000:]}

    def _save_transcript(self, model_key: str, task_name: str, transcript: list):
        """保存 agent 轨迹到文件（统一结构）。

        保存到: outputs/skillsbench/transcripts/{model}/{task}/transcript.json
        """
        try:
            trans_path = self.results_dir / "skillsbench" / "transcripts" / model_key / task_name
            trans_path.mkdir(parents=True, exist_ok=True)
            normalized = []
            for e in transcript:
                if isinstance(e, dict) and "message" in e:
                    normalized.append(e["message"])
                else:
                    normalized.append(e)
            (trans_path / "transcript.json").write_text(
                json.dumps(normalized, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log(f"[{task_name}] Saved transcript to {trans_path / 'transcript.json'}")
        except Exception:
            pass  # transcript 保存失败不影响主流程

    def _setup_workspace(self, task_dir: Path, workspace: Path):
        """复制 environment/ 下的文件到 workspace（排除 Dockerfile）。"""
        env_dir = task_dir / "environment"
        if not env_dir.exists():
            return
        for f in env_dir.rglob("*"):
            if f.is_file() and f.name != "Dockerfile":
                rel = f.relative_to(env_dir)
                dst = workspace / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)

    def _remove_container(self, container_name: str):
        """清理 Docker 容器（如果存在）。"""
        try:
            subprocess.run(["docker", "rm", "-f", container_name],
                          capture_output=True, text=True, timeout=30)
        except Exception:
            pass

    def _evaluate_docker(self, model_key: str, config: dict, sample: int = 0,
                         transcripts_dir: Path = None, **kwargs) -> dict:
        """Per-task Docker 模式: 每个任务用自己的 Dockerfile 构建镜像，在容器内运行 NanoBotAgent。

        工作流:
        1. 遍历所有任务（排除 SKIP_TASKS_DOCKER）
        2. 对每个任务:
           - 构建镜像: docker build -t task-{task_name} task/environment/
           - 启动容器（挂载 OpenClawPro 实现热更新）
           - 复制 environment 文件到 /workspace
           - 执行 NanoBotAgent
           - pytest 验证
           - 收集结果并清理
        """
        # Determine OpenClawPro directory for volume mount
        openclawpro_dir = Path(os.getenv("OPENCLAWPRO_DIR",
            str(Path(__file__).parent.parent.parent / "OpenClawPro")))
        if not openclawpro_dir.exists():
            raise FileNotFoundError(f"OpenClawPro directory not found: {openclawpro_dir}")

        tasks_dir = self._get_tasks_dir()
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        max_turns = kwargs.get("max_turns", 3)
        all_tasks = sorted([d.name for d in tasks_dir.iterdir() if d.is_dir()])
        # Docker 模式下跳过 SKIP_TASKS_DOCKER，但不再跳过 SKIP_TASKS（Docker 可以处理）
        task_names = [t for t in all_tasks if t not in SKIP_TASKS_DOCKER]

        # Support task_ids filter from --task argument
        task_ids = kwargs.get("task_ids")
        if task_ids:
            task_names = [t for t in task_names if t in task_ids]
            if not task_names:
                return {"score": 0, "total": 0, "error": f"no tasks match task_ids: {task_ids}"}

        if sample and sample < len(task_names):
            random.seed(42)
            task_names = random.sample(task_names, sample)

        results = []
        passed = 0

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        proxy_http = os.environ.get('HTTP_PROXY_INNER', '')
        proxy_https = os.environ.get('HTTPS_PROXY_INNER', '')

        for i, task_name in enumerate(task_names):
            # Per-task deduplication: check for existing result before running
            task_result_dir = self.results_dir / "skillsbench" / model_key / task_name
            dedup_file = task_result_dir / "result.json"
            if dedup_file.exists():
                try:
                    cached = json.loads(dedup_file.read_text())
                    if cached.get("status") in ("passed", "failed"):
                        log(f"[{task_name}] Found cached result, skipping")
                        cached["_from_cache"] = True
                        results.append(cached)
                        if cached.get("status") == "passed":
                            passed += 1
                        continue
                except Exception:
                    pass

            start = time.time()
            result = self._run_single_task_docker(
                task_name, config, tasks_dir, max_turns,
                openclawpro_dir, openrouter_api_key, proxy_http, proxy_https,
                transcripts_dir=transcripts_dir, model_key=model_key
            )
            result["elapsed_s"] = round(time.time() - start, 2)

            # Save result to dedup location (unified structure)
            task_result_dir = self.results_dir / "skillsbench" / model_key / task_name
            task_result_dir.mkdir(parents=True, exist_ok=True)
            (task_result_dir / "result.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            log(f"[{task_name}] Saved result to {task_result_dir / 'result.json'}")

            if result.get("status") == "passed":
                passed += 1
            results.append(result)

        total = len(task_names)
        score = round(passed / total * 100, 1) if total else 0
        summary = {
            "model": model_key, "total": total, "passed": passed,
            "failed": total - passed, "score": score,
            "pass_rate": f"{passed}/{total}", "max_turns": max_turns,
            "skipped_docker": len(SKIP_TASKS_DOCKER), "results": results,
        }
        self.save_result("skillsbench", model_key, summary)
        return summary

    def _setup_container_paths(self, container_name: str, instruction: str, mount_point: str):
        """Detect instruction paths and create appropriate symlinks in container.

        Different tasks use different path patterns:
        - /root/input/ + /root/output/ (e.g., edit-pdf)
        - /workspace/ (e.g., spring-boot-jakarta-migration)
        - /app/workspace/ (e.g., flink-query, lean4-proof, jpg-ocr-stat)
        - /root/workspace/ (e.g., parallel-tfidf-search)

        The mount_point is determined by the task pattern:
        - /app/workspace/ tasks: mount at /app/workspace
        - All other tasks: mount at /workspace

        We create symlinks for /root/input and /root/output based on the mount point.
        """
        # Pattern: /root/input/ and /root/output/
        if "/root/input/" in instruction or "/root/output/" in instruction:
            subprocess.run(["docker", "exec", container_name, "mkdir", "-p", f"{mount_point}/input", f"{mount_point}/output"],
                          capture_output=True, text=True)
            subprocess.run(["docker", "exec", container_name, "ln", "-sf", f"{mount_point}/input", "/root/input"],
                          capture_output=True, text=True)
            subprocess.run(["docker", "exec", container_name, "ln", "-sf", f"{mount_point}/output", "/root/output"],
                          capture_output=True, text=True)

        # Pattern: /app/ (but not /app/workspace which is the mount point itself)
        # Create symlink so /app maps to mount_point, and subdirectories work automatically
        if "/app/" in instruction and "/app/workspace/" not in instruction:
            # Remove original /app directory and replace with symlink to mount_point
            subprocess.run(["docker", "exec", container_name, "rm", "-rf", "/app"],
                          capture_output=True, text=True)
            subprocess.run(["docker", "exec", container_name, "ln", "-sf", mount_point, "/app"],
                          capture_output=True, text=True)
            # Ensure data and output directories exist inside mount_point
            if "/app/data/" in instruction:
                subprocess.run(["docker", "exec", container_name, "mkdir", "-p", f"{mount_point}/data"],
                              capture_output=True, text=True)
            if "/app/output/" in instruction:
                subprocess.run(["docker", "exec", container_name, "mkdir", "-p", f"{mount_point}/output"],
                              capture_output=True, text=True)

        # Pattern: /root/workspace/ - mount at /workspace already works since /workspace != /root/workspace
        # No symlink needed for this pattern

        # Pattern: pure /root/ paths (e.g., /root/scan_data.stl, /root/mass_report.json)
        # If instruction uses /root/ but not /root/input/, /root/output/, or /root/workspace/
        # we need to symlink /root to mount_point so files written to /root/ appear in workspace
        if "/root/" in instruction and "/root/input/" not in instruction and "/root/output/" not in instruction and "/root/workspace/" not in instruction:
            # Remove original /root directory and replace with symlink to mount_point
            subprocess.run(["docker", "exec", container_name, "rm", "-rf", "/root"],
                          capture_output=True, text=True)
            subprocess.run(["docker", "exec", container_name, "ln", "-sf", mount_point, "/root"],
                          capture_output=True, text=True)

    def _run_single_task_docker(self, task_name: str, config: dict, tasks_dir: Path,
                                 max_turns: int, openclawpro_dir: Path,
                                 openrouter_api_key: str, proxy_http: str, proxy_https: str,
                                 transcripts_dir: Path = None, model_key: str = None) -> dict:
        """在 per-task Docker 容器内运行单个 SkillsBench 任务。"""
        task_dir = tasks_dir / task_name
        instruction = (task_dir / "instruction.md").read_text(encoding="utf-8")
        env_dockerfile = task_dir / "environment" / "Dockerfile"

        if not env_dockerfile.exists():
            return {"task": task_name, "status": "skipped", "error": "no Dockerfile"}

        # Build per-task Docker image
        task_image = f"skillsbench-task-{task_name}:latest"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = uuid.uuid4().hex[:6]
        container_name = f"sb_{task_name}_{timestamp}_{run_id}"

        build_cmd = ["docker", "build", "-t", task_image, "-f", str(env_dockerfile)]
        if proxy_http:
            build_cmd.insert(1, "--build-arg")
            build_cmd.insert(2, f"http_proxy={proxy_http}")
            build_cmd.insert(1, "--build-arg")
            build_cmd.insert(2, f"https_proxy={proxy_https}")
        build_cmd.append(str(task_dir / "environment"))

        try:
            build_proc = subprocess.run(build_cmd, capture_output=True, text=True, timeout=600)
            if build_proc.returncode != 0:
                return {"task": task_name, "status": "skipped",
                        "error": f"docker build failed: {build_proc.stderr[:500]}"}
        except subprocess.TimeoutExpired:
            return {"task": task_name, "status": "skipped", "error": "docker build timeout"}
        except Exception as e:
            return {"task": task_name, "status": "skipped", "error": str(e)}

        # Create workspace directory for this task
        workspace_host = Path(f"/tmp/skillsbench_workspace/{task_name}")
        if workspace_host.exists():
            shutil.rmtree(workspace_host)
        workspace_host.mkdir(parents=True)

        # Copy environment files (except Dockerfile) to workspace
        env_dir = task_dir / "environment"
        for f in env_dir.rglob("*"):
            if f.is_file() and f.name != "Dockerfile":
                rel = f.relative_to(env_dir)
                dst = workspace_host / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)

        # Prepare env args
        env_args = [
            "-e", f"http_proxy={proxy_http}",
            "-e", f"https_proxy={proxy_https}",
            "-e", f"HTTP_PROXY={proxy_http}",
            "-e", f"HTTPS_PROXY={proxy_https}",
            "-e", f"OPENROUTER_API_KEY={openrouter_api_key}",
        ]

        # Start container
        # Determine mount point based on instruction path pattern
        # /app/workspace/ tasks need mount at /app/workspace, all others at /workspace
        mount_point = "/app/workspace" if "/app/workspace/" in instruction else "/workspace"

        docker_run_cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-v", f"{workspace_host}:{mount_point}:rw",
            "-v", f"{openclawpro_dir}:/root/OpenClawPro:rw",
            "-w", "/",
            *env_args,
            task_image,
            "/bin/bash", "-c", "tail -f /dev/null",
        ]

        try:
            run_proc = subprocess.run(docker_run_cmd, capture_output=True, text=True, timeout=60)
            if run_proc.returncode != 0:
                return {"task": task_name, "status": "error",
                        "error": f"container start failed: {run_proc.stderr[:500]}"}
        except subprocess.TimeoutExpired:
            return {"task": task_name, "status": "error", "error": "container start timeout"}
        except Exception as e:
            return {"task": task_name, "status": "error", "error": str(e)}

        # For /app/ tasks: copy data and skills BEFORE creating symlinks
        # (Once /app -> /workspace symlink exists, /app/data and /app/skills would resolve to /workspace/*)
        if "/app/" in instruction and "/app/workspace/" not in instruction:
            # Copy data from image's /app/data to /workspace/data before symlink is created
            subprocess.run(["docker", "exec", container_name, "mkdir", "-p", "/workspace/data"],
                          capture_output=True, text=True)
            subprocess.run(
                ["docker", "exec", container_name, "cp", "-r", "/app/data/.", "/workspace/data"],
                capture_output=True, text=True, timeout=60
            )
            # Copy skills from image's /app/skills to /workspace/skills
            subprocess.run(["docker", "exec", container_name, "mkdir", "-p", "/workspace/skills"],
                          capture_output=True, text=True)
            subprocess.run(
                ["docker", "exec", container_name, "cp", "-r", "/app/skills/.", "/workspace/skills"],
                capture_output=True, text=True, timeout=60
            )

        # Dynamically create symlinks based on instruction paths
        self._setup_container_paths(container_name, instruction, mount_point)

        # Harbor Architecture: Agent runs on host, commands via docker exec
        try:
            result = self._execute_nanobot_on_host(
                container_name, task_name, config, instruction, workspace_host,
                max_turns, model_key, transcripts_dir, mount_point
            )
        except Exception as e:
            result = {"task": task_name, "status": "error", "error": str(e)[:500]}
        finally:
            # Clean up container
            self._remove_container(container_name)
            # Clean up image
            try:
                subprocess.run(["docker", "rmi", "-f", task_image],
                              capture_output=True, text=True, timeout=60)
            except Exception:
                pass

        return result

    def _execute_nanobot_on_host(self, container_name: str, task_name: str,
                                      config: dict, instruction: str, workspace_host: Path,
                                      max_turns: int, model_key: str,
                                      transcripts_dir: Path = None,
                                      mount_point: str = "/workspace") -> dict:
        """Harbor Architecture: 在宿主机运行 NanoBotAgent，命令通过 docker exec 在容器内执行。

        工作流程:
        1. NanoBotAgent 在宿主机运行 (使用 Python 3.11)
        2. 文件操作直接在工作空间 (挂载到容器)
        3. 命令执行通过 DockerExecTool 代理到容器内 (docker exec)
        4. pytest 通过 docker exec 在容器内运行
        """
        # Import HarborNanoBotAgent from OpenClawPro
        # Use same path resolution logic as import_nanobot_agent
        import sys
        from pathlib import Path

        openclawpro_path = None
        candidates = [
            os.getenv("OPENCLAWPRO_DIR"),
            str(Path(__file__).parent.parent.parent / "OpenClawPro"),
        ]
        for path_str in candidates:
            if not path_str:
                continue
            p = Path(path_str)
            if (p / "harness" / "agent" / "nanobot.py").exists():
                openclawpro_path = str(p)
                break

        if not openclawpro_path:
            raise ImportError("OpenClawPro not found. Set OPENCLAWPRO_DIR env var.")

        if openclawpro_path not in sys.path:
            sys.path.insert(0, openclawpro_path)

        from harness.agent.nanobot import HarborNanoBotAgent

        prompt = (
            f"Complete this programming task in the workspace {workspace_host}.\n\n"
            f"TASK INSTRUCTIONS:\n{instruction}\n\n"
            f"Use the tools to write files and execute code directly in the workspace. "
            f"All output files must be created at the paths specified in the instructions."
        )

        session_id = f"skills_{task_name}"
        all_transcripts = []
        test_output = ""

        # Create HarborNanoBotAgent on host machine
        # HarborNanoBotAgent uses DockerExecTool to run commands in container via docker exec
        agent = HarborNanoBotAgent(
            container_name=container_name,
            mount_point=mount_point,
            model=config["model"],
            api_url=config["api_url"],
            api_key=config["api_key"],
            workspace=workspace_host,
            timeout=300,
            disable_safety_guard=True,
        )

        for turn in range(max_turns):
            try:
                result = agent.execute(prompt, session_id=f"{session_id}_t{turn}")
            except Exception as e:
                return {"task": task_name, "status": "error", "error": str(e)[:500], "turns": turn + 1}

            # Collect transcript
            if result.transcript:
                all_transcripts.extend(result.transcript)

            # Run pytest inside container via docker exec
            passed, test_output = self._run_pytest_harbor(container_name, workspace_host, mount_point)

            if passed:
                # Save transcript on success
                if transcripts_dir and model_key and all_transcripts:
                    self._save_transcript(model_key, task_name, all_transcripts)
                return {"task": task_name, "status": "passed", "turns": turn + 1}

            # pytest failed → prepare feedback prompt for next turn
            if turn < max_turns - 1:
                workspace_files = _list_workspace_files(workspace_host)
                prompt = (
                    f"The tests FAILED. Fix the code in the workspace.\n\n"
                    f"PYTEST OUTPUT:\n{test_output[-2000:]}\n\n"
                    f"FILES IN WORKSPACE:\n{workspace_files}"
                )

        # Save failed transcript
        if transcripts_dir and model_key and all_transcripts:
            self._save_transcript(model_key, task_name, all_transcripts)
        return {"task": task_name, "status": "failed", "turns": max_turns,
                "test_output": test_output[-1000:]}

    def _run_pytest_harbor(self, container_name: str, workspace_host: Path, mount_point: str = "/workspace") -> tuple:
        """Harbor Architecture: pytest 在容器内通过 docker exec 运行。

        NanoBotAgent 在宿主机运行，但 pytest 必须在容器内执行以验证任务代码。
        容器需要 python3 和 pytest - 由任务的基础镜像提供。
        如果容器没有pytest，则通过pip安装。
        """
        task_name = workspace_host.name
        task_tests_src = self._get_tasks_dir() / task_name / "tests"
        if not task_tests_src.exists():
            return False, "no tests/ directory"

        # Copy test files from workspace (where agent may have modified them) to container
        workspace_tests = workspace_host / "tests"
        subprocess.run(["docker", "exec", container_name, "mkdir", "-p", f"{mount_point}/tests"],
                      capture_output=True, text=True)
        # If agent modified tests in workspace (has actual test files), use those; otherwise use original
        has_test_files = workspace_tests.exists() and any(workspace_tests.glob("test_*.py"))
        test_source = workspace_tests if has_test_files else task_tests_src
        for f in test_source.glob("*"):
            if f.is_file() and f.name != "Dockerfile":
                # Read test file and replace host paths with container paths
                content = f.read_text(encoding="utf-8")
                # Replace host workspace path with container mount point
                content = content.replace(str(workspace_host), mount_point)
                # Also handle common variations
                content = content.replace("/tmp/skillsbench_workspace/", "/workspace/")
                content = content.replace("/private/tmp/skillsbench_workspace/", "/workspace/")
                # Write to temp file and copy
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                subprocess.run(["docker", "cp", tmp_path, f"{container_name}:{mount_point}/tests/{f.name}"],
                              capture_output=True, text=True)
                import os
                os.unlink(tmp_path)

        # Determine which python to use - try python3 first (base image python), then python3.11
        for py_cmd in ["python3", "python3.11"]:
            check = subprocess.run(
                ["docker", "exec", container_name, "which", py_cmd],
                capture_output=True, text=True, timeout=10
            )
            if check.returncode == 0:
                actual_py = py_cmd
                break
        else:
            actual_py = "python3"  # fallback

        # Check if pytest is installed, if not install it
        check_pytest = subprocess.run(
            ["docker", "exec", container_name, actual_py, "-m", "pytest", "--version"],
            capture_output=True, text=True, timeout=30
        )
        if check_pytest.returncode != 0:
            # Install pytest
            log(f"[{task_name}] Installing pytest in container...")
            # Check if pip supports --break-system-packages (PEP 668)
            check_pip = subprocess.run(
                ["docker", "exec", container_name, actual_py, "-m", "pip", "install", "--help"],
                capture_output=True, text=True, timeout=30
            )
            pip_supports_break_system = "--break-system-packages" in check_pip.stdout

            if pip_supports_break_system:
                install_cmd = ["docker", "exec", container_name, actual_py, "-m", "pip", "install", "-q", "--break-system-packages", "pytest"]
            else:
                # For older pip (e.g., Ubuntu 20.04), use --user or install without the flag
                install_cmd = ["docker", "exec", container_name, actual_py, "-m", "pip", "install", "-q", "pytest"]

            install_result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=120)
            if install_result.returncode != 0:
                return False, f"Failed to install pytest: {install_result.stderr[-500:]}"

        # Run pytest inside container via docker exec
        # Set TEST_ROOT env var so tests can find files if modified by agent
        pytest_cmd = [
            "docker", "exec", "-w", mount_point,
            "-e", f"TEST_ROOT={mount_point}",
            container_name,
            actual_py, "-m", "pytest", f"{mount_point}/tests/test_outputs.py", "-v", "--tb=short"
        ]
        try:
            proc = subprocess.run(pytest_cmd, capture_output=True, text=True, timeout=120)
            return proc.returncode == 0, proc.stdout[-1500:] + "\n" + proc.stderr[-500:]
        except subprocess.TimeoutExpired:
            return False, "pytest timeout"
        except Exception as exc:
            return False, f"pytest error: {exc}"

    def collect(self, model_key: str) -> dict | None:
        result_dir = self._find_result_dir("skillsbench")
        if not result_dir:
            return None
        result_f = result_dir / f"{model_key}.json"
        if not result_f.exists():
            return None
        try:
            data = json.loads(result_f.read_text())
            return {"score": data["score"], "passed": data["passed"], "total": data["total"],
                    "pass_rate": data["pass_rate"]}
        except Exception:
            return None
