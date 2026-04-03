"""SkillsBench — 56+ 个纯 Python 任务 (无 Docker)，多轮 Agent 模式。

评分方式: NanoBotAgent 在 workspace 中自主编写代码 → pytest 验证 (pass/fail)。
支持多轮迭代: 若 pytest 失败，把错误反馈给 NanoBotAgent 让它修正，最多 MAX_TURNS 轮。

工作流: 读 instruction.md → NanoBotAgent 在 workspace 中写文件/执行代码 →
跑 pytest 验证 → 失败则反馈修正 → 最多 max_turns 轮。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from ..utils.nanobot import import_nanobot_agent
from .base import BaseBenchmark

# 需要 Docker 或特殊系统依赖的任务（跳过）
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
        """
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

        if sample and sample < len(task_names):
            import random
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
                    self._save_transcript(transcripts_dir, model_key, task_name, all_transcripts)
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
            self._save_transcript(transcripts_dir, model_key, task_name, all_transcripts)
        return {"task": task_name, "status": "failed", "turns": max_turns,
                "test_output": test_output[-1000:]}

    def _save_transcript(self, transcripts_dir: Path, model_key: str, task_name: str,
                         transcript: list):
        """保存 agent 轨迹到文件。"""
        try:
            trans_path = Path(transcripts_dir) / "skillsbench" / model_key
            trans_path.mkdir(parents=True, exist_ok=True)
            normalized = []
            for e in transcript:
                if isinstance(e, dict) and "message" in e:
                    normalized.append(e["message"])
                else:
                    normalized.append(e)
            (trans_path / f"{task_name}_transcript.json").write_text(
                json.dumps(normalized, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
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
