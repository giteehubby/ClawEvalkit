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
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    # Container work directory (fixed, no mount point needed)
    # Uses docker cp instead of volume mounts for file transfer
    CONTAINER_WORK_DIR = "/work"

    def __init__(self, use_docker: bool = True, reuse_container: bool = False, **kwargs):
        self.use_docker = use_docker
        self.reuse_container = reuse_container
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
                 transcripts_dir: Path = None, parallel: int = 1, **kwargs) -> dict:
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
            return self._evaluate_docker(model_key, config, sample, transcripts_dir, parallel=parallel, **kwargs)

        tasks_dir = self._get_tasks_dir()
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        max_turns = kwargs.get("max_turns", 3)
        force = kwargs.get("force", False)
        all_tasks = sorted([d.name for d in tasks_dir.iterdir() if d.is_dir()])
        # 根据 use_docker 决定跳过哪些任务
        if self.use_docker:
            # 使用 Docker：跳过需要特殊依赖的任务
            skip_set = SKIP_TASKS
        else:
            # 不使用 Docker：跳过 Docker 专用任务，但保留依赖容易解决的任务
            skip_set = SKIP_TASKS - EASY_SKIP_TASKS
        all_task_names = [t for t in all_tasks if t not in skip_set]  # 所有有效任务，用于汇总

        # Support task_ids filter from --task argument
        task_ids = kwargs.get("task_ids")
        if task_ids:
            all_task_names = [t for t in all_task_names if t in task_ids]
            if not all_task_names:
                return {"score": 0, "total": 0, "error": f"no tasks match task_ids: {task_ids}"}

        # 先基于已有缓存生成初始汇总（sample 前，反映所有任务的进度）
        self._build_and_save_summary(model_key, all_task_names, max_turns=max_turns)

        task_names = all_task_names  # 复制用于后续过滤

        # Pre-filter tasks that already have cached results (unless force=True)
        if not force:
            uncached_tasks = []
            for t in task_names:
                task_result_dir = self.results_dir / "skillsbench" / model_key / t
                dedup_file = task_result_dir / "result.json"
                if not dedup_file.exists():
                    uncached_tasks.append(t)
                else:
                    try:
                        cached = json.loads(dedup_file.read_text())
                        if cached.get("status") not in ("passed", "failed"):
                            uncached_tasks.append(t)  # Incomplete result, re-run
                    except Exception:
                        uncached_tasks.append(t)  # Corrupted result, re-run
            log(f"[skillsbench] {len(task_names) - len(uncached_tasks)} tasks already cached, {len(uncached_tasks)} remaining")
            task_names = uncached_tasks

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
            # 每个任务完成后更新汇总（基于所有任务）
            self._build_and_save_summary(model_key, all_task_names, new_results=results, max_turns=max_turns)

        # 最终汇总也基于所有任务（会覆盖中间结果）
        self._build_and_save_summary(model_key, all_task_names, new_results=results, max_turns=max_turns)
        return self._load_summary(model_key)

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

    def _save_transcript(self, model_key: str, task_name: str, transcript: list, turn: int = None):
        """保存 agent 轨迹到文件（统一结构）。

        保存到: outputs/skillsbench/transcripts/{model}/{task}/transcript.json
        如果指定 turn，则额外保存到: outputs/skillsbench/transcripts/{model}/{task}/transcript_turn_{turn}.json
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
            # Save main transcript
            (trans_path / "transcript.json").write_text(
                json.dumps(normalized, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            # Save turn-specific transcript for debugging
            if turn is not None:
                (trans_path / f"transcript_turn_{turn}.json").write_text(
                    json.dumps(normalized, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                log(f"[{task_name}] Saved transcript (turn {turn}) to {trans_path / f'transcript_turn_{turn}.json'}")
            else:
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

    def _load_summary(self, model_key: str) -> dict:
        """读取已保存的汇总文件。"""
        result_f = self.results_dir / "skillsbench" / f"{model_key}.json"
        if result_f.exists():
            try:
                return json.loads(result_f.read_text())
            except Exception:
                pass
        return {"model": model_key, "total": 0, "passed": 0, "score": 0}

    def _build_and_save_summary(self, model_key: str, task_names: list,
                                new_results: list = None, max_turns: int = 3):
        """从 per-task 缓存 + 新结果构建汇总并保存。

        在运行开始时和每个任务完成后调用，确保中断后也能保留最新进度。
        """
        results = list(new_results) if new_results else []

        # 收集已有缓存（排除 new_results 中已有的）
        new_task_names = {r.get("task") for r in results}
        for t in task_names:
            if t in new_task_names:
                continue
            f = self.results_dir / "skillsbench" / model_key / t / "result.json"
            if f.exists():
                try:
                    cached = json.loads(f.read_text())
                    cached["_from_cache"] = True
                    results.append(cached)
                except Exception:
                    pass

        passed = sum(1 for r in results if r.get("status") == "passed")
        total = len(task_names)
        scored = len(results)
        score = round(passed / total * 100, 1) if total else 0
        summary = {
            "model": model_key, "total": total, "passed": passed,
            "failed": scored - passed, "pending": total - scored,
            "score": score,
            "pass_rate": f"{passed}/{total}", "max_turns": max_turns,
            "skipped_docker": len(SKIP_TASKS_DOCKER), "results": results,
        }
        self.save_result("skillsbench", model_key, summary)
        log(f"[skillsbench] 汇总已保存: {passed}/{total} passed, {total - scored} pending")

    def _remove_container(self, container_name: str):
        """清理 Docker 容器（如果存在）。"""
        try:
            subprocess.run(["docker", "rm", "-f", container_name],
                          capture_output=True, text=True, timeout=30)
        except Exception:
            pass

    def _evaluate_docker(self, model_key: str, config: dict, sample: int = 0,
                         transcripts_dir: Path = None, parallel: int = 1, **kwargs) -> dict:
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
        force = kwargs.get("force", False)
        all_tasks = sorted([d.name for d in tasks_dir.iterdir() if d.is_dir()])
        # Docker 模式下跳过 SKIP_TASKS_DOCKER，但不再跳过 SKIP_TASKS（Docker 可以处理）
        all_task_names = [t for t in all_tasks if t not in SKIP_TASKS_DOCKER]  # 所有有效任务，用于汇总

        # Support task_ids filter from --task argument
        task_ids = kwargs.get("task_ids")
        if task_ids:
            all_task_names = [t for t in all_task_names if t in task_ids]
            if not all_task_names:
                return {"score": 0, "total": 0, "error": f"no tasks match task_ids: {task_ids}"}

        # 先基于已有缓存生成初始汇总（sample 前，反映所有任务的进度）
        self._build_and_save_summary(model_key, all_task_names, max_turns=max_turns)

        task_names = all_task_names  # 复制用于后续过滤

        # Pre-filter tasks that already have cached results (unless force=True)
        if not force:
            uncached_tasks = []
            for t in task_names:
                task_result_dir = self.results_dir / "skillsbench" / model_key / t
                dedup_file = task_result_dir / "result.json"
                if not dedup_file.exists():
                    uncached_tasks.append(t)
                else:
                    try:
                        cached = json.loads(dedup_file.read_text())
                        if cached.get("status") not in ("passed", "failed"):
                            uncached_tasks.append(t)  # Incomplete result, re-run
                    except Exception:
                        uncached_tasks.append(t)  # Corrupted result, re-run
            log(f"[skillsbench] {len(task_names) - len(uncached_tasks)} tasks already cached, {len(uncached_tasks)} remaining")
            task_names = uncached_tasks

        if sample and sample < len(task_names):
            random.seed(42)
            task_names = random.sample(task_names, sample)

        results = []
        passed = 0

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        # Resolve proxy: prefer INNER vars, fallback to standard proxy vars
        raw_proxy_http = (
            os.environ.get('HTTP_PROXY_INNER', '')
            or os.environ.get('HTTP_PROXY', '')
            or os.environ.get('http_proxy', '')
        )
        raw_proxy_https = (
            os.environ.get('HTTPS_PROXY_INNER', '')
            or os.environ.get('HTTPS_PROXY', '')
            or os.environ.get('https_proxy', '')
        )
        # Docker build runs on host → use original proxy (127.0.0.1 works)
        build_proxy_http = raw_proxy_http
        build_proxy_https = raw_proxy_https
        # Docker run inside container → convert to host.docker.internal
        run_proxy_http = raw_proxy_http
        run_proxy_https = raw_proxy_https
        for old in ('127.0.0.1', 'localhost'):
            if run_proxy_http and old in run_proxy_http:
                run_proxy_http = run_proxy_http.replace(old, 'host.docker.internal')
            if run_proxy_https and old in run_proxy_https:
                run_proxy_https = run_proxy_https.replace(old, 'host.docker.internal')

        def run_single_task(task_name: str) -> dict:
            """运行单个任务: 缓存检查 → _run_single_task_docker → 保存结果。"""
            # Per-task deduplication: check for existing result before running (skip if force=True)
            if not force:
                task_result_dir = self.results_dir / "skillsbench" / model_key / task_name
                dedup_file = task_result_dir / "result.json"
                if dedup_file.exists():
                    try:
                        cached = json.loads(dedup_file.read_text())
                        if cached.get("status") in ("passed", "failed"):
                            log(f"[{task_name}] Found cached result, skipping")
                            cached["_from_cache"] = True
                            return cached
                    except Exception:
                        pass
            else:
                log(f"[{task_name}] Force mode: ignoring cached result")

            start = time.time()
            result = self._run_single_task_docker(
                task_name, config, tasks_dir, max_turns,
                openclawpro_dir, openrouter_api_key, run_proxy_http, run_proxy_https,
                build_proxy_http=build_proxy_http, build_proxy_https=build_proxy_https,
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

            return result

        if parallel > 1:
            log(f"[skillsbench] Running {len(task_names)} tasks with parallel={parallel}")
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                future_to_task = {
                    executor.submit(run_single_task, t): t for t in task_names
                }
                for future in as_completed(future_to_task):
                    task_name = future_to_task[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        log(f"[{task_name}] Thread error: {exc}")
                        result = {"task": task_name, "status": "error", "error": str(exc)[:500]}
                    if result.get("status") == "passed":
                        passed += 1
                    results.append(result)
                    # 每个任务完成后更新汇总（基于所有任务）
                    self._build_and_save_summary(model_key, all_task_names, new_results=results, max_turns=max_turns)
        else:
            for i, task_name in enumerate(task_names):
                result = run_single_task(task_name)
                if result.get("status") == "passed":
                    passed += 1
                results.append(result)
                # 每个任务完成后更新汇总（基于所有任务）
                self._build_and_save_summary(model_key, all_task_names, new_results=results, max_turns=max_turns)

        # 最终汇总也基于所有任务（会覆盖中间结果）
        self._build_and_save_summary(model_key, all_task_names, new_results=results, max_turns=max_turns)
        return self._load_summary(model_key)

    def _run_single_task_docker(self, task_name: str, config: dict, tasks_dir: Path,
                                 max_turns: int, openclawpro_dir: Path,
                                 openrouter_api_key: str, proxy_http: str, proxy_https: str,
                                 build_proxy_http: str = "", build_proxy_https: str = "",
                                 transcripts_dir: Path = None, model_key: str = None) -> dict:
        """在 per-task Docker 容器内运行单个 SkillsBench 任务 (使用 docker cp, 无需挂载点)。

        简化流程:
        1. 构建镜像
        2. 创建宿主机工作空间
        3. 复制环境文件到工作空间
        4. 启动容器 (无挂载)
        5. 通过 docker cp 复制文件到容器
        6. 运行 agent (HarborNanoBotAgent)
        7. 通过 docker cp 复制结果回宿主机
        8. 清理容器
        """
        task_dir = tasks_dir / task_name
        instruction = (task_dir / "instruction.md").read_text(encoding="utf-8")
        env_dockerfile = task_dir / "environment" / "Dockerfile"

        if not env_dockerfile.exists():
            return {"task": task_name, "status": "skipped", "error": "no Dockerfile"}

        # Build per-task Docker image
        task_image = f"skillsbench-task-{task_name}:latest"
        container_name = f"sb-{task_name}"

        # Check if container already exists AND is running (reuse mode)
        container_exists = False
        if self.reuse_container:
            check_proc = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
                capture_output=True, text=True
            )
            if container_name in check_proc.stdout:
                # Check if container is actually running
                running_proc = subprocess.run(
                    ["docker", "ps", "--filter", f"name={container_name}", "--filter", "status=running", "--format", "{{.Names}}"],
                    capture_output=True, text=True
                )
                if container_name in running_proc.stdout:
                    container_exists = True
                    log(f"[{task_name}] ♻️  Reusing existing container")
                else:
                    # Container exists but stopped — restart it
                    log(f"[{task_name}] ♻️  Restarting stopped container")
                    subprocess.run(
                        ["docker", "start", container_name],
                        capture_output=True, text=True, timeout=60
                    )
                    container_exists = True

        # Build image if not in reuse mode or container doesn't exist
        if not container_exists:
            log(f"[{task_name}] 🔨 Building image...")
            # Use build_proxy (host proxy) for docker build
            bp_http = build_proxy_http or proxy_http
            bp_https = build_proxy_https or proxy_https
            build_cmd = ["docker", "build", "-t", task_image, "-f", str(env_dockerfile)]
            if bp_http:
                build_cmd += ["--build-arg", f"http_proxy={bp_http}",
                              "--build-arg", f"https_proxy={bp_https}"]
            build_cmd.append(str(task_dir / "environment"))

            try:
                build_proc = subprocess.run(build_cmd, capture_output=True, text=True, timeout=1800)
                if build_proc.returncode != 0:
                    return {"task": task_name, "status": "skipped",
                            "error": f"docker build failed: {build_proc.stderr[:500]}"}
            except subprocess.TimeoutExpired:
                return {"task": task_name, "status": "skipped", "error": "docker build timeout"}
            except Exception as e:
                return {"task": task_name, "status": "skipped", "error": str(e)}

        # Create host workspace
        workspace_host = Path(f"/tmp/skillsbench_workspace/{task_name}")
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

        # Copy solution files to workspace (needed by pytest for ground_truth etc.)
        solution_dir = task_dir / "solution"
        if solution_dir.exists():
            for f in solution_dir.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(solution_dir.parent)
                    dst = workspace_host / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)

        # Start container (no mounts!)
        if not container_exists:
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
                run_proc = subprocess.run(docker_run_cmd, capture_output=True, text=True, timeout=60)
                if run_proc.returncode != 0:
                    return {"task": task_name, "status": "error",
                            "error": f"container start failed: {run_proc.stderr[:500]}"}
            except subprocess.TimeoutExpired:
                return {"task": task_name, "status": "error", "error": "container start timeout"}
            except Exception as e:
                return {"task": task_name, "status": "error", "error": str(e)}

        # Copy files to container via docker cp
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
        try:
            result = self._run_agent_in_container(
                container_name, task_name, config, instruction, workspace_host,
                max_turns, model_key, transcripts_dir, tasks_dir
            )
        except Exception as e:
            result = {"task": task_name, "status": "error", "error": str(e)[:500]}
        finally:
            # Copy results back
            log(f"[{task_name}] 📥 Copying results back...")
            subprocess.run(
                ["docker", "cp", f"{container_name}:{self.CONTAINER_WORK_DIR}/output/", str(workspace_host)],
                capture_output=True, text=True, timeout=30
            )
            # Cleanup container and image (skip if reuse_container=True)
            if not self.reuse_container:
                self._remove_container(container_name)
                # Clean up image
                try:
                    subprocess.run(["docker", "rmi", "-f", task_image],
                                  capture_output=True, text=True, timeout=60)
                except Exception:
                    pass

        return result

    def _run_agent_in_container(self, container_name: str, task_name: str,
                                 config: dict, instruction: str, workspace_host: Path,
                                 max_turns: int, model_key: str,
                                 transcripts_dir: Path = None,
                                 tasks_dir: Path = None) -> dict:
        """在容器内运行 NanoBotAgent (通过 docker cp 传输文件, 无需挂载点).

        工作流程:
        1. 使用 HarborNanoBotAgent 在宿主机运行
        2. 文件通过 docker cp 复制到容器
        3. 命令通过 DockerExecTool (docker exec) 在容器内执行
        4. pytest 通过 docker exec 在容器内运行
        """
        import sys

        # Import HarborNanoBotAgent from OpenClawPro
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

        # Modify instruction to use container work dir path
        modified_instruction = instruction.replace("/root/", f"{self.CONTAINER_WORK_DIR}/")
        modified_instruction = modified_instruction.replace("/workspace/", f"{self.CONTAINER_WORK_DIR}/")

        prompt = (
            f"Complete this programming task in the workspace {self.CONTAINER_WORK_DIR}.\n\n"
            f"TASK INSTRUCTIONS:\n{modified_instruction}\n\n"
            f"Use the tools to write files and execute code directly in the workspace. "
            f"All output files must be created at the paths specified in the instructions."
        )

        session_id = f"skills_{task_name}"
        all_transcripts = []
        test_output = ""

        # Create HarborNanoBotAgent on host machine
        agent = HarborNanoBotAgent(
            container_name=container_name,
            mount_point=self.CONTAINER_WORK_DIR,
            model=config["model"],
            api_url=config["api_url"],
            api_key=config["api_key"],
            workspace=workspace_host,
            timeout=300,
            disable_safety_guard=True,
        )

        log(f"[{task_name}] 🤖 Running agent (max {max_turns} turns)...")

        for turn in range(max_turns):
            log(f"[{task_name}] 🔄 Agent turn {turn + 1}/{max_turns}")
            try:
                result = agent.execute(prompt, session_id=f"{session_id}_t{turn}")
            except Exception as e:
                return {"task": task_name, "status": "error", "error": str(e)[:500], "turns": turn + 1}

            # Collect transcript
            if result.transcript:
                all_transcripts.extend(result.transcript)

            # Save transcript after each turn for debugging
            if transcripts_dir and model_key and all_transcripts:
                self._save_transcript(model_key, task_name, all_transcripts, turn=turn + 1)

            # Run pytest inside container via docker exec
            log(f"[{task_name}] 🧪 Running pytest...")
            passed, test_output = self._run_pytest_in_container(container_name, workspace_host, tasks_dir)
            log(f"[{task_name}] 🧪 Pytest output: {test_output[:500]}...")

            if passed:
                log(f"[{task_name}] ✅ Pytest passed!")
                if transcripts_dir and model_key and all_transcripts:
                    self._save_transcript(model_key, task_name, all_transcripts)
                return {"task": task_name, "status": "passed", "turns": turn + 1}

            # pytest failed → prepare feedback prompt for next turn
            log(f"[{task_name}] ❌ Pytest failed, preparing feedback...")
            if turn < max_turns - 1:
                prompt = (
                    f"The tests FAILED. Fix the code in the workspace {self.CONTAINER_WORK_DIR}.\n\n"
                    f"PYTEST OUTPUT:\n{test_output[-2000:]}\n\n"
                    f"Fix the code and ensure all output files are created at the correct paths."
                )

        # Save failed transcript
        if transcripts_dir and model_key and all_transcripts:
            self._save_transcript(model_key, task_name, all_transcripts)
        return {"task": task_name, "status": "failed", "turns": max_turns,
                "test_output": test_output[-1000:]}

    def _run_pytest_in_container(self, container_name: str, workspace_host: Path, tasks_dir: Path = None) -> tuple:
        """在容器内运行 pytest (通过 docker cp 传输文件, 无需挂载点).

        NanoBotAgent 在宿主机运行，但 pytest 必须在容器内执行以验证任务代码。
        """
        task_name = workspace_host.name
        if tasks_dir is None:
            tasks_dir = self._get_tasks_dir()
        task_tests_src = tasks_dir / task_name / "tests"
        if not task_tests_src.exists():
            return False, "no tests/ directory"

        # Copy test files to container
        subprocess.run(
            ["docker", "exec", container_name, "mkdir", "-p", f"{self.CONTAINER_WORK_DIR}/tests"],
            capture_output=True, text=True
        )

        for f in task_tests_src.glob("*"):
            if f.is_file() and f.name != "Dockerfile":
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
            ["docker", "exec", container_name, "pip3", "install", "--break-system-packages", "-q",
             "pytest", "pytesseract", "pypdf", "PyMuPDF"],
            capture_output=True, text=True, timeout=120
        )

        result = subprocess.run(
            ["docker", "exec", "-w", self.CONTAINER_WORK_DIR, container_name,
             "python3", "-m", "pytest", f"{self.CONTAINER_WORK_DIR}/tests", "-v", "--tb=short"],
            capture_output=True, text=True, timeout=120
        )

        return result.returncode == 0, result.stdout[-1500:] + "\n" + result.stderr[-500:]

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
