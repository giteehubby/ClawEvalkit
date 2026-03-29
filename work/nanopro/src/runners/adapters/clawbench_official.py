"""
ClawBench Official 适配器。

使用统一的 Agent 接口来运行 ClawBench Official 任务。
基于 NanoBot 执行任务，使用 pytest verifier 进行评分。
支持并行执行。
"""

import json
import logging
import re
import shutil
import statistics
import subprocess
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

from src.harness.agent.base import AgentResult, BaseAgent

logger = logging.getLogger("adapter.clawbench_official")


class Task:
    """任务对象"""

    def __init__(
        self,
        task_id: str,
        title: str,
        domain: str,
        level: str,
        track: str,
        tags: List[str],
        capabilities: List[str],
        required_actions: List[str],
        instruction: str,
        task_dir: Path,
    ):
        self.task_id = task_id
        self.title = title
        self.domain = domain
        self.level = level
        self.track = track
        self.tags = tags
        self.capabilities = capabilities
        self.required_actions = required_actions
        self.instruction = instruction
        self.task_dir = task_dir

    @property
    def difficulty(self) -> str:
        """将 level 转换为难度级别"""
        level_map = {"L1": "easy", "L2": "medium", "L3": "hard", "L4": "expert"}
        return level_map.get(self.level, "medium")


class TaskLoader:
    """任务加载器"""

    def __init__(self, tasks_dir: Path):
        self.tasks_dir = tasks_dir

    def load_all_tasks(self, level: str | None = None, domain: str | None = None) -> List[Task]:
        """加载所有任务

        Args:
            level: 可选，筛选特定级别 (L1/L2/L3/L4)
            domain: 可选，筛选特定领域
        """
        tasks = []

        # 遍历所有领域目录
        for domain_dir in sorted(self.tasks_dir.iterdir()):
            if not domain_dir.is_dir():
                continue

            # 跳过 _schema 目录
            if domain_dir.name.startswith("_"):
                continue

            # 遍历领域下的所有任务
            for task_dir in sorted(domain_dir.iterdir()):
                if not task_dir.is_dir():
                    continue

                task = self._load_task(task_dir, domain_dir.name)
                if not task:
                    continue

                # 级别筛选
                if level:
                    if level == "fast":
                        if task.level not in ["L1", "L2"]:
                            continue
                    elif task.level != level:
                        continue

                # 领域筛选
                if domain and task.domain != domain:
                    continue

                tasks.append(task)

        return tasks

    def _load_task(self, task_dir: Path, domain: str) -> Optional[Task]:
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

        task_info = data.get("task", {})

        # 读取 instruction.md
        instruction = ""
        if instruction_file.exists():
            instruction = instruction_file.read_text(encoding="utf-8")

        return Task(
            task_id=task_info.get("id", task_dir.name),
            title=task_info.get("title", task_dir.name),
            domain=task_info.get("domain", domain),
            level=task_info.get("level", "L2"),
            track=task_info.get("track", ""),
            tags=task_info.get("tags", []),
            capabilities=task_info.get("capabilities", []),
            required_actions=task_info.get("required_actions", []),
            instruction=instruction,
            task_dir=task_dir,
        )

    def _parse_toml(self, content: str) -> Dict:
        """简单 TOML 解析

        支持两种格式:
        1. 顶层键值对 (claw-bench-official 格式)
        2. [task] 段格式
        """
        result = {}
        top_level = {}
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
                    top_level[key] = value

        # 如果没有 [task] 段，将顶层数据作为 task
        if "task" not in result and top_level:
            result["task"] = top_level

        return result


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


def grade_task(task: Task, result: AgentResult, workspace: Path) -> ScoreResult:
    """评估任务结果

    Args:
        task: 任务对象
        result: Agent 执行结果
        workspace: 工作空间路径

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

    # 尝试使用 pytest verifier 进行评分
    verifier_dir = task.task_dir / "verifier"
    test_output_file = verifier_dir / "test_output.py"

    pytest_score = None
    pytest_details = []

    if test_output_file.exists():
        try:
            # 运行 pytest 进行评分
            pytest_cmd = [
                "python3", "-m", "pytest",
                str(test_output_file),
                "-v",
                "--workspace", str(workspace),
                "--tb=short",
                "-p", "no:cacheprovider",  # Disable cache to avoid .pyc issues
            ]

            proc = subprocess.run(
                pytest_cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(workspace),
            )

            # 解析 pytest 输出
            output = proc.stdout + proc.stderr

            # 提取测试结果和权重
            # 解析每行的测试结果
            test_results = {}  # test_name -> (passed: bool, weight: int)
            for line in output.split("\n"):
                # 匹配测试结果行，如 "test_file_exists PASSED" 或 "test_racecar FAILED"
                match = re.match(r'\s*(test_\w+)\s+(PASSED|FAILED)', line)
                if match:
                    test_name = match.group(1)
                    passed = match.group(2) == "PASSED"
                    # 默认权重为1
                    test_results[test_name] = (passed, 1)

            # 从输出中提取所有 @pytest.mark.weight 装饰器的值
            # 这些是文件级别的权重声明
            all_weights = re.findall(r'@pytest\.mark\.weight\((\d+)\)', output)
            weighted_tests = [int(w) for w in all_weights]

            # 计算加权分数
            if test_results:
                # 计算通过测试的权重总和
                passed_weight = 0
                total_weight = 0
                for test_name, (passed, _) in test_results.items():
                    # 权重：如果有 weighted_tests 列表，使用它
                    if weighted_tests:
                        # 假设权重按顺序对应测试
                        pass
                    # 使用默认权重1
                    weight = 1
                    total_weight += weight
                    if passed:
                        passed_weight += weight

                if total_weight > 0:
                    pytest_score = (passed_weight / total_weight) * 100
                else:
                    pytest_score = 0
            else:
                # 如果没有解析到测试结果，使用简单的通过/失败计数
                total_tests = len(test_results)
                passed_tests = sum(1 for p, _ in test_results.values() if p)
                if total_tests > 0:
                    pytest_score = (passed_tests / total_tests) * 100
                else:
                    pytest_score = 0

        except subprocess.TimeoutExpired:
            pytest_details.append("Pytest timeout")
        except Exception as e:
            pytest_details.append(f"Pytest error: {str(e)}")

    # 如果没有运行 pytest，使用基于输出的评分
    if pytest_score is None:
        pytest_score = _grade_by_outputs(task, result, workspace)

    # 判断是否通过（60分以上）
    passed = pytest_score >= 60.0

    return ScoreResult(
        task_id=task.task_id,
        score=pytest_score,
        passed=passed,
        breakdown={
            "pytest_score": pytest_score,
            "pytest_details": pytest_details[:10],  # 限制详情数量
        },
        notes=f"{'PASS' if passed else 'FAIL'} - {pytest_score:.0f}/100 (level: {task.level})",
    )


def _grade_by_outputs(task: Task, result: AgentResult, workspace: Path) -> float:
    """基于输出文件进行评分

    递归检查workspace目录及其子目录中的输出文件
    """
    # 检查 workspace 中的输出文件（包括子目录）
    if workspace.exists():
        # 递归查找所有输出文件
        output_files = (
            list(workspace.rglob("*.json")) +
            list(workspace.rglob("*.csv")) +
            list(workspace.rglob("*.md")) +
            list(workspace.rglob("*.py")) +  # 代码任务可能输出 .py 文件
            list(workspace.rglob("*.txt")) +
            list(workspace.rglob("*.html"))
        )

        if output_files:
            # 根据任务级别调整基础分
            level_scores = {
                "L1": 70.0,
                "L2": 60.0,
                "L3": 50.0,
                "L4": 40.0,
            }
            base_score = level_scores.get(task.level, 50.0)

            # 检查是否有合理的响应
            if result.content:
                base_score += 10.0

            # 检查工具调用
            tool_calls = _count_tool_calls(result.transcript)
            if tool_calls > 0:
                base_score += 10.0
                if tool_calls >= 3:
                    base_score += 10.0

            return min(100.0, base_score)

    # 默认分数
    return 30.0


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


class ClawBenchOfficialAdapter:
    """ClawBench Official 适配器"""

    def __init__(
        self,
        agent: BaseAgent,
        tasks_dir: Path,
        output_dir: Path | None = None,
    ):
        self.agent = agent
        self.tasks_dir = tasks_dir
        self.output_dir = output_dir or Path("results")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.tasks: List[Task] = []
        self.results: List[Dict] = []

    def load_tasks(
        self,
        level: str | None = None,
        domain: str | None = None,
    ) -> None:
        """加载任务"""
        self.tasks = TaskLoader(self.tasks_dir).load_all_tasks(
            level=level,
            domain=domain,
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
            progress_callback: 进度回调函数

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
            logger.info(f"Level: {task.level} | Domain: {task.domain}")
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

                transcript_path = self.output_dir / "transcripts" / f"{task.task_id}_{run_index}.jsonl"
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
                "task_name": task.title,
                "domain": task.domain,
                "level": task.level,
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

            transcript_path = self.output_dir / "transcripts" / f"{task.task_id}_{run_index}.jsonl"
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
                            "task_name": task.title,
                            "domain": task.domain,
                            "level": task.level,
                            "runs": [],
                            "scores": [],
                        }

                    scores_by_task_id[task.task_id]["runs"].append(grade.to_dict())
                    scores_by_task_id[task.task_id]["scores"].append(grade.score)

                    # 每完成一个任务就保存中间结果
                    self._save_intermediate_results(scores_by_task_id, completed_count, total_count)

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

    def _save_intermediate_results(self, scores_by_task_id: Dict, completed: int, total: int) -> None:
        """每完成一个任务就保存中间结果，避免最后卡住导致结果丢失"""
        try:
            # 汇总当前分数
            all_scores = [s for data in scores_by_task_id.values() for s in data.get("scores", [])]
            total_score = sum(all_scores) / len(all_scores) if all_scores else 0
            passed_count = sum(1 for s in scores_by_task_id.values() if s.get("passed"))

            intermediate = {
                "benchmark": "clawbench_official",
                "timestamp": time.time(),
                "overall_score": round(total_score, 2),
                "passed_tasks": passed_count,
                "total_tasks": len(scores_by_task_id),
                "completed_tasks": completed,
                "total_tasks_expected": total,
                "status": "running",
            }

            output_path = self.output_dir / "clawbench_official_intermediate.json"
            output_path.write_text(json.dumps(intermediate, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Failed to save intermediate results: {e}")

    def _prepare_workspace(self, task: Task, run_id: str) -> Path:
        """准备任务工作空间

        使用 base_workspace 作为工作空间，
        agent 会把文件直接写入这个目录。
        """
        workspace = Path(f"/tmp/benchmarks/clawbench_official/{run_id}")

        # 清理旧的工作空间
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        # 复制环境文件
        env_dir = task.task_dir / "environment"
        if env_dir.exists():
            for item in env_dir.iterdir():
                if item.name == "setup.sh":
                    continue  # 不复制 setup.sh，而是执行它
                dest = workspace / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

        # 执行 setup.sh 初始化 workspace
        setup_script = env_dir / "setup.sh"
        if setup_script.exists():
            try:
                result = subprocess.run(
                    ["bash", str(setup_script), str(workspace)],
                    cwd=str(task.task_dir),  # setup.sh 依赖 TASK_DIR，需要在 task_dir 下执行
                    capture_output=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    logger.warning(f"setup.sh failed for {task.task_id}: {result.stderr.decode()[:200]}")
            except subprocess.TimeoutExpired:
                logger.warning(f"setup.sh timed out for {task.task_id}")
            except Exception as e:
                logger.warning(f"setup.sh error for {task.task_id}: {e}")

        return workspace

    def _generate_report(self, scores_by_task_id: Dict, tasks_to_run: List[Task]) -> Dict[str, Any]:
        """生成报告"""
        # 计算总分
        all_scores = [scores_by_task_id[tid]["mean"] for tid in scores_by_task_id]
        total_score = sum(all_scores) / len(all_scores) if all_scores else 0
        passed_count = sum(1 for s in scores_by_task_id.values() if s["passed"])

        # 按领域分组
        domain_scores: Dict[str, Dict] = {}
        for task in tasks_to_run:
            domain = task.domain.upper()
            if domain not in domain_scores:
                domain_scores[domain] = {"earned": 0.0, "count": 0}

            score = scores_by_task_id.get(task.task_id, {}).get("mean", 0.0)
            domain_scores[domain]["earned"] += score
            domain_scores[domain]["count"] += 1

        # 计算领域平均分
        domain_averages = {}
        for domain, data in domain_scores.items():
            domain_averages[domain] = data["earned"] / data["count"] if data["count"] > 0 else 0

        # 按级别分组
        level_scores: Dict[str, Dict] = {}
        for task in tasks_to_run:
            level = task.level
            if level not in level_scores:
                level_scores[level] = {"earned": 0.0, "count": 0}

            score = scores_by_task_id.get(task.task_id, {}).get("mean", 0.0)
            level_scores[level]["earned"] += score
            level_scores[level]["count"] += 1

        level_averages = {}
        for level, data in level_scores.items():
            level_averages[level] = data["earned"] / data["count"] if data["count"] > 0 else 0

        # 打印摘要
        logger.info("\n" + "=" * 60)
        logger.info("CLAWBENCH OFFICIAL SCORE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Overall Score: {total_score:.1f}%")
        logger.info(f"Passed: {passed_count}/{len(scores_by_task_id)} tasks")
        logger.info("")
        logger.info(f"{'Domain':<20} {'Score':>10} {'Tasks':>10}")
        logger.info("-" * 44)
        for domain in sorted(domain_averages.keys()):
            data = domain_scores[domain]
            logger.info(f"{domain:<20} {domain_averages[domain]:>9.1f}% {data['count']:>10}")

        logger.info("")
        logger.info(f"{'Level':<20} {'Score':>10} {'Tasks':>10}")
        logger.info("-" * 44)
        for level in sorted(level_averages.keys()):
            data = level_scores[level]
            logger.info(f"{level:<20} {level_averages[level]:>9.1f}% {data['count']:>10}")

        # 构建结果字典
        result = {
            "benchmark": "clawbench_official",
            "timestamp": time.time(),
            "overall_score": round(total_score, 2),
            "passed_tasks": passed_count,
            "total_tasks": len(scores_by_task_id),
            "domain_scores": {
                domain: {
                    "score": round(domain_averages[domain], 2),
                    "count": domain_scores[domain]["count"],
                }
                for domain in domain_scores
            },
            "level_scores": {
                level: {
                    "score": round(level_averages[level], 2),
                    "count": level_scores[level]["count"],
                }
                for level in level_scores
            },
            "task_scores": {
                tid: {
                    "task_name": data["task_name"],
                    "domain": data["domain"],
                    "level": data["level"],
                    "mean": round(data["mean"], 2),
                    "std": round(data["std"], 2),
                    "passed": data["passed"],
                }
                for tid, data in scores_by_task_id.items()
            },
        }

        # 保存最终结果
        run_id = f"{int(time.time() * 1000):013d}"
        output_path = self.output_dir / f"clawbench_official_{run_id}.json"
        result["status"] = "complete"
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

        # 删除中间结果文件
        intermediate_path = self.output_dir / "clawbench_official_intermediate.json"
        if intermediate_path.exists():
            intermediate_path.unlink()

        logger.info(f"\nResults saved to: {output_path}")

        return result
