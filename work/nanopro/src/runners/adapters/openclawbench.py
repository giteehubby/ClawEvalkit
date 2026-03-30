"""
OpenClawBench 适配器。

使用统一的 Agent 接口来运行 OpenClawBench 任务。
基于 NanoBot 执行任务，复用 agentbench-openclaw 的打分逻辑。
"""

import hashlib
import json
import logging
import os
import re
import shutil
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from src.harness.agent.base import AgentResult, BaseAgent

logger = logging.getLogger("adapter.openclawbench")


class Task:
    """任务对象"""

    def __init__(
        self,
        task_id: str,
        name: str,
        user_message: str,
        suite: str,
        difficulty: str,
        mode: str,
        input_files: List[Dict],
        expected_outputs: List[Dict],
        expected_metrics: Dict,
        scoring: Dict,
        task_dir: Path,
    ):
        self.task_id = task_id
        self.name = name
        self.user_message = user_message
        self.suite = suite
        self.difficulty = difficulty
        self.mode = mode
        self.input_files = input_files
        self.expected_outputs = expected_outputs
        self.expected_metrics = expected_metrics
        self.scoring = scoring
        self.task_dir = task_dir


class TaskLoader:
    """任务加载器"""

    def __init__(self, tasks_dir: Path):
        self.tasks_dir = tasks_dir

    def load_all_tasks(self, suite: str | None = None, difficulty: str | None = None) -> List[Task]:
        """加载所有任务

        Args:
            suite: 可选，筛选特定 suite
            difficulty: 可选，筛选特定难度 (easy/medium/hard)
        """
        tasks = []

        for suite_dir in sorted(self.tasks_dir.iterdir()):
            if not suite_dir.is_dir():
                continue
            if suite and suite_dir.name != suite:
                continue

            for task_dir in sorted(suite_dir.iterdir()):
                if not task_dir.is_dir():
                    continue

                task_file = task_dir / "task.yaml"
                if not task_file.exists():
                    continue

                task = self._load_task(task_dir)
                if task:
                    # 难度筛选
                    if difficulty:
                        if difficulty == "fast":
                            if task.difficulty not in ["easy", "medium"]:
                                continue
                        elif task.difficulty != difficulty:
                            continue

                    tasks.append(task)

        return tasks

    def _load_task(self, task_dir: Path) -> Optional[Task]:
        """加载单个任务"""
        task_file = task_dir / "task.yaml"

        try:
            with open(task_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) if HAS_YAML else self._parse_yaml_simple(f.read())
        except Exception as e:
            logger.warning(f"Failed to load task {task_dir}: {e}")
            return None

        if not data:
            return None

        # 支持 turns 格式（多轮对话任务，如 memory suite）
        turns = data.get("turns", [])
        if turns and isinstance(turns[0], dict):
            first_message = turns[0].get("message", "") or ""
        else:
            first_message = data.get("user_message", "")

        return Task(
            task_id=data.get("id", task_dir.name),
            name=data.get("name", task_dir.name),
            user_message=first_message,
            suite=data.get("suite", task_dir.parent.name),
            difficulty=data.get("difficulty", "medium"),
            mode=data.get("mode", "real"),
            input_files=data.get("input_files", []),
            expected_outputs=data.get("expected_outputs", []),
            expected_metrics=data.get("expected_metrics", {}),
            scoring=data.get("scoring", {}),
            task_dir=task_dir,
        )

    def _parse_yaml_simple(self, content: str) -> Dict:
        """简单 YAML 解析（当 PyYAML 不可用时）"""
        result = {}
        for line in content.split("\n"):
            if ":" in line and not line.strip().startswith("#"):
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip().strip('"').strip("'")
        return result


class ScoreResult:
    """评分结果"""

    def __init__(
        self,
        task_id: str,
        layer0: float = 0.0,
        layer1: float = 0.0,
        layer2: float = 0.0,
        layer3: float = 0.0,
        composite: float = 0.0,
        breakdown: Dict | None = None,
        metrics: Dict | None = None,
        notes: str = "",
    ):
        self.task_id = task_id
        self.layer0 = layer0
        self.layer1 = layer1
        self.layer2 = layer2
        self.layer3 = layer3
        self.composite = composite
        self.breakdown = breakdown or {}
        self.metrics = metrics or {}
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "layer0": self.layer0,
            "layer1": self.layer1,
            "layer2": self.layer2,
            "layer3": self.layer3,
            "composite": self.composite,
            "breakdown": self.breakdown,
            "metrics": self.metrics,
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
    metrics = {
        "total_time_ms": result.execution_time * 1000 if result.execution_time else 0,
        "tool_calls_total": _count_tool_calls(result.transcript),
        "errors": 1 if result.status == "error" else 0,
        "planning_ratio": _estimate_planning_ratio(result.transcript),
    }

    # Layer 0: 自动结构检查
    layer0 = _grade_layer0(task, result, workspace)

    # Layer 1: 指标分析
    layer1 = _grade_layer1(task, metrics)

    # Layer 2: 行为分析
    layer2 = _grade_layer2(task, result)

    # Layer 3: 输出质量 (简化版 - 基于完成状态)
    layer3 = _grade_layer3(task, result, workspace)

    # 计算加权总分
    weights = task.scoring
    layer0_weight = weights.get("layer0_weight", 0.20)
    layer1_weight = weights.get("layer1_weight", 0.35)
    layer2_weight = weights.get("layer2_weight", 0.20)
    layer3_weight = weights.get("layer3_weight", 0.25)

    composite = (
        layer0 * layer0_weight +
        layer1 * layer1_weight +
        layer2 * layer2_weight +
        layer3 * layer3_weight
    )

    return ScoreResult(
        task_id=task.task_id,
        layer0=layer0,
        layer1=layer1,
        layer2=layer2,
        layer3=layer3,
        composite=composite,
        metrics=metrics,
        notes=f"{int(composite)}/100 (L0:{int(layer0)} L1:{int(layer1)} L2:{int(layer2)} L3:{int(layer3)})",
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


def _estimate_planning_ratio(transcript: List[Dict]) -> float:
    """估计规划时间比例（简化版）"""
    # 简单估算：前几次 tool calls 视为规划阶段
    tool_calls = 0
    for entry in transcript:
        if entry.get("type") == "message":
            msg = entry.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "toolCall":
                        tool_calls += 1
                        if tool_calls > 2:
                            break

    # 如果工具调用很少，规划比例低
    total_tools = _count_tool_calls(transcript)
    if total_tools <= 2:
        return 0.1
    if tool_calls <= 2:
        return 0.3
    return 0.2


def _grade_layer0(task: Task, agent_result: AgentResult, workspace: Path) -> float:
    """Layer 0: 自动结构检查"""
    if agent_result.status == "error":
        return 0.0

    total_points = 0
    earned_points = 0

    for output in task.expected_outputs:
        pattern = output.get("pattern", "")
        required = output.get("required", False)
        validators = output.get("validators", [])

        file_path = workspace / pattern
        matched = False

        for validator in validators:
            v_type = validator.get("type", "")
            total_points += 30  # 每个 validator 最多 30 分

            if v_type == "file-exists":
                if file_path.exists():
                    earned_points += 30
                    matched = True

            elif v_type == "content-contains":
                if file_path.exists():
                    sections = validator.get("sections", [])
                    found = 0
                    try:
                        content = file_path.read_text(encoding="utf-8").lower()
                        for section in sections:
                            if section.lower() in content:
                                found += 1
                        earned_points += (found / len(sections)) * 30 if sections else 0
                        matched = True
                    except:
                        pass

            elif v_type == "word-count-range":
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        word_count = len(content.split())
                        min_words = validator.get("min", 0)
                        max_words = validator.get("max", 1000000)
                        if min_words <= word_count <= max_words:
                            earned_points += 30
                        elif word_count >= min_words * 0.5:
                            earned_points += 15
                        matched = True
                    except:
                        pass

            elif v_type == "command-output-contains":
                if file_path.exists():
                    try:
                        cmd = validator.get("command", "")
                        contains = validator.get("contains", [])
                        # 在 workspace 目录执行命令
                        result = subprocess.run(
                            cmd, shell=True, cwd=str(workspace),
                            capture_output=True, text=True, timeout=10
                        )
                        output_text = result.stdout.lower()
                        found = sum(1 for c in contains if c.lower() in output_text)
                        if found == len(contains):
                            earned_points += 30
                        elif found > 0:
                            earned_points += (found / len(contains)) * 30
                        matched = True
                    except:
                        pass

    # 归一化到 0-100
    if total_points == 0:
        return 50.0
    return min(100.0, (earned_points / total_points) * 100)


def _grade_layer1(task: Task, metrics: Dict) -> float:
    """Layer 1: 指标分析"""
    if not task.expected_metrics:
        return 50.0

    expected_tools = task.expected_metrics.get("tool_calls", [0, 100])
    expected_ratio = task.expected_metrics.get("planning_ratio", [0, 1])
    errors = metrics.get("errors", 0)

    total_points = 0
    earned_points = 0

    # 工具调用数评分
    tool_calls = metrics.get("tool_calls_total", 0)
    min_tools, max_tools = expected_tools if len(expected_tools) == 2 else [0, 100]
    total_points += 40

    if min_tools <= tool_calls <= max_tools:
        earned_points += 40
    elif min_tools * 2 <= tool_calls <= max_tools * 2:
        earned_points += 20

    # 规划比例评分
    planning_ratio = metrics.get("planning_ratio", 0.2)
    min_ratio, max_ratio = expected_ratio if len(expected_ratio) == 2 else [0, 1]
    total_points += 30

    if min_ratio <= planning_ratio <= max_ratio:
        earned_points += 30
    elif min_ratio * 2 <= planning_ratio <= max_ratio * 2:
        earned_points += 15

    # 错误评分
    total_points += 30
    if errors == 0:
        earned_points += 30
    elif errors <= 2:
        earned_points += 15

    return (earned_points / total_points) * 100


def _grade_layer2(task: Task, result: AgentResult) -> float:
    """Layer 2: 行为分析"""
    if result.status == "error":
        return 20.0

    # 简化版行为评分
    # 指令遵循 (30分) - 基于是否有响应
    instruction_score = 25 if result.content else 10

    # 工具选择 (25分) - 基于工具调用类型
    tool_calls = _count_tool_calls(result.transcript)
    if tool_calls > 0:
        tool_score = 20
    else:
        tool_score = 10

    # 方法质量 (25分) - 简化
    approach_score = 20 if tool_calls > 0 else 10

    # 错误恢复 (20分)
    error_score = 20 if result.status == "success" else 10

    return instruction_score + tool_score + approach_score + error_score


def _grade_layer3(task: Task, result: AgentResult, workspace: Path) -> float:
    """Layer 3: 输出质量"""
    if result.status == "error":
        return 20.0

    # 简化版输出质量评分
    # 检查是否有输出文件
    has_outputs = False
    for output in task.expected_outputs:
        pattern = output.get("pattern", "")
        if (workspace / pattern).exists():
            has_outputs = True
            break

    if not has_outputs:
        return 0.0

    # 基于任务难度调整
    difficulty = task.difficulty
    if difficulty == "easy":
        return 75.0
    elif difficulty == "medium":
        return 65.0
    else:
        return 55.0


class OpenClawBenchAdapter:
    """OpenClawBench 适配器"""

    def __init__(
        self,
        agent: BaseAgent,
        tasks_dir: Path,
        output_dir: Path | None = None,
    ):
        self.agent = agent
        self.task_loader = TaskLoader(tasks_dir)
        self.output_dir = output_dir or Path("results")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.tasks: List[Task] = []
        self.results: List[Dict] = []

    def load_tasks(
        self,
        suite: str | None = None,
        difficulty: str | None = None,
    ) -> None:
        """加载任务"""
        self.tasks = self.task_loader.load_all_tasks(suite=suite, difficulty=difficulty)
        logger.info(f"Loaded {len(self.tasks)} tasks")

    def run(
        self,
        task_ids: List[str] | None = None,
        runs_per_task: int = 1,
    ) -> Dict[str, Any]:
        """运行 benchmark

        Args:
            task_ids: 要运行的任务 ID 列表，None 表示全部
            runs_per_task: 每个任务运行次数

        Returns:
            Dict: 运行结果
        """
        # 筛选任务
        if task_ids:
            tasks_to_run = [t for t in self.tasks if t.task_id in task_ids]
        else:
            tasks_to_run = self.tasks

        logger.info(f"Running benchmark on {len(tasks_to_run)} tasks ({runs_per_task} run(s) per task)")

        scores_by_task_id = {}

        for i, task in enumerate(tasks_to_run, 1):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Task {i}/{len(tasks_to_run)}: {task.task_id} ({task.name}) [{task.suite}]")
            logger.info(f"{'=' * 60}")

            task_scores = []

            for run_index in range(runs_per_task):
                # 准备工作空间
                workspace = self._prepare_workspace(task, f"{task.task_id}_{run_index}")

                # 执行任务
                try:
                    result = self.agent.execute(
                        task.user_message,
                        f"{task.task_id}_{run_index}",
                        workspace=workspace
                    )
                except Exception as e:
                    logger.warning(f"Task execution failed: {e}")
                    result = AgentResult(status="error", error=str(e))

                # 设置 workspace 路径
                result.workspace = str(workspace)

                # 保存 transcript
                transcript_path = self.output_dir / "transcripts" / f"{task.task_id}_{run_index}.jsonl"
                result.save_transcript(transcript_path)

                # 评分
                score = grade_task(task, result, workspace)
                task_scores.append(score)

                # 记录分数
                status_emoji = "✅" if score.composite >= 80 else "⚠️" if score.composite >= 50 else "❌"
                logger.info(f"{status_emoji} {task.task_id}: {score.notes}")

            # 统计多轮运行的平均分
            composites = [s.composite for s in task_scores]
            scores_by_task_id[task.task_id] = {
                "task_name": task.name,
                "suite": task.suite,
                "difficulty": task.difficulty,
                "runs": [s.to_dict() for s in task_scores],
                "mean": statistics.mean(composites),
                "std": statistics.stdev(composites) if len(composites) > 1 else 0.0,
                "min": min(composites),
                "max": max(composites),
                "metrics": task_scores[0].metrics if task_scores else {},
            }

        # 生成报告
        return self._generate_report(scores_by_task_id, tasks_to_run)

    def _prepare_workspace(self, task: Task, run_id: str) -> Path:
        """准备任务工作空间"""
        import shutil
        import tempfile

        workspace = Path(f"/tmp/benchmarks/openclawbench/{run_id}")

        # 清理旧的工作空间
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        # 复制输入文件
        task_inputs_dir = task.task_dir / "inputs"
        if task_inputs_dir.exists():
            for f in task_inputs_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, workspace / f.name)

        # 运行 setup.sh 如果存在
        setup_sh = task.task_dir / "setup.sh"
        if setup_sh.exists():
            normalized_setup_path = None
            try:
                # Normalize line endings before invoking task setup on Linux.
                # Some task repos may be checked out with CRLF from Windows.
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    suffix=".sh",
                    prefix="openclaw_setup_",
                    dir=workspace.parent,
                    delete=False,
                ) as tmp_setup:
                    tmp_setup.write(setup_sh.read_bytes().replace(b"\r\n", b"\n"))
                    normalized_setup_path = Path(tmp_setup.name)

                proc = subprocess.run(
                    ["bash", str(normalized_setup_path), str(workspace)],
                    capture_output=True,
                    timeout=30,
                    check=False,
                    text=True,
                )
                if proc.returncode != 0:
                    logger.warning(
                        "setup.sh failed for %s (exit=%s)\nstdout:\n%s\nstderr:\n%s",
                        task.task_id,
                        proc.returncode,
                        proc.stdout.strip(),
                        proc.stderr.strip(),
                    )
            except Exception as e:
                logger.warning(f"setup.sh failed: {e}")
            finally:
                if normalized_setup_path and normalized_setup_path.exists():
                    normalized_setup_path.unlink(missing_ok=True)

        # 复制 skills
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

        return workspace

    def _generate_report(self, scores_by_task_id: Dict, tasks_to_run: List[Task]) -> Dict[str, Any]:
        """生成报告"""
        # 计算总分
        all_scores = [scores_by_task_id[tid]["mean"] for tid in scores_by_task_id]
        total_score = sum(all_scores) / len(all_scores) if all_scores else 0

        # 计算 passed_tasks (阈值 >= 60)
        passed_tasks = sum(1 for s in all_scores if s >= 60)

        # 按 suite 分组
        suite_scores: Dict[str, Dict] = {}
        for task in tasks_to_run:
            suite = task.suite.upper()
            if suite not in suite_scores:
                suite_scores[suite] = {"earned": 0.0, "count": 0}

            score = scores_by_task_id.get(task.task_id, {}).get("mean", 0.0)
            suite_scores[suite]["earned"] += score
            suite_scores[suite]["count"] += 1

        # 计算 suite 平均分
        suite_averages = {}
        for suite, data in suite_scores.items():
            suite_averages[suite] = data["earned"] / data["count"] if data["count"] > 0 else 0

        # 打印摘要
        logger.info("\n" + "=" * 60)
        logger.info("OPENCLAWBENCH SCORE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Overall Score: {total_score:.1f}")
        logger.info(f"Total Tasks: {len(scores_by_task_id)}")
        logger.info("")
        logger.info(f"{'Suite':<20} {'Score':>10} {'Tasks':>10}")
        logger.info("-" * 44)
        for suite in sorted(suite_averages.keys()):
            data = suite_scores[suite]
            logger.info(f"{suite:<20} {suite_averages[suite]:>9.1f} {data['count']:>10}")

        # 构建结果字典
        result = {
            "benchmark": "openclawbench",
            "timestamp": time.time(),
            "overall_score": round(total_score, 2),
            "passed_tasks": passed_tasks,
            "total_tasks": len(scores_by_task_id),
            "suite_scores": {
                suite: {
                    "score": round(suite_averages[suite], 2),
                    "count": suite_scores[suite]["count"],
                }
                for suite in suite_scores
            },
            "task_scores": {
                tid: {
                    "task_name": data["task_name"],
                    "suite": data["suite"],
                    "difficulty": data["difficulty"],
                    "mean": round(data["mean"], 2),
                    "std": round(data["std"], 2),
                }
                for tid, data in scores_by_task_id.items()
            },
        }

        # 保存结果
        run_id = f"{int(time.time() * 1000):013d}"
        output_path = self.output_dir / f"openclawbench_{run_id}.json"
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info(f"\nResults saved to: {output_path}")

        return result
