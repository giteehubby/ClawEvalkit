"""
PinchBench 适配器。

使用统一的 Agent 接口来运行 PinchBench 任务。
"""

import json
import logging
import re
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from src.harness.agent.base import AgentResult, BaseAgent

logger = logging.getLogger("adapter.pinchbench")


class Task:
    """任务对象"""

    def __init__(
        self,
        task_id: str,
        name: str,
        prompt: str,
        category: str,
        timeout: int,
        grading_type: str,
        grading_code: str = "",
        workspace_files: List[Dict] | None = None,
        sessions: List | None = None,
        frontmatter: Dict | None = None,
    ):
        self.task_id = task_id
        self.name = name
        self.prompt = prompt
        self.category = category
        self.timeout_seconds = timeout
        self.grading_type = grading_type
        self.grading_code = grading_code
        self.workspace_files = workspace_files or []
        self.sessions = sessions or []
        self.frontmatter = frontmatter or {}


class TaskLoader:
    """任务加载器"""

    def __init__(self, tasks_dir: Path):
        self.tasks_dir = tasks_dir

    def load_all_tasks(self) -> List[Task]:
        """加载所有任务"""
        tasks = []
        for task_file in sorted(self.tasks_dir.glob("task_*.md")):
            if task_file.name == "TASK_TEMPLATE.md":
                continue
            task = self._load_task(task_file)
            if task:
                tasks.append(task)
        return tasks

    def _load_task(self, path: Path) -> Optional[Task]:
        """加载单个任务"""
        content = path.read_text(encoding="utf-8")

        # 解析 frontmatter
        frontmatter = {}
        grading_code = ""

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_text = parts[1]
                body = parts[2].strip()

                # 使用 YAML 解析 frontmatter
                if HAS_YAML:
                    try:
                        frontmatter = yaml.safe_load(fm_text) or {}
                    except Exception as e:
                        logger.warning(f"Failed to parse YAML frontmatter in {path}: {e}")
                        # 回退到简单解析
                        frontmatter = self._parse_simple_frontmatter(fm_text)
                else:
                    frontmatter = self._parse_simple_frontmatter(fm_text)

                # 提取 grading 代码
                grading_code = self._extract_grading_code(body)
            else:
                body = content
        else:
            body = content

        # 提取 task_id
        task_id = path.stem

        # 提取 name
        name = frontmatter.get("name", task_id.replace("_", " ").title())

        # 提取 category
        category = frontmatter.get("category", "general")

        # 提取 grading_type
        grading_type = frontmatter.get("grading_type", "automated")

        # 提取 timeout
        timeout = int(frontmatter.get("timeout_seconds", 300))

        # 提取 sessions
        sessions = []
        if "sessions" in frontmatter:
            sessions_str = frontmatter.get("sessions", "")
            if isinstance(sessions_str, str):
                sessions = [s.strip() for s in sessions_str.split(",")]
            elif isinstance(sessions_str, list):
                sessions = sessions_str

        # 提取 workspace files
        workspace_files = []
        if "workspace_files" in frontmatter:
            workspace_files = frontmatter.get("workspace_files", [])

        # 提取 prompt
        prompt = self._extract_prompt(body)

        return Task(
            task_id=task_id,
            name=name,
            prompt=prompt,
            category=category,
            timeout=timeout,
            grading_type=grading_type,
            grading_code=grading_code,
            workspace_files=workspace_files,
            sessions=sessions,
            frontmatter=frontmatter,
        )

    def _parse_simple_frontmatter(self, fm_text: str) -> Dict[str, Any]:
        """简单解析 frontmatter（当 YAML 不可用时）"""
        result = {}
        for line in fm_text.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip()
        return result

    def _extract_grading_code(self, body: str) -> str:
        """从 body 中提取 grading 代码"""
        # 查找 ```python ... ``` 块
        code_blocks = re.findall(r"```python\s*(.*?)```", body, re.DOTALL)
        if code_blocks:
            # 返回第一个 grading 函数
            return code_blocks[0]
        return ""

    def _extract_prompt(self, body: str) -> str:
        """从 body 中提取 prompt"""
        lines = body.split("\n")
        prompt_lines = []
        in_prompt = False

        for line in lines:
            # 匹配 ## Prompt 或 ## Prompt\n\n 之后的内容
            if re.match(r"^#{1,3}\s+Prompt", line, re.IGNORECASE):
                in_prompt = True
                continue
            if in_prompt:
                if line.startswith("#"):
                    break
                prompt_lines.append(line)

        if not prompt_lines:
            # 尝试提取 ## Task 后的内容
            for line in lines:
                if re.match(r"^#{1,3}\s+Task", line, re.IGNORECASE):
                    in_prompt = True
                    continue
                if in_prompt:
                    if line.startswith("#"):
                        break
                    prompt_lines.append(line)

        return "\n".join(prompt_lines).strip()


class GradeResult:
    """评分结果"""

    def __init__(
        self,
        task_id: str,
        score: float,
        max_score: float = 1.0,
        grading_type: str = "automated",
        breakdown: Dict | None = None,
        notes: str = "",
    ):
        self.task_id = task_id
        self.score = score
        self.max_score = max_score
        self.grading_type = grading_type
        self.breakdown = breakdown or {}
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "score": self.score,
            "max_score": self.max_score,
            "grading_type": self.grading_type,
            "breakdown": self.breakdown,
            "notes": self.notes,
        }


def grade_task(task: Task, result: AgentResult, skill_dir: Path) -> GradeResult:
    """评估任务结果

    Args:
        task: 任务对象
        result: Agent 执行结果
        skill_dir: PinchBench 根目录

    Returns:
        GradeResult: 评分结果
    """
    # 如果有 grading 代码，执行它
    if task.grading_code:
        return _grade_with_code(task, result)

    # 否则使用简单的自动评分
    return _grade_simple(task, result)


def _grade_with_code(task: Task, result: AgentResult) -> GradeResult:
    """使用 grading 代码评分"""
    # 构建 transcript
    transcript = _build_transcript_from_result(result)

    # 执行 grading 代码
    try:
        # 创建 grading 函数作用域
        local_vars = {}
        exec_globals = {
            "__builtins__": __builtins__,
            "Path": Path,
            "re": __import__("re"),
            "json": __import__("json"),
        }

        # 执行 grading 代码
        exec(task.grading_code, exec_globals, local_vars)

        # 查找 grade 函数
        grade_func = None
        for name, obj in local_vars.items():
            if callable(obj) and name == "grade":
                grade_func = obj
                break

        if grade_func is None:
            logger.warning(f"No grade function found in {task.task_id}")
            return _grade_simple(task, result)

        # 执行 grading
        scores = grade_func(transcript, result.workspace)

        # 计算总分
        if isinstance(scores, dict):
            breakdown = scores
            total = sum(scores.values())
            max_score = len(scores)
            # 返回比例分数（0-1）
            score_normalized = total / max_score if max_score > 0 else 0.0
        else:
            breakdown = {"score": scores}
            total = float(scores)
            max_score = 1.0
            score_normalized = total

        return GradeResult(
            task_id=task.task_id,
            score=score_normalized,  # 返回 0-1 范围的比例
            max_score=1.0,  # 统一 max_score 为 1
            grading_type=task.grading_type,
            breakdown=breakdown,
        )

    except Exception as e:
        logger.warning(f"Grading code failed for {task.task_id}: {e}")
        return _grade_simple(task, result)


def _build_transcript_from_result(result: AgentResult) -> List[Dict]:
    """从 AgentResult 构建 transcript"""
    transcript = []

    # 添加 assistant 消息
    if result.transcript:
        transcript.extend(result.transcript)
    elif result.content:
        # 如果没有 transcript 但有 content，创建一个简单的消息
        transcript.append({
            "type": "message",
            "message": {
                "role": "assistant",
                "content": result.content,
            }
        })

    return transcript


def _grade_simple(task: Task, result: AgentResult) -> GradeResult:
    """简单的自动评分"""
    # 基于任务完成状态评分
    if result.status == "error":
        return GradeResult(
            task_id=task.task_id,
            score=0.0,
            grading_type="automated",
            notes=f"Agent error: {result.error[:100]}",
        )

    if result.status == "timeout":
        return GradeResult(
            task_id=task.task_id,
            score=0.3,
            grading_type="automated",
            notes="Task timed out",
        )

    # 检查是否有响应内容
    if not result.content and not result.transcript:
        return GradeResult(
            task_id=task.task_id,
            score=0.0,
            grading_type="automated",
            notes="No response from agent",
        )

    # 基础分：任务成功执行
    score = 0.5

    # 检查 workspace 文件
    workspace = Path(result.workspace)
    if workspace.exists():
        files = list(workspace.rglob("*"))
        file_count = len([f for f in files if f.is_file()])
        if file_count > 0:
            score += 0.2

    return GradeResult(
        task_id=task.task_id,
        score=min(score, 1.0),
        grading_type="automated",
    )


class PinchBenchAdapter:
    """PinchBench 适配器"""

    def __init__(
        self,
        agent: BaseAgent,
        tasks_dir: Path,
        skill_dir: Path,
        output_dir: Path | None = None,
    ):
        self.agent = agent
        self.task_loader = TaskLoader(tasks_dir)
        self.skill_dir = skill_dir
        self.output_dir = output_dir or Path("results")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.tasks: List[Task] = []
        self.results: List[Dict] = []

    def load_tasks(self) -> None:
        """加载所有任务"""
        self.tasks = self.task_loader.load_all_tasks()
        logger.info(f"Loaded {len(self.tasks)} tasks")

    @staticmethod
    def _merge_multi_session_results(results_list: List[AgentResult]) -> AgentResult:
        """将多轮 session 结果合并成单个结果，便于统一评分和 transcript 保存。"""
        if not results_list:
            return AgentResult(status="error", error="No results")

        combined_transcript: List[Dict[str, Any]] = []
        combined_content: List[str] = []
        last_result = results_list[-1]

        for result in results_list:
            if result.transcript:
                combined_transcript.extend(result.transcript)
            if result.content:
                combined_content.append(result.content)

        return AgentResult(
            status=last_result.status,
            content=last_result.content or "\n\n".join(combined_content),
            transcript=combined_transcript,
            usage=last_result.usage,
            workspace=last_result.workspace,
            execution_time=sum(r.execution_time for r in results_list),
            error=last_result.error,
        )

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

        grades_by_task_id = {}

        for i, task in enumerate(tasks_to_run, 1):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Task {i}/{len(tasks_to_run)}: {task.task_id} ({task.name})")
            logger.info(f"{'=' * 60}")

            task_grades = []
            task_results = []

            for run_index in range(runs_per_task):
                # 准备工作空间
                workspace = self._prepare_workspace(task, f"{task.task_id}_{run_index}")

                # 执行任务
                try:
                    if task.sessions:
                        # 多轮对话
                        results_list = self.agent.execute_multi(task.sessions, f"{task.task_id}_{run_index}", workspace=workspace)
                        result = self._merge_multi_session_results(results_list)
                    else:
                        # 单轮对话
                        result = self.agent.execute(task.prompt, f"{task.task_id}_{run_index}", workspace=workspace)
                except Exception as e:
                    logger.warning(f"Task execution failed: {e}")
                    result = AgentResult(status="error", error=str(e))

                # 设置 workspace 路径
                result.workspace = str(workspace)
                task_results.append(result)

                # 保存 transcript
                transcript_path = self.output_dir / "transcripts" / f"{task.task_id}_{run_index}.jsonl"
                result.save_transcript(transcript_path)
                logger.info(f"   Transcript saved: {transcript_path}")

                # 评分
                grade = grade_task(task, result, self.skill_dir)
                task_grades.append(grade)

                # 记录分数
                score_pct = grade.score / grade.max_score * 100 if grade.max_score > 0 else 0
                status_emoji = "✅" if score_pct >= 70 else "⚠️" if score_pct > 0 else "❌"
                logger.info(f"{status_emoji} {task.task_id}: {score_pct:.1f}% ({grade.score:.2f}/{grade.max_score})")

                if grade.notes:
                    logger.info(f"   Notes: {grade.notes[:100]}")

            # 统计多轮运行的平均分
            scores = [g.score for g in task_grades]
            grades_by_task_id[task.task_id] = {
                "task_name": task.name,
                "category": task.category,
                "runs": [g.to_dict() for g in task_grades],
                "mean": statistics.mean(scores),
                "std": statistics.stdev(scores) if len(scores) > 1 else 0.0,
                "min": min(scores),
                "max": max(scores),
            }

        # 生成报告
        return self._generate_report(grades_by_task_id, tasks_to_run)

    def _prepare_workspace(self, task: Task, run_id: str) -> Path:
        """准备任务工作空间"""
        import shutil
        import tempfile

        workspace = Path(tempfile.gettempdir()) / "benchmarks" / "pinchbench" / run_id

        # 清理旧的工作空间
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        # 复制 workspace files
        for file_spec in task.workspace_files:
            if isinstance(file_spec, dict):
                dest_name = file_spec.get("dest") or file_spec.get("path", "")
                content = file_spec.get("content")
                source_name = file_spec.get("source")
            else:
                dest_name = str(file_spec)
                content = None
                source_name = str(file_spec)

            dest = workspace / dest_name

            # 如果有 content，直接写入文件
            if content:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
            # 否则从 assets 目录复制
            elif source_name:
                source = self.skill_dir / "assets" / source_name
                if source.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)

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

    def _generate_report(self, grades_by_task_id: Dict, tasks_to_run: List[Task]) -> Dict[str, Any]:
        """生成报告"""
        # 计算总分
        all_scores = [grades_by_task_id[tid]["mean"] for tid in grades_by_task_id]
        total_score = sum(all_scores)
        max_score = float(len(grades_by_task_id))
        score_pct = (total_score / max_score * 100) if max_score > 0 else 0

        # 计算 passed_tasks (默认阈值 0.7)
        passed_tasks = sum(1 for s in all_scores if s >= 0.7)

        # 按类别分组
        category_scores: Dict[str, Dict] = {}
        for task in tasks_to_run:
            category = task.category.upper() if task.category else "UNCATEGORIZED"
            if category not in category_scores:
                category_scores[category] = {"earned": 0.0, "possible": 0.0, "count": 0}

            score = grades_by_task_id.get(task.task_id, {}).get("mean", 0.0)
            category_scores[category]["earned"] += score
            category_scores[category]["possible"] += 1.0
            category_scores[category]["count"] += 1

        # 打印摘要
        logger.info("\n" + "=" * 60)
        logger.info("PINCHBENCH SCORE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Overall Score: {score_pct:.1f}% ({total_score:.1f} / {max_score:.0f})")
        logger.info("")
        logger.info(f"{'Category':<20} {'Score':>10} {'Tasks':>10}")
        logger.info("-" * 44)
        for category in sorted(category_scores.keys()):
            data = category_scores[category]
            pct = (data["earned"] / data["possible"] * 100) if data["possible"] > 0 else 0
            logger.info(f"{category:<20} {pct:>9.1f}% {data['count']:>10}")

        # 构建结果字典
        result = {
            "benchmark": "pinchbench",
            "timestamp": time.time(),
            "overall_score": round(score_pct, 2),
            "passed_tasks": passed_tasks,
            "total_tasks": len(grades_by_task_id),
            "category_scores": {
                cat: {
                    "score": round((data["earned"] / data["possible"] * 100), 2) if data["possible"] > 0 else 0,
                    "count": data["count"],
                }
                for cat, data in category_scores.items()
            },
            "task_scores": {
                tid: {
                    "task_name": data["task_name"],
                    "category": data["category"],
                    "mean": round(data["mean"], 4),
                    "std": round(data["std"], 4),
                }
                for tid, data in grades_by_task_id.items()
            },
        }

        # 保存结果
        run_id = f"{int(time.time() * 1000):013d}"
        output_path = self.output_dir / f"pinchbench_{run_id}.json"
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info(f"\nResults saved to: {output_path}")

        return result
