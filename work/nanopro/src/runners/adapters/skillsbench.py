"""
SkillsBench 适配器。

使用统一的 Agent 接口来运行 SkillsBench 任务。
基于 NanoBot 执行任务，复用 SkillsBench 的测试验证逻辑。
支持并行执行。
"""

import json
import logging
import os
import re
import shutil
import statistics
import subprocess
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

from src.harness.agent.base import AgentResult, BaseAgent

logger = logging.getLogger("adapter.skillsbench")


class Task:
    """任务对象"""

    def __init__(
        self,
        task_id: str,
        name: str,
        instruction: str,
        difficulty: str,
        category: str,
        tags: List[str],
        timeout: int,
        expected_outputs: List[str],
        task_dir: Path,
    ):
        self.task_id = task_id
        self.name = name
        self.instruction = instruction
        self.difficulty = difficulty
        self.category = category
        self.tags = tags
        self.timeout = timeout
        self.expected_outputs = expected_outputs
        self.task_dir = task_dir


class TaskLoader:
    """任务加载器"""

    def __init__(self, tasks_dir: Path):
        self.tasks_dir = tasks_dir

    def load_all_tasks(self, difficulty: str | None = None, category: str | None = None) -> List[Task]:
        """加载所有任务

        Args:
            difficulty: 可选，筛选特定难度 (easy/medium/hard)
            category: 可选，筛选特定类别
        """
        tasks = []

        for task_dir in sorted(self.tasks_dir.iterdir()):
            if not task_dir.is_dir():
                continue

            task = self._load_task(task_dir)
            if not task:
                continue

            # 难度筛选
            if difficulty:
                if difficulty == "fast":
                    if task.difficulty not in ["easy", "medium"]:
                        continue
                elif task.difficulty != difficulty:
                    continue

            # 类别筛选
            if category and task.category.lower() != category.lower():
                continue

            tasks.append(task)

        return tasks

    def _load_task(self, task_dir: Path) -> Optional[Task]:
        """加载单个任务"""
        task_file = task_dir / "task.toml"
        instruction_file = task_dir / "instruction.md"

        if not task_file.exists():
            return None

        # 解析 task.toml
        try:
            content = task_file.read_text(encoding="utf-8")
            data = self._parse_toml(content)
        except Exception as e:
            logger.warning(f"Failed to load task {task_dir}: {e}")
            return None

        if not data:
            return None

        metadata = data.get("metadata", {})
        verifier = data.get("verifier", {})
        agent_config = data.get("agent", {})

        # 读取 instruction.md
        instruction = ""
        if instruction_file.exists():
            instruction = instruction_file.read_text(encoding="utf-8")

        # 提取期望输出（从 instruction 中解析）
        expected_outputs = self._extract_expected_outputs(instruction)

        return Task(
            task_id=task_dir.name,
            name=metadata.get("author_name", task_dir.name),
            instruction=instruction,
            difficulty=metadata.get("difficulty", "medium"),
            category=metadata.get("category", "general"),
            tags=metadata.get("tags", []),
            timeout=int(float(agent_config.get("timeout_sec", 1800))),
            expected_outputs=expected_outputs,
            task_dir=task_dir,
        )

    def _parse_toml(self, content: str) -> Dict:
        """简单 TOML 解析"""
        result = {"metadata": {}, "verifier": {}, "agent": {}, "environment": {}}
        current_section = None

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # 移除行内注释
            if "#" in line and not line.strip().startswith("#"):
                line = line.split("#")[0]

            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                if current_section not in result:
                    result[current_section] = {}
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if current_section:
                    result[current_section][key] = value
                else:
                    result[key] = value

        return result

    def _extract_expected_outputs(self, instruction: str) -> List[str]:
        """从 instruction 中提取期望输出文件"""
        outputs = []

        # 匹配 /root/output/... 格式
        for match in re.findall(r'/root/[a-zA-Z0-9_/.-]+', instruction):
            if match.startswith("/root/output/") or match.startswith("/root/"):
                outputs.append(match)

        # 去重
        return list(set(outputs))

class ScoreResult:
    """评分结果"""

    def __init__(
        self,
        task_id: str,
        score: float = 0.0,
        max_score: float = 100.0,
        passed: bool = False,
        breakdown: Dict | None = None,
        notes: str = "",
    ):
        self.task_id = task_id
        self.score = score
        self.max_score = max_score
        self.passed = passed
        self.breakdown = breakdown or {}
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "score": self.score,
            "max_score": self.max_score,
            "passed": self.passed,
            "breakdown": self.breakdown,
            "notes": self.notes,
        }


def _download_wget_files(env_dir: Path, workspace: Path) -> None:
    """解析 Dockerfile 并下载 wget/curl 下载的文件（不使用 Docker 时）"""
    dockerfile = env_dir / "Dockerfile"
    if not dockerfile.exists():
        return

    content = dockerfile.read_text()
    import re

    # 匹配 wget -O /path URL 或 curl -L -o /path URL
    # wget -O /root/xxx https://...
    wget_pattern = re.compile(r'(?:wget|curl).*?\s+-O\s+(\S+)\s+(https?://\S+)', re.MULTILINE)
    for match in wget_pattern.finditer(content):
        dest_path = match.group(1)
        url = match.group(2)
        # 跳过安装脚本（不下载到 /usr, /tmp/uv 等）
        if any(x in dest_path for x in ['/usr/', '/tmp/uv', '/tmp/elan', '/opt/', '/home/']):
            continue
        # 解析目标路径相对于 /root/ 或 /app/
        if dest_path.startswith('/root/'):
            rel = dest_path[6:]  # 去掉 /root/
            local_path = workspace / "root" / rel
        elif dest_path.startswith('/app/'):
            rel = dest_path[5:]  # 去掉 /app/
            local_path = workspace / "app" / rel
        else:
            continue
        # 如果文件不存在，下载它
        if not local_path.exists():
            local_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                import urllib.request
                print(f"  Downloading {url} -> {local_path}")
                urllib.request.urlretrieve(url, local_path)
            except Exception as e:
                print(f"  Failed to download {url}: {e}")


def run_pytest_verification(task: Task, workspace: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """使用 pytest 运行任务的测试验证

    Args:
        task: 任务对象
        workspace: 工作空间路径
        output_dir: 测试输出目录

    Returns:
        dict: 包含 passed, score, details 的字典
    """
    tests_dir = workspace / "tests"
    if not tests_dir.exists():
        return {"passed": False, "score": 0.0, "details": "No tests directory found"}

    # 先尝试下载 wget/curl 的文件（如 pdf-excel-diff 需要的 employee 文件）
    env_dir = task.task_dir / "environment"
    _download_wget_files(env_dir, workspace)

    # 查找测试文件：优先 test_outputs.py，也支持其他 test_*.py
    test_output_file = tests_dir / "test_outputs.py"
    if not test_output_file.exists():
        # 尝试其他 test_*.py 文件
        other_tests = sorted(tests_dir.glob("test_*.py"))
        if other_tests:
            test_output_file = other_tests[0]
        else:
            return {"passed": False, "score": 0.0, "details": f"No test_*.py found in {tests_dir}"}

    # /app/output/ 应该对应 workspace/app/output/
    output_path = workspace / "app" / "output"
    output_path.mkdir(parents=True, exist_ok=True)

    # /root/ 应该对应 workspace/root/ (SkillsBench 任务的文件通常在 /root/ 下)
    root_path = workspace / "root"

    # 预处理测试文件：替换硬编码的路径
    # SkillsBench 任务中，测试文件可能硬编码 /root/ 或 /app/output 路径
    try:
        content = test_output_file.read_text(encoding="utf-8")
        modified = False

        # 替换 /app/output 为实际的 output_path 目录
        if "/app/output" in content:
            content = content.replace("/app/output", str(output_path))
            modified = True

        # 替换 /root/ 为 workspace/root/ 目录
        if "/root/" in content:
            content = content.replace("/root/", str(root_path) + "/")
            modified = True

        if modified:
            # 直接覆盖 test_outputs.py（这是在 workspace 的副本，不影响原始任务文件）
            test_output_file.write_text(content, encoding="utf-8")
    except Exception:
        pass  # 如果预处理失败，继续使用原始文件

    # 运行 pytest，设置 HOME
    env = os.environ.copy()
    env["HOME"] = str(Path.home())

    try:
        result = subprocess.run(
            [
                "pytest",
                str(test_output_file),
                "-v",
                "--tb=short",
            ],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

        passed = result.returncode == 0

        # 解析 pytest 输出获取详细信息
        details = {
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-1000:] if result.stderr else "",
            "returncode": result.returncode,
        }

        # 计算分数：所有测试通过得 100 分，否则得 0 分
        # 这是 SkillsBench 原生的评判方式
        score = 100.0 if passed else 0.0

        return {
            "passed": passed,
            "score": score,
            "details": details,
        }

    except subprocess.TimeoutExpired:
        return {"passed": False, "score": 0.0, "details": "pytest timed out"}
    except FileNotFoundError:
        return {"passed": False, "score": 0.0, "details": "pytest not installed"}
    except Exception as e:
        return {"passed": False, "score": 0.0, "details": f"pytest error: {str(e)}"}


def grade_task(task: Task, result: AgentResult, workspace: Path, use_pytest: bool = True) -> ScoreResult:
    """评估任务结果

    Args:
        task: 任务对象
        result: Agent 执行结果
        workspace: 工作空间路径
        use_pytest: 是否使用 pytest 验证（默认 True）

    Returns:
        ScoreResult: 评分结果
    """
    if result.status == "error":
        return ScoreResult(
            task_id=task.task_id,
            score=0.0,
            notes=f"Agent error: {result.error[:100]}",
        )

    if result.status == "timeout":
        return ScoreResult(
            task_id=task.task_id,
            score=10.0,
            notes="Task timed out",
        )

    # 尝试使用 pytest 验证（原生评判）
    pytest_result = None
    if use_pytest:
        pytest_result = run_pytest_verification(task, workspace)

        if pytest_result["passed"]:
            return ScoreResult(
                task_id=task.task_id,
                score=pytest_result["score"],
                passed=True,
                breakdown={"pytest": pytest_result["details"]},
                notes=f"PASS - pytest passed (100/100)",
            )
        elif "pytest not installed" not in pytest_result["details"]:
            # pytest 运行了但测试失败
            return ScoreResult(
                task_id=task.task_id,
                score=pytest_result["score"],
                passed=False,
                breakdown={"pytest": pytest_result["details"]},
                notes=f"FAIL - pytest failed (0/100): {str(pytest_result['details'])[:100]}",
            )

    # 回退到启发式评分（当 pytest 不可用或没有测试时）
    output_checks = []
    output_score = 0.0

    for expected_file in task.expected_outputs:
        # 转换路径：尝试多个可能的写入位置
        # 1. workspace/app/output/xxx (标准)
        # 2. workspace/xxx (标准)
        # 3. workspace/root/xxx (agent 误以为在 /root/ 下)
        relative_path = expected_file.replace("/root/", "")
        local_path = workspace / relative_path
        alt_path = workspace / "root" / relative_path
        app_path = workspace / "app" / "output" / relative_path.replace("output/", "")

        found = False
        found_path = None
        for check_path in [app_path, local_path, alt_path]:
            if check_path.exists():
                found = True
                found_path = check_path
                break

        if found:
            output_checks.append({"file": expected_file, "found": True, "size": found_path.stat().st_size, "path": str(found_path)})
            output_score += 1.0
        else:
            output_checks.append({"file": expected_file, "found": False, "tried": [str(app_path), str(local_path), str(alt_path)]})

    # 如果没有明确的输出文件，检查 workspace 中的文件
    if not task.expected_outputs:
        files = list(workspace.rglob("*"))
        file_count = len([f for f in files if f.is_file()])
        if file_count > 0:
            output_score = min(50.0, file_count * 10)

    # 基于难度调整基础分
    difficulty_scores = {
        "easy": 30.0,
        "medium": 20.0,
        "hard": 10.0,
    }
    base_score = difficulty_scores.get(task.difficulty, 20.0)

    # 检查是否有合理的响应
    if result.content:
        base_score += 10.0

    # 检查是否有工具调用
    tool_calls = _count_tool_calls(result.transcript)
    if tool_calls > 0:
        base_score += 10.0
        if tool_calls >= 3:
            base_score += 5.0

    # 计算输出文件分
    output_weight = len(task.expected_outputs) if task.expected_outputs else 1
    output_points = (output_score / output_weight) * 30 if output_weight > 0 else 0

    total_score = min(100.0, base_score + output_points)

    # 判断是否通过（60分以上）
    passed = total_score >= 60.0

    return ScoreResult(
        task_id=task.task_id,
        score=total_score,
        passed=passed,
        breakdown={
            "base_score": base_score,
            "output_score": output_points,
            "tool_calls": tool_calls,
            "output_checks": output_checks,
            "pytest_fallback": pytest_result is not None,
        },
        notes=f"{'PASS' if passed else 'FAIL'} - {total_score:.0f}/100 (difficulty: {task.difficulty})",
    )


def _count_tool_calls(transcript: List[Dict]) -> int:
    """统计工具调用次数"""
    count = 0
    for entry in transcript:
        if entry.get("type") == "message":
            msg = entry.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "toolCall":
                        count += 1
    return count


class SkillsBenchAdapter:
    """SkillsBench 适配器"""

    def __init__(
        self,
        agent: BaseAgent,
        tasks_dir: Path,
        output_dir: Path | None = None,
        agent_factory: Optional[Callable[[Path], BaseAgent]] = None,
        transcript_dir: Path | None = None,
    ):
        self.agent = agent
        self.tasks_dir = tasks_dir
        self.output_dir = output_dir or Path("results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.agent_factory = agent_factory
        # transcript_dir: if set, transcripts go directly here (e.g. exp/transcripts/skillsbench/)
        # instead of output_dir/transcripts/
        self.transcript_dir = transcript_dir
        if self.transcript_dir:
            self.transcript_dir.mkdir(parents=True, exist_ok=True)

        self.tasks: List[Task] = []
        self.results: List[Dict] = []

    def load_tasks(
        self,
        difficulty: str | None = None,
        category: str | None = None,
    ) -> None:
        """加载任务"""
        self.tasks = TaskLoader(self.tasks_dir).load_all_tasks(
            difficulty=difficulty,
            category=category,
        )
        logger.info(f"Loaded {len(self.tasks)} tasks")

    def run(
        self,
        task_ids: List[str] | None = None,
        runs_per_task: int = 1,
        threads: int = 1,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """运行 benchmark

        Args:
            task_ids: 要运行的任务 ID 列表，None 表示全部
            runs_per_task: 每个任务运行次数
            threads: 并行线程数（默认1，即串行执行）
            progress_callback: 进度回调函数，接收 (completed, total, task_id, grade) 参数

        Returns:
            Dict: 运行结果
        """
        # 筛选任务
        if task_ids:
            tasks_to_run = [t for t in self.tasks if t.task_id in task_ids]
        else:
            tasks_to_run = self.tasks

        logger.info(f"Running benchmark on {len(tasks_to_run)} tasks ({runs_per_task} run(s) per task, {threads} thread(s))")

        if threads > 1:
            return self._run_parallel(tasks_to_run, runs_per_task, threads, progress_callback)
        else:
            return self._run_sequential(tasks_to_run, runs_per_task, progress_callback)

    def _run_sequential(
        self,
        tasks_to_run: List[Task],
        runs_per_task: int,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """串行执行任务"""
        scores_by_task_id = {}
        total = len(tasks_to_run) * runs_per_task

        for i, task in enumerate(tasks_to_run, 1):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Task {i}/{len(tasks_to_run)}: {task.task_id}")
            logger.info(f"Difficulty: {task.difficulty} | Category: {task.category}")
            logger.info(f"{'=' * 60}")

            task_grades = []

            for run_index in range(runs_per_task):
                workspace = self._prepare_workspace(task, f"{task.task_id}_{run_index}")

                try:
                    result = self.agent.execute(
                        task.instruction,
                        f"{task.task_id}_{run_index}",
                        workspace=workspace
                    )
                except Exception as e:
                    logger.warning(f"Task execution failed: {e}")
                    result = AgentResult(status="error", error=str(e))

                result.workspace = str(workspace)

                transcript_path = (self.transcript_dir or (self.output_dir / "transcripts")) / f"{task.task_id}_{run_index}.jsonl"
                result.save_transcript(transcript_path)

                grade = grade_task(task, result, workspace)
                task_grades.append(grade)

                status_emoji = "✅" if grade.passed else "❌"
                logger.info(f"{status_emoji} {task.task_id}: {grade.notes}")

                if progress_callback:
                    progress_callback(i, len(tasks_to_run), task.task_id, grade)

            scores = [g.score for g in task_grades]
            passed_count = sum(1 for g in task_grades if g.passed)
            scores_by_task_id[task.task_id] = {
                "task_name": task.name,
                "category": task.category,
                "difficulty": task.difficulty,
                "runs": [g.to_dict() for g in task_grades],
                "mean": statistics.mean(scores),
                "std": statistics.stdev(scores) if len(scores) > 1 else 0.0,
                "min": min(scores),
                "max": max(scores),
                "passed": passed_count > 0,
            }

        return self._generate_report(scores_by_task_id, tasks_to_run)

    def _run_parallel(
        self,
        tasks_to_run: List[Task],
        runs_per_task: int,
        threads: int,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """并行执行任务"""
        scores_by_task_id = {}
        lock = threading.Lock()
        completed_count = 0
        total_count = len(tasks_to_run) * runs_per_task

        def run_single_task(task: Task, run_index: int) -> tuple:
            """运行单个任务（线程安全）"""
            workspace = self._prepare_workspace(task, f"{task.task_id}_{run_index}")
            agent = self.agent_factory(workspace) if self.agent_factory else self.agent

            try:
                result = agent.execute(
                    task.instruction,
                    f"{task.task_id}_{run_index}",
                    workspace=workspace
                )
            except Exception as e:
                logger.warning(f"Task execution failed: {e}")
                result = AgentResult(status="error", error=str(e))
            finally:
                if self.agent_factory:
                    try:
                        agent.cleanup()
                    except Exception:
                        pass

            result.workspace = str(workspace)

            transcript_path = (self.transcript_dir or (self.output_dir / "transcripts")) / f"{task.task_id}_{run_index}.jsonl"
            result.save_transcript(transcript_path)

            grade = grade_task(task, result, workspace)
            return task, run_index, grade

        # 准备所有任务
        all_work = [(task, run_index) for task in tasks_to_run for run_index in range(runs_per_task)]

        logger.info(f"Starting parallel execution with {threads} threads on {len(all_work)} items")

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(run_single_task, task, run_idx): (task, run_idx) for task, run_idx in all_work}

            # 进度条
            if HAS_TQDM:
                pbar = tqdm(total=total_count, desc="Benchmark", unit="task", ncols=100)

            for future in as_completed(futures):
                task, run_index, grade = future.result()

                with lock:
                    completed_count += 1
                    status_emoji = "✅" if grade.passed else "❌"
                    logger.info(f"[{completed_count}/{total_count}] {status_emoji} {task.task_id}: {grade.notes}")

                    if progress_callback:
                        progress_callback(completed_count, total_count, task.task_id, grade)

                    if HAS_TQDM:
                        pbar.update(1)

                    # 收集结果
                    if task.task_id not in scores_by_task_id:
                        scores_by_task_id[task.task_id] = {
                            "task_name": task.name,
                            "category": task.category,
                            "difficulty": task.difficulty,
                            "runs": [],
                            "scores": [],
                        }

                    scores_by_task_id[task.task_id]["runs"].append(grade.to_dict())
                    scores_by_task_id[task.task_id]["scores"].append(grade.score)

            if HAS_TQDM:
                pbar.close()

        # 汇总每个任务的分数
        for task_id, data in scores_by_task_id.items():
            scores = data["scores"]
            passed_count = sum(1 for s, r in zip(scores, data["runs"]) if r["passed"])
            data["mean"] = statistics.mean(scores)
            data["std"] = statistics.stdev(scores) if len(scores) > 1 else 0.0
            data["min"] = min(scores)
            data["max"] = max(scores)
            data["passed"] = passed_count > 0
            del data["scores"]  # 清理临时字段

        return self._generate_report(scores_by_task_id, tasks_to_run)

    def _prepare_workspace(self, task: Task, run_id: str) -> Path:
        """准备任务工作空间"""
        import shutil

        workspace = Path(f"/tmp/benchmarks/skillsbench/{run_id}")

        # 清理旧的工作空间
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        # 创建 /app/ 目录结构（模拟容器内环境）
        app_dir = workspace / "app"
        app_output_dir = app_dir / "output"
        app_output_dir.mkdir(parents=True, exist_ok=True)

        # 将整个 environment/ 复制到 /app/，与 Dockerfile 的行为一致
        # 例如: environment/video/ -> /app/video/, environment/workspace/ -> /app/workspace/
        env_dir = task.task_dir / "environment"
        if env_dir.exists():
            # 复制所有子目录和文件（排除 Dockerfile 等容器相关文件）
            for item in env_dir.iterdir():
                if item.name in ("Dockerfile", "docker-compose.yaml"):
                    continue
                dest = app_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

        # 复制 environment/ 根目录下的文件到 /root/
        # 部分任务的 Dockerfile 使用 "COPY xxx /root/xxx"（如 COPY data /root/data）
        root_dest = workspace / "root"
        root_dest.mkdir(parents=True, exist_ok=True)
        for item in env_dir.iterdir():
            if item.is_file() and item.name not in ("Dockerfile", "docker-compose.yaml"):
                shutil.copy2(item, root_dest / item.name)

        # 创建 symlink: workspace/root/environment -> workspace/app
        # 这样 /root/environment/xxx/ 和 /app/xxx/ 都能访问
        env_link = root_dest / "environment"
        if env_link.is_symlink():
            env_link.unlink()
        if not env_link.exists():
            env_link.symlink_to("../app")

        # 下载 Dockerfile 中 wget/curl 下载的文件（如 employee Excel/PDF 文件）
        _download_wget_files(env_dir, workspace)

        # 复制 skills 到 /app/ 和 workspace
        skills_src = env_dir / "skills"
        if skills_src.exists():
            # /app/ 下的 skills
            app_skills_dir = app_dir / "skills"
            app_skills_dir.mkdir(exist_ok=True)
            for skill in skills_src.iterdir():
                if skill.is_dir():
                    shutil.copytree(skill, app_skills_dir / skill.name, dirs_exist_ok=True)

            # workspace 下的 skills
            skills_dest = workspace / "skills"
            skills_dest.mkdir(parents=True, exist_ok=True)
            for skill in skills_src.iterdir():
                if skill.is_dir():
                    shutil.copytree(skill, skills_dest / skill.name, dirs_exist_ok=True)

            # workspace/root/ 下的 skills（兼容性）
            skills_root = workspace / "root"
            skills_root.mkdir(exist_ok=True)
            for skill in skills_src.iterdir():
                if skill.is_dir():
                    shutil.copytree(skill, skills_root / skill.name, dirs_exist_ok=True)

        # 复制 skills 到 ~/.openclaw/skills
        main_skills_dir = Path.home() / ".openclaw" / "workspace" / "skills"
        if main_skills_dir.exists():
            dest_skills_dir = workspace / "skills"
            dest_skills_dir.mkdir(parents=True, exist_ok=True)
            for skill_dir_src in main_skills_dir.iterdir():
                if skill_dir_src.is_dir():
                    dest_skill_dir = dest_skills_dir / skill_dir_src.name
                    if dest_skill_dir.exists():
                        shutil.rmtree(dest_skill_dir)
                    shutil.copytree(skill_dir_src, dest_skill_dir)

        # 复制 tests 到 workspace（用于 pytest 验证）
        tests_dir = task.task_dir / "tests"
        if tests_dir.exists():
            tests_dest = workspace / "tests"
            shutil.copytree(tests_dir, tests_dest, dirs_exist_ok=True)

        return workspace

    def _generate_report(self, scores_by_task_id: Dict, tasks_to_run: List[Task]) -> Dict[str, Any]:
        """生成报告"""
        # 计算总分
        all_scores = [scores_by_task_id[tid]["mean"] for tid in scores_by_task_id]
        total_score = sum(all_scores) / len(all_scores) if all_scores else 0
        passed_count = sum(1 for s in scores_by_task_id.values() if s["passed"])

        # 按类别分组
        category_scores: Dict[str, Dict] = {}
        for task in tasks_to_run:
            category = task.category.upper()
            if category not in category_scores:
                category_scores[category] = {"earned": 0.0, "count": 0}

            score = scores_by_task_id.get(task.task_id, {}).get("mean", 0.0)
            category_scores[category]["earned"] += score
            category_scores[category]["count"] += 1

        # 计算类别平均分
        category_averages = {}
        for cat, data in category_scores.items():
            category_averages[cat] = data["earned"] / data["count"] if data["count"] > 0 else 0

        # 按难度分组
        difficulty_scores: Dict[str, Dict] = {}
        for task in tasks_to_run:
            diff = task.difficulty.upper()
            if diff not in difficulty_scores:
                difficulty_scores[diff] = {"earned": 0.0, "count": 0}

            score = scores_by_task_id.get(task.task_id, {}).get("mean", 0.0)
            difficulty_scores[diff]["earned"] += score
            difficulty_scores[diff]["count"] += 1

        difficulty_averages = {}
        for diff, data in difficulty_scores.items():
            difficulty_averages[diff] = data["earned"] / data["count"] if data["count"] > 0 else 0

        # 打印摘要
        logger.info("\n" + "=" * 60)
        logger.info("SKILLSBENCH SCORE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Overall Score: {total_score:.1f}%")
        logger.info(f"Passed: {passed_count}/{len(scores_by_task_id)} tasks")
        logger.info("")
        logger.info(f"{'Category':<20} {'Score':>10} {'Tasks':>10}")
        logger.info("-" * 44)
        for category in sorted(category_averages.keys()):
            data = category_scores[category]
            logger.info(f"{category:<20} {category_averages[category]:>9.1f}% {data['count']:>10}")

        logger.info("")
        logger.info(f"{'Difficulty':<20} {'Score':>10} {'Tasks':>10}")
        logger.info("-" * 44)
        for diff in sorted(difficulty_averages.keys()):
            data = difficulty_scores[diff]
            logger.info(f"{diff:<20} {difficulty_averages[diff]:>9.1f}% {data['count']:>10}")

        # 构建结果字典
        result = {
            "benchmark": "skillsbench",
            "timestamp": time.time(),
            "overall_score": round(total_score, 2),
            "passed_tasks": passed_count,
            "total_tasks": len(scores_by_task_id),
            "category_scores": {
                cat: {
                    "score": round(category_averages[cat], 2),
                    "count": category_scores[cat]["count"],
                }
                for cat in category_scores
            },
            "difficulty_scores": {
                diff: {
                    "score": round(difficulty_averages[diff], 2),
                    "count": difficulty_scores[diff]["count"],
                }
                for diff in difficulty_scores
            },
            "task_scores": {
                tid: {
                    "task_name": data["task_name"],
                    "category": data["category"],
                    "difficulty": data["difficulty"],
                    "mean": round(data["mean"], 2),
                    "std": round(data["std"], 2),
                    "passed": data["passed"],
                }
                for tid, data in scores_by_task_id.items()
            },
        }

        # 保存结果
        run_id = f"{int(time.time() * 1000):013d}"
        output_path = self.output_dir / f"skillsbench_{run_id}.json"
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info(f"\nResults saved to: {output_path}")

        return result
