"""SkillsBench — 56+ 个纯 Python 任务 (无 Docker)，多轮 Agent 模式。

评分方式: LLM 生成代码 → 执行 → pytest 验证 (pass/fail)。
支持多轮迭代: 若 pytest 失败，把错误反馈给 LLM 让它修正，最多 MAX_TURNS 轮。

工作流: 读 instruction.md → 调 LLM 获取代码 → 执行代码 → 若失败则把错误反馈
→ LLM 修正 → 再执行 → 最多 max_turns 轮 → 跑 pytest 验证。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from ..utils.api import call_llm
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
    "azure-bgp-oscillation-route-leak", "syzkaller-ppdev-syzlang",
    # Lean4
    "lean4-proof",
    # Rust
    "multilingual-video-dubbing",
    # FFmpeg/视频
    "dynamic-object-aware-egomotion", "mario-coin-counting", "pedestrian-traffic-counting",
    "pg-essay-to-audiobook", "video-filler-word-remover", "video-silence-remover", "video-tutorial-indexer",
    # Node.js
    "data-to-d3", "fix-visual-stability", "react-performance-debugging",
    "scheduling-email-assistant", "threejs-structure-parser", "threejs-to-obj",
    # Graphviz/特殊工具
    "dialogue-parser", "software-dependency-audit",
    # GPU/JAX
    "jax-computing-basics",
    # 大量数据/特殊API
    "enterprise-information-search", "gh-repo-analytics",
}


def _call_llm_multi(messages: list, config: dict, max_tokens: int = 8192, timeout: float = 180) -> str:
    """调用 LLM 多轮对话接口，支持重试。底层复用 utils/api.call_llm。"""
    return call_llm(messages, config, max_tokens=max_tokens, timeout=timeout)


def _extract_files(response: str) -> dict:
    """从 LLM 响应中提取文件内容，返回 {文件名: 内容}。

    支持三种格式:
    1. ```language\\n# filename\\ncontent```
    2. ### filename.py\\n```\\ncontent```
    3. File: filename.py\\n```\\ncontent```
    """
    files = {}
    ext_pat = r"(?:py|json|txt|csv|md|sh|yaml|yml|toml|cfg|ini|xml|html|css|js|ts|sql|r|R|jl|m|ipynb)"

    # 模式1: ```language\n# filename\ncontent```
    blocks = re.findall(r"```(?:\w*)\s*\n(.*?)```", response, re.DOTALL)
    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        first = lines[0].strip()
        fname = None
        for prefix in ["# ", "// ", "-- ", "<!-- ", "% "]:
            if first.startswith(prefix):
                candidate = first[len(prefix):].strip()
                if re.match(r"^[\w/.-]+\.\w+$", candidate):
                    fname = candidate
                    break
        if fname:
            files[fname] = "\n".join(lines[1:])

    # 模式2: 标题+代码块
    pattern = rf"(?:###?\s+|[*]{{2}})([^\n*]+\.{ext_pat})[*]{{0,2}}\s*\n```(?:\w*)\s*\n(.*?)```"
    for m in re.finditer(pattern, response, re.DOTALL):
        fname = m.group(1).strip().strip("`")
        files[fname] = m.group(2).strip()

    # 模式3: File: filename\n```\ncontent```
    pattern2 = rf"(?:File|Output|Create):\s*`?([^\n`]+\.{ext_pat})`?\s*\n```(?:\w*)\s*\n(.*?)```"
    for m in re.finditer(pattern2, response, re.DOTALL | re.IGNORECASE):
        fname = m.group(1).strip()
        files[fname] = m.group(2).strip()

    return files


def _write_files(files: dict, workspace: Path):
    """把提取的文件写入 workspace，处理 /root/ 前缀。"""
    for fname, content in files.items():
        clean_name = fname.lstrip("/")
        if clean_name.startswith("root/"):
            clean_name = clean_name[5:]
        target = workspace / clean_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + "\n", encoding="utf-8")


def _execute_scripts(workspace: Path, files: dict) -> str:
    """执行 workspace 中的 Python 脚本，返回执行结果摘要。

    先安装 requirements.txt（如果有），再执行 LLM 产出的 .py 文件，
    收集所有 stdout/stderr 结果。
    """
    outputs = []
    env = {**os.environ, "HOME": str(workspace)}

    req_file = workspace / "requirements.txt"
    if req_file.exists():
        try:
            proc = subprocess.run(
                ["python3", "-m", "pip", "install", "-q", "-r", str(req_file)],
                capture_output=True, text=True, timeout=120, env=env,
            )
            if proc.returncode != 0:
                outputs.append(f"[pip install failed] {proc.stderr[-300:]}")
        except Exception:
            pass

    py_scripts = [f for f in files.keys() if f.endswith(".py") and "test" not in f.lower()]
    if not py_scripts:
        py_scripts = [f.name for f in workspace.glob("*.py") if "test" not in f.name.lower()]

    for script in py_scripts:
        script_path = workspace / script
        if not script_path.exists():
            continue
        try:
            proc = subprocess.run(
                ["python3", str(script_path)], cwd=workspace,
                capture_output=True, text=True, timeout=120, env=env,
            )
            if proc.returncode != 0:
                outputs.append(f"[{script} FAILED (rc={proc.returncode})]\nstdout: {proc.stdout[-500:]}\nstderr: {proc.stderr[-500:]}")
            else:
                outputs.append(f"[{script} OK]\nstdout: {proc.stdout[-300:]}")
        except subprocess.TimeoutExpired:
            outputs.append(f"[{script} TIMEOUT after 120s]")
        except Exception as exc:
            outputs.append(f"[{script} ERROR: {exc}]")

    return "\n".join(outputs)


def _run_pytest(workspace: Path, task_dir: Path) -> tuple:
    """运行 pytest 验证，返回 (passed: bool, output: str)。"""
    test_py = task_dir / "tests" / "test_outputs.py"
    if not test_py.exists():
        return False, "no test_outputs.py"

    tests_workspace = workspace / "tests"
    tests_workspace.mkdir(exist_ok=True)
    test_content = test_py.read_text(encoding="utf-8")
    test_content = test_content.replace("/root/", f"{workspace}/")
    test_content = test_content.replace("'/root'", f"'{workspace}'")
    test_content = test_content.replace('"/root"', f'"{workspace}"')
    (tests_workspace / "test_outputs.py").write_text(test_content, encoding="utf-8")

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

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
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
        task_names = [t for t in all_tasks if t not in SKIP_TASKS]

        if sample and sample < len(task_names):
            import random
            random.seed(42)
            task_names = random.sample(task_names, sample)

        workspace_base = Path("/tmp/skillsbench_workspace")
        results = []
        passed = 0

        for i, task_name in enumerate(task_names):
            start = time.time()
            result = self._run_single_task(task_name, config, tasks_dir, workspace_base, max_turns)
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
                         workspace_base: Path, max_turns: int = 3) -> dict:
        """运行单个 SkillsBench 任务 (多轮 agent 模式)。

        流程: 读 instruction.md → 列出 environment/ 文件 → 发送给 LLM →
        提取文件 → 写入 workspace → 执行 → pytest → 失败则反馈修正
        """
        task_dir = tasks_dir / task_name
        instruction = (task_dir / "instruction.md").read_text(encoding="utf-8")

        workspace = workspace_base / task_name
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)

        # 复制 environment/ 下的文件
        env_dir = task_dir / "environment"
        input_files_info = []
        if env_dir.exists():
            for f in env_dir.rglob("*"):
                if f.is_file() and f.name != "Dockerfile":
                    rel = f.relative_to(env_dir)
                    dst = workspace / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)
                    size = f.stat().st_size
                    input_files_info.append(f"  {rel} ({size} bytes)")
                    if size < 5000 and f.suffix in ('.txt', '.csv', '.json', '.yaml', '.yml', '.md', '.py', '.cfg', '.ini', '.toml'):
                        try:
                            content = f.read_text(encoding="utf-8")
                            input_files_info.append(f"    Content:\n{content[:2000]}")
                        except Exception:
                            pass

        input_files_str = "\n".join(input_files_info) if input_files_info else "  (no input files)"

        system_msg = """You are an expert programmer solving a coding task in an iterative environment.

RULES:
- The working directory is /root/ (I will execute your code there)
- Write ALL files needed to produce the required outputs
- For each file, format as: ### filename.py\n```python\n<complete code>\n```
- Install any needed pip packages by including: ### requirements.txt\n```\npackage1\npackage2\n```
- Your code will be EXECUTED. Make sure it runs correctly with real data.
- If I show you errors, fix them and provide the COMPLETE corrected files (not just the diff)."""

        user_msg = f"""Solve this programming task.

TASK INSTRUCTIONS:
{instruction}

INPUT FILES in /root/:
{input_files_str}

Write the complete solution. All output files must be created by your code at the paths specified in the instructions."""

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        all_files = {}

        for turn in range(max_turns):
            response = _call_llm_multi(messages, config, max_tokens=4096)
            if response.startswith("ERROR:"):
                return {"task": task_name, "status": "error", "error": response, "turns": turn + 1}

            messages.append({"role": "assistant", "content": response})

            files = _extract_files(response)
            if not files:
                code_blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", response, re.DOTALL)
                if code_blocks:
                    main_code = max(code_blocks, key=len)
                    files["solution.py"] = main_code.strip()
                json_blocks = re.findall(r"```(?:json)?\s*\n(\{.*?\})```", response, re.DOTALL)
                for jb in json_blocks:
                    for guess in ["answer.json", "output.json", "result.json", "results.json"]:
                        if guess in instruction.lower():
                            files[guess] = jb.strip()
                            break

            all_files.update(files)
            _write_files(files, workspace)

            exec_output = _execute_scripts(workspace, files)
            passed, test_output = _run_pytest(workspace, task_dir)

            if passed:
                return {"task": task_name, "status": "passed", "turns": turn + 1,
                        "files_written": list(all_files.keys())}

            if turn < max_turns - 1:
                workspace_files = _list_workspace_files(workspace)
                feedback = f"""Your code was executed but the tests FAILED. Here's what happened:

EXECUTION OUTPUT:
{exec_output[-2000:] if exec_output else "(no script output)"}

PYTEST OUTPUT:
{test_output[-2000:]}

FILES IN WORKSPACE:
{workspace_files}

Please fix the issues and provide the COMPLETE corrected files."""
                messages.append({"role": "user", "content": feedback})

        return {"task": task_name, "status": "failed", "turns": max_turns,
                "stdout": test_output[-1000:], "exec_output": exec_output[-500:],
                "files_written": list(all_files.keys())}

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
