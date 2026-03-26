"""
SkillBench 适配器 - 使用 NanoBot Agent

SkillBench 核心是比较 baseline（无技能）vs augmented（有技能）的差异。
适配器内部 hardcode 了要跑的 packs 和 skills。
"""

import json
import logging
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_scripts_dir = Path(__file__).parent
sys.path.insert(0, str(_scripts_dir))

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from agent.base import AgentResult, BaseAgent

logger = logging.getLogger("adapter.skillbench")


# Hardcoded packs and skills configuration
PACKS = [
    {"pack": "coding/swe-lite", "skills": ["calc-fixer", "slugify-fixer"]},
    {"pack": "docs/text-lite", "skills": ["doc-filler"]},
    {"pack": "coding/tool-use", "skills": []},
]


def _load_skill_instructions(skill_path: Path | None) -> str:
    """加载技能指令（跳过 frontmatter）"""
    if not skill_path or not skill_path.exists():
        return ""
    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        return f"\n\n[Skill Instructions]\n{content}\n[/Skill Instructions]\n\n"
    return ""


class Task:
    """SkillBench 任务对象"""
    def __init__(self, task_id: str, instructions: str, task_dir: Path, repo_dir: Path):
        self.task_id = task_id
        self.instructions = instructions
        self.task_dir = task_dir
        self.repo_dir = repo_dir


class TaskLoader:
    """加载 SkillBench 任务"""
    def __init__(self, pack_dir: Path):
        self.pack_dir = pack_dir

    def load_all_tasks(self) -> List[Task]:
        manifest_file = self.pack_dir / "manifest.yaml"
        if not manifest_file.exists():
            logger.error(f"Manifest not found: {manifest_file}")
            return []

        if not HAS_YAML:
            logger.error("PyYAML is required")
            return []

        tasks = []
        try:
            data = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            return []

        for task_data in data.get("tasks", []):
            task_id = task_data.get("id")
            task_path = task_data.get("path", f"tasks/{task_id}")
            repo_path = task_data.get("repo_path", f"{task_path}/repo")
            instructions = task_data.get("instructions", "")

            task_dir = self.pack_dir / task_path
            repo_dir = self.pack_dir / repo_path

            if not task_dir.exists() or not repo_dir.exists():
                logger.warning(f"Task not found: {task_id}")
                continue

            task_md = task_dir / "TASK.md"
            if task_md.exists():
                instructions = task_md.read_text(encoding="utf-8")

            tasks.append(Task(task_id, instructions, task_dir, repo_dir))

        return tasks


def run_unittest(workspace: Path) -> tuple[bool, str]:
    """运行测试，返回 (passed, notes)"""
    try:
        result = subprocess.run(
            ["python", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            cwd=workspace,
            capture_output=True,
            timeout=300,
        )
        passed = result.returncode == 0
        try:
            stdout = result.stdout.decode("utf-8", errors="ignore")[-500:]
            stderr = result.stderr.decode("utf-8", errors="ignore")[-500:]
        except Exception:
            stdout = str(result.stdout)[-500:] if result.stdout else ""
            stderr = str(result.stderr)[-500:] if result.stderr else ""

        if passed:
            return True, "All tests passed"
        else:
            return False, f"Tests failed. stdout: {stdout[:200]}, stderr: {stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, "Evaluation timed out"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


class _SingleModeAdapter:
    """内部adapter：跑单个 pack 的单个 mode（baseline 或 augmented）"""

    def __init__(
        self,
        agent: BaseAgent,
        pack_dir: Path,
        mode: str,
        skill_path: Optional[Path],
        output_dir: Path,
    ):
        self.agent = agent
        self.pack_dir = pack_dir
        self.mode = mode
        self.skill_path = skill_path
        self.output_dir = output_dir
        self.skill_instructions = ""
        if mode == "augmented" and skill_path:
            self.skill_instructions = _load_skill_instructions(skill_path)

    def _prepare_workspace(self, task: Task) -> Path:
        """准备工作空间"""
        base_temp = Path(tempfile.gettempdir())
        workspace = base_temp / "benchmarks" / "skillbench" / f"{task.task_id}_{self.mode}"
        workspace.mkdir(parents=True, exist_ok=True)

        for item in workspace.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        if task.repo_dir.exists():
            for item in task.repo_dir.iterdir():
                dest = workspace / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

        if self.skill_path and self.skill_path.exists():
            skill_dest = workspace / ".claude" / "skills"
            skill_dest.mkdir(parents=True, exist_ok=True)
            for item in self.skill_path.iterdir():
                if item.is_dir():
                    shutil.copytree(item, skill_dest / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, skill_dest / item.name)

        return workspace

    def _count_tool_calls(self, transcript: list) -> int:
        count = 0
        if not transcript:
            return 0
        for entry in transcript:
            if entry.get("type") == "message":
                msg = entry.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "toolCall":
                            count += 1
        return count

    def run_single_task(self, task: Task) -> Dict[str, Any]:
        workspace = self._prepare_workspace(task)
        logger.info(f"[{self.mode}] Running {task.task_id}...")
        start_time = time.time()

        instructions = self.skill_instructions + task.instructions

        # 记录当前 transcript 长度，用于只统计本次任务的工具调用
        transcript_before = len(self.agent._transcript)

        try:
            result = self.agent.execute(instructions, f"{task.task_id}_{self.mode}", workspace=workspace)
        except Exception as e:
            logger.warning(f"Task execution failed: {e}")
            result = AgentResult(status="error", error=str(e))

        execution_time = time.time() - start_time
        passed, notes = run_unittest(workspace)

        # 只统计本次新增的 transcript 条目，避免跨任务累积
        transcript_after = len(self.agent._transcript)
        current_task_transcript = self.agent._transcript[transcript_before:transcript_after]
        tool_calls = self._count_tool_calls(current_task_transcript)

        # 保存 transcript
        transcript_path = self.output_dir / "transcripts" / f"{task.task_id}_{self.mode}.jsonl"
        # 保存本次任务的 transcript 片段
        result.workspace = str(workspace)
        tmp_result = AgentResult(
            status=result.status,
            content=result.content,
            transcript=current_task_transcript,
            usage=result.usage,
            workspace=result.workspace,
            execution_time=result.execution_time,
            error=result.error,
        )
        tmp_result.save_transcript(transcript_path)
        logger.info(f"  Transcript saved: {transcript_path}")
        usage = result.usage or {}
        has_error = bool(result.error)

        return {
            "task_id": task.task_id,
            "mode": self.mode,
            "status": "passed" if passed else "failed",
            "passed": passed,
            "execution_time": execution_time,
            "notes": notes,
            "workspace": str(workspace),
            "tool_calls": tool_calls,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "has_error": has_error,
        }

    def run(self, task_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """运行单个 mode"""
        tasks = TaskLoader(self.pack_dir).load_all_tasks()
        if task_ids:
            tasks = [t for t in tasks if t.task_id in task_ids]

        logger.info(f"Running {self.mode} on {len(tasks)} tasks")

        results = []
        for i, task in enumerate(tasks, 1):
            logger.info(f"\n[{i}/{len(tasks)}] {task.task_id}")
            result = self.run_single_task(task)
            results.append(result)
            status = "PASS" if result["passed"] else "FAIL"
            logger.info(f"[{self.mode}] {task.task_id}: {status} - {result['notes']}")

        return self._aggregate(results)

    def _aggregate(self, results: List[Dict]) -> Dict[str, Any]:
        total = len(results)
        passed_count = sum(1 for r in results if r["passed"])

        runtimes = [r["execution_time"] for r in results if r.get("execution_time")]
        avg_runtime = round(sum(runtimes) / len(runtimes), 3) if runtimes else 0

        total_tokens = sum(r.get("total_tokens", 0) for r in results)
        avg_total_tokens = round(total_tokens / total, 3) if total else 0

        total_tool_calls = sum(r.get("tool_calls", 0) for r in results)
        avg_tool_calls = round(total_tool_calls / total, 3) if total else 0

        skill_name = self.skill_path.name if self.skill_path else "none"
        output_path = self.output_dir / f"skillbench_{self.mode}_{skill_name}_{int(time.time())}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

        return {
            "mode": self.mode,
            "total": total,
            "passed": passed_count,
            "failed": total - passed_count,
            "success_rate": round(passed_count / total, 3) if total else 0,
            "avg_runtime_s": avg_runtime,
            "avg_total_tokens": avg_total_tokens,
            "avg_tool_calls": avg_tool_calls,
            "total_tokens": total_tokens,
            "total_tool_calls": total_tool_calls,
            "results": results,
        }


class SkillBenchAdapter:
    """
    SkillBench 适配器。

    内部 hardcode 了 packs 和 skills，跑完所有 pack 后生成汇总报告。
    run() 返回标准结果结构（benchmark, overall_score, total_tasks, passed_tasks 等）。
    """

    def __init__(
        self,
        agent: BaseAgent,
        skillbench_dir: Path,
        output_dir: Path,
    ):
        self.agent = agent
        self.skillbench_dir = skillbench_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> Dict[str, Any]:
        """
        运行所有 packs。

        Returns:
            Dict: 包含 benchmark、overall_score、total_tasks、passed_tasks、
                  runs（每个 pack 的详细结果）等字段。
        """
        timestamp = int(time.time())
        all_pack_results = []

        for pack_config in PACKS:
            pack_name = pack_config["pack"]
            skill_names = pack_config["skills"]

            pack_dir = self.skillbench_dir / "packs" / pack_name
            if not pack_dir.exists():
                logger.warning(f"Pack not found: {pack_dir}, skipping...")
                continue

            tasks = TaskLoader(pack_dir).load_all_tasks()
            if not tasks:
                logger.warning(f"No tasks loaded for {pack_name}, skipping...")
                continue

            logger.info(f"\n{'#'*60}")
            logger.info(f"# Running: {pack_name} (skills: {skill_names or 'None'})")
            logger.info(f"# Tasks: {len(tasks)}")
            logger.info(f"{'#'*60}")

            pack_result = self._run_pack(pack_dir, pack_name, skill_names)
            all_pack_results.append(pack_result)

            # pack 间 sleep
            time.sleep(10)

        # 汇总
        total_baseline_passed = sum(r["baseline"]["passed"] for r in all_pack_results)
        total_baseline = sum(r["baseline"]["total"] for r in all_pack_results)

        full_report = {
            "benchmark": "skillbench",
            "version": "0.1.0",
            "timestamp": timestamp,
            "runs": all_pack_results,
            "summary": {
                "total_tasks": total_baseline,
                "total_baseline_passed": total_baseline_passed,
                "overall_baseline_success_rate": (
                    round(total_baseline_passed / total_baseline, 3) if total_baseline else None
                ),
            },
        }

        report_path = self.output_dir / f"skillbench_full_{timestamp}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(full_report, f, indent=2, ensure_ascii=False)

        # 打印汇总
        self._print_summary(all_pack_results, total_baseline_passed, total_baseline, report_path)

        # 返回标准结构，兼容 run.py 的打印逻辑
        return {
            "benchmark": "skillbench",
            "overall_score": (
                round(total_baseline_passed / total_baseline * 100, 2) if total_baseline else 0
            ),
            "passed_tasks": total_baseline_passed,
            "total_tasks": total_baseline,
            "full_report": full_report,
        }

    def _run_pack(
        self,
        pack_dir: Path,
        pack_name: str,
        skill_names: List[str],
    ) -> Dict[str, Any]:
        """运行单个 pack：遍历 skills 跑 augmented，末了跑 baseline"""
        skill_results: Dict[str, Dict] = {}

        for skill_name in skill_names:
            skill_path = pack_dir / "skills" / skill_name
            if not skill_path.exists():
                logger.warning(f"Skill not found: {skill_path}, skipping...")
                continue

            adapter = _SingleModeAdapter(
                agent=self.agent,
                pack_dir=pack_dir,
                mode="augmented",
                skill_path=skill_path,
                output_dir=self.output_dir,
            )
            result = adapter.run()
            skill_results[skill_name] = result

            agg = result
            logger.info(
                f"  [{skill_name}] {agg['passed']}/{agg['total']} passed, "
                f"success_rate={agg['success_rate']}, "
                f"avg_runtime={agg['avg_runtime_s']}s, "
                f"avg_tokens={agg['avg_total_tokens']}, "
                f"avg_tool_calls={agg['avg_tool_calls']}"
            )

            time.sleep(10)

        # baseline
        baseline_adapter = _SingleModeAdapter(
            agent=self.agent,
            pack_dir=pack_dir,
            mode="baseline",
            skill_path=None,
            output_dir=self.output_dir,
        )
        baseline_result = baseline_adapter.run()
        b_agg = baseline_result
        logger.info(
            f"  [baseline] {b_agg['passed']}/{b_agg['total']} passed, "
            f"success_rate={b_agg['success_rate']}, "
            f"avg_runtime={b_agg['avg_runtime_s']}s, "
            f"avg_tokens={b_agg['avg_total_tokens']}, "
            f"avg_tool_calls={b_agg['avg_tool_calls']}"
        )

        # delta
        delta = None
        if skill_results:
            main_skill_name = skill_names[0]
            main_skill = skill_results.get(main_skill_name)
            if main_skill:
                delta = {
                    k: round(main_skill[k] - b_agg.get(k, 0), 3)
                    for k in ["success_rate", "avg_runtime_s", "avg_total_tokens", "avg_tool_calls"]
                }
                logger.info(
                    f"  [delta vs {main_skill_name}] success_rate={delta.get('success_rate')}, "
                    f"avg_runtime={delta.get('avg_runtime_s')}s, "
                    f"avg_tokens={delta.get('avg_total_tokens')}, "
                    f"avg_tool_calls={delta.get('avg_tool_calls')}"
                )

        return {
            "pack": pack_name,
            "skills": skill_results,
            "baseline": baseline_result,
            "delta": delta,
        }

    def _print_summary(
        self,
        all_pack_results: List[Dict],
        total_baseline_passed: int,
        total_baseline: int,
        report_path: Path,
    ) -> None:
        logger.info(f"\n{'=' * 80}")
        logger.info("FULL SKILLBENCH REPORT")
        logger.info(f"{'=' * 80}")
        logger.info(f"Timestamp: {int(time.time())}")
        logger.info(
            f"\n{'Pack':<20} {'Skill':<25} {'Mode':<12} {'Pass':<8} {'Succ%':<8} "
            f"{'AvgTime':<10} {'AvgTokens':<12} {'AvgTools':<10}"
        )
        logger.info("-" * 115)

        for r in all_pack_results:
            pack = r["pack"]
            b = r["baseline"]
            logger.info(
                f"{pack:<20} {'-':<25} {'baseline':<12} {b['passed']}/{b['total']:<6} "
                f"{b['success_rate']:<8} {b['avg_runtime_s']:<10} "
                f"{b['avg_total_tokens']:<12} {b['avg_tool_calls']:<10}"
            )
            for skill_name, s in r["skills"].items():
                logger.info(
                    f"{'':<20} {skill_name:<25} {'augmented':<12} "
                    f"{s['passed']}/{s['total']:<6} {s['success_rate']:<8} "
                    f"{s['avg_runtime_s']:<10} {s['avg_total_tokens']:<12} "
                    f"{s['avg_tool_calls']:<10}"
                )
            d = r["delta"]
            if d:
                logger.info(
                    f"{'':<20} {'':<25} {'delta':<12} {'':<8} "
                    f"{d.get('success_rate', ''):<8} {d.get('avg_runtime_s', ''):<10} "
                    f"{d.get('avg_total_tokens', ''):<12} {d.get('avg_tool_calls', ''):<10}"
                )

        logger.info("-" * 115)
        logger.info(f"\nTOTAL: {total_baseline_passed}/{total_baseline} passed overall")
        logger.info(f"Full report: {report_path}")
