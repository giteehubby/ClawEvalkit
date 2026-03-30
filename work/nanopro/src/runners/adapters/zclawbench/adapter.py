"""
ZClawBench 适配器 (no-docker 风格)。

ZClawBench: 116 tasks × 6 categories, 评估 LLM Agent 在 OpenClaw-style 工作流中的表现。
数据来源: HuggingFace datasets (zai-org/ZClawBench)

评测模式:
  1. [离线分析]   加载已有轨迹，用 Judge Model 评估各模型表现
  2. [重新运行]  用自己的 agent 重新跑任务，再由 Judge Model 评分

grading 方式: Judge Model (doubao-seed-1.8) 评估，无自动化 grading 脚本。
这与 WildClawBench 的 automated_checks 不同——ZClawBench 的任务依赖 LLM Judge 做质量评估。

不依赖 Docker，全部在本地执行。
"""

import json
import logging
import shutil
import statistics
import subprocess
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.harness.agent.base import AgentResult, BaseAgent
from src.runners.adapters.zclawbench.grading import (
    JudgeScore,
    get_ark_key,
    run_judge_eval,
    run_judge_eval_offline,
    format_judge_score,
)
from src.runners.adapters.zclawbench.task_loader import (
    ZClawBenchTask,
    ZClawBenchTaskLoader,
)

logger = logging.getLogger("adapter.zclawbench")


# ---------------------------------------------------------------------------
# Task 对象 (与 WildClawBench.Task 对齐)
# ---------------------------------------------------------------------------

@dataclass
class ZClawBenchTask:
    """ZClawBench 任务对象"""
    task_id: str
    name: str
    category: str
    prompt: str
    timeout_seconds: int
    workspace_path: str
    reference_trajectories: Dict[str, List[Dict]]
    tool_names: List[str]


# ---------------------------------------------------------------------------
# 主适配器
# ---------------------------------------------------------------------------

class ZClawBenchAdapter:
    """
    ZClawBench 适配器。

    支持两种运行模式:
    - offline:     加载 HuggingFace 已有轨迹，用 Judge Model 评估
    - rerun:      用 agent 重新执行任务，再用 Judge Model 评估

    不需要 Docker，全部在本地执行。
    """

    def __init__(
        self,
        agent: BaseAgent,
        output_dir: Optional[Path] = None,
        judge_model: str = "ep-20260113141316-sfsps",  # Doubao Seed 1.8 (from .env doubao_18_model_name)
    ):
        self.agent = agent
        self.output_dir = output_dir or Path("results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.judge_model = judge_model

        self.task_loader = ZClawBenchTaskLoader()
        self.tasks: List[ZClawBenchTask] = []
        self.results: List[Dict] = []

    # ---------------------------------------------------------------------------
    # 任务加载
    # ---------------------------------------------------------------------------

    def load_tasks(
        self,
        category: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """加载 ZClawBench 任务

        Args:
            category: 可选，筛选特定类别
            model_name: 可选，筛选特定模型的轨迹
        """
        raw_tasks = self.task_loader.load_all_tasks(category=category)
        self.tasks = [
            ZClawBenchTask(
                task_id=t.task_id,
                name=t.name,
                category=t.category,
                prompt=t.prompt,
                timeout_seconds=t.timeout_seconds,
                workspace_path=t.workspace_path,
                reference_trajectories=t.reference_trajectories,
                tool_names=t.tool_names,
            )
            for t in raw_tasks
        ]
        logger.info(f"Loaded {len(self.tasks)} tasks")

    # ---------------------------------------------------------------------------
    # 运行入口
    # ---------------------------------------------------------------------------

    def run(
        self,
        task_ids: Optional[List[str]] = None,
        runs_per_task: int = 1,
        mode: str = "offline",
        target_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        运行 ZClawBench 评估。

        Args:
            task_ids:  要运行的任务 ID 列表，None 表示全部
            runs_per_task: 每个任务运行次数
            mode:      "offline" (分析已有轨迹) 或 "rerun" (重新执行)
            target_model: 在 offline 模式下筛选特定模型轨迹
        """
        if task_ids:
            tasks_to_run = [t for t in self.tasks if t.task_id in task_ids]
        else:
            tasks_to_run = self.tasks

        logger.info(f"Running ZClawBench in {mode} mode on {len(tasks_to_run)} tasks")

        scores_by_task_id: Dict[str, Dict[str, Any]] = {}

        for i, task in enumerate(tasks_to_run, 1):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Task {i}/{len(tasks_to_run)}: {task.task_id} [{task.category}]")
            logger.info(f"{'=' * 60}")

            if mode == "offline":
                task_scores = self._run_offline(task, target_model=target_model)
            else:
                task_scores = self._run_rerun(task, runs_per_task=runs_per_task)

            # 聚合多轮结果
            valid = [s["overall_score"] for s in task_scores if "overall_score" in s]
            if valid:
                scores_by_task_id[task.task_id] = {
                    "task_name": task.name,
                    "category": task.category,
                    "runs": task_scores,
                    "mean": statistics.mean(valid),
                    "std": statistics.stdev(valid) if len(valid) > 1 else 0.0,
                    "min": min(valid),
                    "max": max(valid),
                }
            else:
                scores_by_task_id[task.task_id] = {
                    "task_name": task.name,
                    "category": task.category,
                    "runs": task_scores,
                    "mean": 0.0,
                    "std": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                }

        return self._generate_report(scores_by_task_id, tasks_to_run, mode)

    # ---------------------------------------------------------------------------
    # Offline 模式: 分析已有轨迹
    # ---------------------------------------------------------------------------

    def _run_offline(
        self,
        task: ZClawBenchTask,
        target_model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """离线分析: 用 Judge Model 评估 HuggingFace 上的已有轨迹"""
        api_key = get_ark_key(Path(__file__).parent.parent.parent)
        if not api_key:
            logger.error("ARK_API_KEY not found. Cannot run judge evaluation.")
            return []

        results = []
        for model_name, trajectory in task.reference_trajectories.items():
            if target_model and target_model.lower() not in model_name.lower():
                continue

            logger.info(f"  Evaluating {model_name} ...")

            score = run_judge_eval_offline(
                trajectory=trajectory,
                task_id=task.task_id,
                category=task.category,
                task_prompt=task.prompt,
                model_name=model_name,
                judge_model=self.judge_model,
                api_key=api_key,
            )

            logger.info(f"    {format_judge_score(score)}")
            results.append({
                "task_id": task.task_id,
                "model": score.model,
                "status": "success" if score.overall_score > 0 else "error",
                "scores": {
                    "task_completion": score.task_completion,
                    "tool_usage": score.tool_usage,
                    "reasoning": score.reasoning,
                    "answer_quality": score.answer_quality,
                    "overall_score": score.overall_score,
                },
                "justification": score.justification,
                "mode": "offline",
            })

            # 保存 transcript
            self._save_transcript(task.task_id, model_name, trajectory)

        return results

    # ---------------------------------------------------------------------------
    # Re-run 模式: 重新执行任务
    # ---------------------------------------------------------------------------

    def _run_rerun(
        self,
        task: ZClawBenchTask,
        runs_per_task: int = 1,
    ) -> List[Dict[str, Any]]:
        """重新执行任务: 用 agent 执行 + Judge Model 评分"""
        api_key = get_ark_key(Path(__file__).parent.parent.parent)
        if not api_key:
            logger.error("ARK_API_KEY not found. Cannot run judge evaluation.")
            return []

        results = []

        for run_index in range(runs_per_task):
            run_id = f"{task.task_id}_{run_index}"
            workspace = self._prepare_workspace(task, run_id)

            logger.info(f"  Run {run_index}: executing agent ...")

            try:
                result = self.agent.execute(
                    task.prompt,
                    run_id,
                    workspace=workspace,
                )
            except Exception as e:
                logger.warning(f"Agent execution failed: {e}")
                result = AgentResult(status="error", error=str(e))

            result.workspace = str(workspace)

            # 保存 transcript
            transcript_path = self.output_dir / "transcripts" / f"{run_id}.jsonl"
            result.save_transcript(transcript_path)

            # Judge 评估
            try:
                trajectory = result.transcript
                score = run_judge_eval(
                    trajectory=trajectory,
                    task_id=task.task_id,
                    category=task.category,
                    task_prompt=task.prompt,
                    judge_model=self.judge_model,
                    api_key=api_key,
                    model_name=self.agent.model_name if hasattr(self.agent, "model_name") else "agent",
                )
            except Exception as e:
                logger.error(f"Judge evaluation failed: {e}")
                score = None

            if score:
                logger.info(f"  Run {run_index}: {format_judge_score(score)}")
                results.append({
                    "task_id": task.task_id,
                    "run_index": run_index,
                    "status": "success" if score.overall_score > 0 else "error",
                    "scores": {
                        "task_completion": score.task_completion,
                        "tool_usage": score.tool_usage,
                        "reasoning": score.reasoning,
                        "answer_quality": score.answer_quality,
                        "overall_score": score.overall_score,
                    },
                    "justification": score.justification,
                    "usage": result.usage,
                    "execution_time": result.execution_time,
                    "mode": "rerun",
                })
            else:
                results.append({
                    "task_id": task.task_id,
                    "run_index": run_index,
                    "status": "error",
                    "error": "Judge evaluation failed",
                })

            # 清理临时 workspace
            self._cleanup_workspace(workspace)

        return results

    # ---------------------------------------------------------------------------
    # Workspace 管理 (no-docker 风格，模拟容器隔离)
    # ---------------------------------------------------------------------------

    def _prepare_workspace(self, task: ZClawBenchTask, run_id: str) -> Path:
        """
        准备本地工作空间（no-docker 风格）。

        与 WildClawBench._run_without_docker 对齐:
        - 创建 /tmp/zclawbench_workspace/{run_id} 目录
        - 不需要 setup.sh（ZClawBench 没有这个机制）
        """
        workspace = Path(f"/tmp/zclawbench_workspace/{run_id}")
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        # ZClawBench 没有输入文件，不需要复制

        logger.info(f"  Workspace prepared: {workspace}")
        return workspace

    def _cleanup_workspace(self, workspace: Path) -> None:
        """清理临时工作空间"""
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)

    # ---------------------------------------------------------------------------
    # Transcript 保存
    # ---------------------------------------------------------------------------

    def _save_transcript(
        self,
        task_id: str,
        model_name: str,
        trajectory: List[Dict],
    ) -> Path:
        """保存轨迹到 jsonl 文件"""
        transcript_dir = self.output_dir / "transcripts"
        transcript_dir.mkdir(parents=True, exist_ok=True)

        safe_model = model_name.replace(" ", "_").replace("/", "_")
        path = transcript_dir / f"{task_id}_{safe_model}.jsonl"

        with open(path, "w", encoding="utf-8") as f:
            for msg in trajectory:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        return path

    # ---------------------------------------------------------------------------
    # 报告生成
    # ---------------------------------------------------------------------------

    def _generate_report(
        self,
        scores_by_task_id: Dict[str, Dict[str, Any]],
        tasks_to_run: List[ZClawBenchTask],
        mode: str,
    ) -> Dict[str, Any]:
        """生成评估报告"""

        # 按 category 汇总
        category_scores: Dict[str, Dict[str, float]] = defaultdict(lambda: {"total": 0, "sum": 0.0})
        for task in tasks_to_run:
            cat = task.category
            score = scores_by_task_id.get(task.task_id, {}).get("mean", 0.0)
            category_scores[cat]["sum"] += score
            category_scores[cat]["total"] += 1

        category_avg = {
            cat: data["sum"] / data["total"] if data["total"] > 0 else 0.0
            for cat, data in category_scores.items()
        }

        # 全局平均
        all_means = [scores_by_task_id[t.task_id]["mean"] for t in tasks_to_run if t.task_id in scores_by_task_id]
        overall = sum(all_means) / len(all_means) if all_means else 0.0
        passed = sum(1 for s in all_means if s >= 0.6)

        # 按模型汇总（仅 offline 模式有多模型数据）
        model_scores: Dict[str, Dict[str, float]] = defaultdict(lambda: {"total": 0, "sum": 0.0})
        for task_data in scores_by_task_id.values():
            for run in task_data.get("runs", []):
                model = run.get("model", "unknown")
                score = run.get("scores", {}).get("overall_score", 0.0)
                if score > 0:
                    model_scores[model]["sum"] += score
                    model_scores[model]["total"] += 1

        model_avg = {
            m: data["sum"] / data["total"] if data["total"] > 0 else 0.0
            for m, data in model_scores.items()
        }

        # 打印摘要
        logger.info("\n" + "=" * 60)
        logger.info(f"  ZCLAWBENCH SCORE SUMMARY  [{mode} mode]")
        logger.info("=" * 60)
        logger.info(f"Overall Score: {overall:.2f}  ({passed}/{len(all_means)} tasks ≥0.6)")
        logger.info(f"Total Tasks:  {len(scores_by_task_id)}")
        logger.info("")

        if model_avg:
            logger.info(f"{'Model':<30} {'Score':>10} {'Tasks':>10}")
            logger.info("-" * 55)
            for m in sorted(model_avg.keys()):
                data = model_scores[m]
                logger.info(f"{m:<30} {model_avg[m]:>9.2f} {data['total']:>10}")

        logger.info("")
        logger.info(f"{'Category':<40} {'Score':>10} {'Tasks':>10}")
        logger.info("-" * 65)
        for cat in sorted(category_avg.keys()):
            data = category_scores[cat]
            logger.info(f"{cat:<40} {category_avg[cat]:>9.2f} {data['total']:>10}")

        # 构建结果
        result = {
            "benchmark": "zclawbench",
            "mode": mode,
            "timestamp": time.time(),
            "judge_model": self.judge_model,
            "overall_score": round(overall, 4),
            "passed_tasks": passed,
            "total_tasks": len(scores_by_task_id),
            "category_scores": {
                cat: {"score": round(category_avg[cat], 4), "count": category_scores[cat]["total"]}
                for cat in category_avg
            },
            "model_scores": {
                m: {"score": round(model_avg[m], 4), "total": int(model_scores[m]["total"])}
                for m in model_avg
            },
            "task_scores": {
                tid: {
                    "task_name": data["task_name"],
                    "category": data["category"],
                    "mean": round(data["mean"], 4),
                    "std": round(data["std"], 4),
                    "runs": data["runs"],
                }
                for tid, data in scores_by_task_id.items()
            },
        }

        run_id = f"{int(time.time() * 1000):013d}"
        output_path = self.output_dir / f"zclawbench_{mode}_{run_id}.json"
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"\nResults saved to: {output_path}")

        return result
