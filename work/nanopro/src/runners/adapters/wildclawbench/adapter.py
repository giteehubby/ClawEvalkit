"""
WildClawBench 适配器。

使用统一的 Agent 接口来运行 WildClawBench 任务。
基于 NanoBot 执行任务，复用 wildclawbench 的 Docker 环境设置和打分逻辑。
"""

import json
import logging
import os
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.harness.agent.base import AgentResult, BaseAgent
from src.runners.adapters.wildclawbench.task_parser import parse_task_md
from src.runners.adapters.wildclawbench.grading import run_grading, format_scores
from src.runners.adapters.wildclawbench.docker_utils import (
    start_container,
    setup_workspace,
    setup_skills,
    run_warmup,
    remove_container,
    collect_output_from_container,
    TMP_WORKSPACE,
)

logger = logging.getLogger("adapter.wildclawbench")


@dataclass
class WildClawTask:
    """WildClawBench 任务对象"""
    task_id: str
    name: str
    category: str
    prompt: str
    timeout_seconds: int
    workspace_path: str  # host path
    skills_path: str
    automated_checks: str
    env: str
    skills: str
    warmup: str
    file_path: str = ""


class WildClawBenchAdapter:
    """WildClawBench 适配器"""

    def __init__(
        self,
        agent: BaseAgent,
        tasks_dir: Path,
        wildclawbench_dir: Path,
        output_dir: Path | None = None,
        use_docker: bool = True,
    ):
        self.agent = agent
        self.tasks_dir = tasks_dir
        self.wildclawbench_dir = wildclawbench_dir
        self.output_dir = output_dir or Path("results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_docker = use_docker

        self.tasks: List[WildClawTask] = []
        self.results: List[Dict] = []

    def load_tasks(self, category: str | None = None) -> None:
        """加载任务

        Args:
            category: 可选，筛选特定类别 (如 "01_Productivity_Flow")
        """
        self.tasks = []

        # Get the repos/wildclawbench path
        wildclawbench_repo = self.wildclawbench_dir

        for category_dir in sorted((wildclawbench_repo / "tasks").iterdir()):
            if not category_dir.is_dir():
                continue
            if category and category_dir.name != category:
                continue

            for task_file in sorted(category_dir.glob("*_task_*.md")):
                try:
                    task_data = parse_task_md(task_file)
                    task = WildClawTask(
                        task_id=task_data["task_id"],
                        name=task_data.get("name", task_file.stem),
                        category=task_data["category"],
                        prompt=task_data["prompt"],
                        timeout_seconds=task_data["timeout_seconds"],
                        workspace_path=task_data["workspace_path"],
                        skills_path=task_data["skills_path"],
                        automated_checks=task_data["automated_checks"],
                        env=task_data["env"],
                        skills=task_data["skills"],
                        warmup=task_data["warmup"],
                        file_path=task_data["file_path"],
                    )
                    self.tasks.append(task)
                except Exception as e:
                    logger.warning(f"Failed to load task {task_file}: {e}")

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
        if task_ids:
            tasks_to_run = [t for t in self.tasks if t.task_id in task_ids]
        else:
            tasks_to_run = self.tasks

        logger.info(f"Running benchmark on {len(tasks_to_run)} tasks ({runs_per_task} run(s) per task)")
        if not self.use_docker:
            logger.info("Docker disabled - running in no-docker mode")

        scores_by_task_id = {}

        for i, task in enumerate(tasks_to_run, 1):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Task {i}/{len(tasks_to_run)}: {task.task_id} ({task.name}) [{task.category}]")
            logger.info(f"{'=' * 60}")

            task_scores = []

            for run_index in range(runs_per_task):
                run_id = f"{task.task_id}_{run_index}"

                if self.use_docker:
                    score_result = self._run_with_docker(task, run_id, run_index)
                else:
                    score_result = self._run_without_docker(task, run_id, run_index)

                task_scores.append(score_result)

            # Aggregate scores for this task
            valid_scores = [s["overall_score"] for s in task_scores if "overall_score" in s]
            if valid_scores:
                scores_by_task_id[task.task_id] = {
                    "task_name": task.name,
                    "category": task.category,
                    "runs": task_scores,
                    "mean": statistics.mean(valid_scores),
                    "std": statistics.stdev(valid_scores) if len(valid_scores) > 1 else 0.0,
                    "min": min(valid_scores),
                    "max": max(valid_scores),
                }
            else:
                # All runs failed
                scores_by_task_id[task.task_id] = {
                    "task_name": task.name,
                    "category": task.category,
                    "runs": task_scores,
                    "mean": 0.0,
                    "std": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                }

        # Generate report
        return self._generate_report(scores_by_task_id, tasks_to_run)

    def _run_with_docker(self, task: WildClawTask, run_id: str, run_index: int) -> Dict[str, Any]:
        """使用 Docker 运行单个任务"""
        container_id = None
        try:
            # Step 1: Setup Docker container
            container_id = f"wildclaw_{run_id}"
            logger.info(f"[{run_id}] Starting container {container_id}")

            remove_container(container_id)

            start_container(
                task_id=container_id,
                workspace_path=task.workspace_path,
                extra_env=task.env,
            )

            setup_workspace(container_id)

            if task.skills.strip():
                setup_skills(container_id, task.skills, task.skills_path)

            if task.warmup.strip():
                run_warmup(container_id, task.warmup)

            # Step 2: Run NanoBotAgent on HOST
            logger.info(f"[{run_id}] Running NanoBotAgent on host workspace: {task.workspace_path}")

            results_dir = Path(task.workspace_path) / "results"
            results_dir.mkdir(parents=True, exist_ok=True)

            try:
                result = self.agent.execute(
                    task.prompt,
                    run_id,
                    workspace=Path(task.workspace_path),
                )
            except Exception as e:
                logger.warning(f"[{run_id}] Agent execution failed: {e}")
                result = AgentResult(status="error", error=str(e))

            result.workspace = task.workspace_path

            transcript_path = self.output_dir / "transcripts" / f"{run_id}.jsonl"
            result.save_transcript(transcript_path)

            # Step 3: Run grading in container
            logger.info(f"[{run_id}] Running grading in container")
            scores = run_grading(container_id, task.automated_checks, self.output_dir)

            collect_output_from_container(container_id, self.output_dir)

            return self._build_score_result(task, run_index, result, scores)

        except Exception as e:
            logger.error(f"[{run_id}] Task execution error: {e}")
            return {
                "task_id": task.task_id,
                "run_index": run_index,
                "status": "error",
                "error": str(e),
            }

        finally:
            if container_id:
                try:
                    remove_container(container_id)
                    logger.info(f"[{run_id}] Container cleaned up")
                except Exception as e:
                    logger.warning(f"[{run_id}] Failed to cleanup container: {e}")

    def _run_without_docker(self, task: WildClawTask, run_id: str, run_index: int) -> Dict[str, Any]:
        """不使用 Docker 运行单个任务 - 用于无法安装 Docker 的环境"""
        workspace_path = Path(task.workspace_path)

        try:
            # Step 1: Setup workspace locally
            logger.info(f"[{run_id}] Setting up local workspace: {workspace_path}")

            # Create tmp_workspace directory locally (simulates container's /tmp_workspace)
            tmp_workspace = workspace_path.parent / "tmp_workspace"
            if tmp_workspace.exists():
                shutil.rmtree(tmp_workspace)
            shutil.copytree(workspace_path, tmp_workspace, dirs_exist_ok=True)
            logger.info(f"[{run_id}] Copied workspace to {tmp_workspace}")

            # Step 2: Run warmup commands locally
            if task.warmup.strip():
                logger.info(f"[{run_id}] Running warmup commands locally")
                commands = [
                    line.strip()
                    for line in task.warmup.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                for cmd in commands:
                    logger.info(f"[{run_id}] warmup: {cmd}")
                    r = subprocess.run(cmd, shell=True, cwd=str(workspace_path), capture_output=True, text=True)
                    if r.returncode != 0:
                        logger.warning(f"[{run_id}] warmup command failed: {cmd}\n{r.stderr}")

            # Step 3: Run NanoBotAgent
            logger.info(f"[{run_id}] Running NanoBotAgent on workspace: {workspace_path}")

            results_dir = workspace_path / "results"
            results_dir.mkdir(parents=True, exist_ok=True)

            try:
                result = self.agent.execute(
                    task.prompt,
                    run_id,
                    workspace=workspace_path,
                )
            except Exception as e:
                logger.warning(f"[{run_id}] Agent execution failed: {e}")
                result = AgentResult(status="error", error=str(e))

            result.workspace = str(workspace_path)

            transcript_path = self.output_dir / "transcripts" / f"{run_id}.jsonl"
            result.save_transcript(transcript_path)

            # Step 4: Run grading locally
            logger.info(f"[{run_id}] Running grading locally")
            scores = self._run_grading_local(task, workspace_path)

            return self._build_score_result(task, run_index, result, scores)

        except Exception as e:
            logger.error(f"[{run_id}] Task execution error: {e}")
            return {
                "task_id": task.task_id,
                "run_index": run_index,
                "status": "error",
                "error": str(e),
            }

        finally:
            # Cleanup tmp_workspace
            tmp_workspace = workspace_path.parent / "tmp_workspace"
            if tmp_workspace.exists():
                shutil.rmtree(tmp_workspace, ignore_errors=True)

    def _run_grading_local(self, task: WildClawTask, workspace_path: Path) -> dict:
        """在本地运行 grading（不使用 Docker）"""
        tmp_workspace = workspace_path.parent / "tmp_workspace"

        runner_code = "\n".join([
            "import json, sys",
            task.automated_checks,
            "",
            f'result = grade(transcript=[], workspace_path="{tmp_workspace}")',
            "print(json.dumps(result))",
        ]) + "\n"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(runner_code)
            tmp_host = f.name

        try:
            r = subprocess.run(
                ["python3", tmp_host],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode != 0:
                logger.error(f"[grading] Script execution failed: {r.stderr}")
                return {"error": f"grading script failed: {r.stderr}"}

            try:
                scores = json.loads(r.stdout.strip())
            except json.JSONDecodeError:
                scores = None
                for line in reversed(r.stdout.strip().splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            scores = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            continue
                if scores is None:
                    logger.error(f"[grading] Failed to parse grading result\nstdout: {r.stdout[:500]}")
                    return {"error": "json parse failed"}

        finally:
            Path(tmp_host).unlink(missing_ok=True)

        # Save scores
        score_path = self.output_dir / "score.json"
        score_path.parent.mkdir(parents=True, exist_ok=True)
        score_path.write_text(json.dumps(scores, indent=2, ensure_ascii=False), encoding="utf-8")

        return scores

    def _build_score_result(self, task: WildClawTask, run_index: int, result: AgentResult, scores: dict) -> Dict[str, Any]:
        """构建评分结果"""
        if "error" in scores:
            return {
                "task_id": task.task_id,
                "run_index": run_index,
                "status": "error",
                "scores": scores,
                "error": scores.get("error", "grading failed"),
                "usage": result.usage,
            }
        else:
            numeric_scores = {k: v for k, v in scores.items() if isinstance(v, (int, float))}
            overall = numeric_scores.get(
                "overall_score",
                sum(numeric_scores.values()) / len(numeric_scores) if numeric_scores else 0
            )

            logger.info(f"[{task.task_id}_{run_index}] {format_scores(task.task_id, scores)}")

            return {
                "task_id": task.task_id,
                "run_index": run_index,
                "status": "success",
                "scores": scores,
                "overall_score": overall,
                "usage": result.usage,
                "execution_time": result.execution_time,
            }

    def _generate_report(self, scores_by_task_id: Dict, tasks_to_run: List[WildClawTask]) -> Dict[str, Any]:
        """生成报告"""
        all_scores = [scores_by_task_id[tid]["mean"] for tid in scores_by_task_id]
        total_score = sum(all_scores) / len(all_scores) if all_scores else 0

        category_scores: Dict[str, Dict] = {}
        for task in tasks_to_run:
            cat = task.category
            if cat not in category_scores:
                category_scores[cat] = {"earned": 0.0, "count": 0, "tasks": []}

            score = scores_by_task_id.get(task.task_id, {}).get("mean", 0.0)
            category_scores[cat]["earned"] += score
            category_scores[cat]["count"] += 1
            category_scores[cat]["tasks"].append(task.task_id)

        category_averages = {}
        for cat, data in category_scores.items():
            category_averages[cat] = data["earned"] / data["count"] if data["count"] > 0 else 0

        logger.info("\n" + "=" * 60)
        logger.info("WILDCLAWBENCH SCORE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Overall Score: {total_score:.2f}")
        logger.info(f"Total Tasks: {len(scores_by_task_id)}")
        logger.info("")
        logger.info(f"{'Category':<35} {'Score':>10} {'Tasks':>10}")
        logger.info("-" * 60)
        for cat in sorted(category_averages.keys()):
            data = category_scores[cat]
            logger.info(f"{cat:<35} {category_averages[cat]:>9.2f} {data['count']:>10}")

        result = {
            "benchmark": "wildclawbench",
            "timestamp": time.time(),
            "overall_score": round(total_score, 2),
            "total_tasks": len(scores_by_task_id),
            "category_scores": {
                cat: {
                    "score": round(category_averages[cat], 2),
                    "count": category_scores[cat]["count"],
                }
                for cat in category_scores
            },
            "task_scores": {
                tid: {
                    "task_name": data["task_name"],
                    "category": data["category"],
                    "mean": round(data["mean"], 2),
                    "std": round(data["std"], 2),
                }
                for tid, data in scores_by_task_id.items()
            },
        }

        run_id = f"{int(time.time() * 1000):013d}"
        output_path = self.output_dir / f"wildclawbench_{run_id}.json"
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

        logger.info(f"\nResults saved to: {output_path}")

        return result
