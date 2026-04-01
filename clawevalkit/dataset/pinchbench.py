"""PinchBench — 23 个任务，NanoBotAgent 执行 + 内嵌规则评分。

评分方式: 解析 task markdown → NanoBotAgent 执行 → 内嵌 grade() 函数评分 (0~100)。
部分模型有官方已跑出的分数，直接使用。

任务格式: 每个 task 是一个 markdown 文件，包含:
  - YAML frontmatter (id, category, timeout)
  - ## Prompt (给 agent 的指令)
  - ## Automated Checks (内嵌 Python grade() 函数)
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from ..utils.nanobot import import_nanobot_agent
from .base import BaseBenchmark

OFFICIAL_SCORES = {
    "claude-sonnet": 86.9,
    "claude-opus": 86.3,
    "gemini-2.5-pro": 61.4,
    "gpt-4o": 64.7,
}


class PinchBench(BaseBenchmark):
    DISPLAY_NAME = "PinchBench"
    TASK_COUNT = 23
    SCORE_RANGE = "0-100"

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """运行 PinchBench 评测: 解析任务 → NanoBotAgent 执行 → grade() 评分。

        流程:
        1. 若模型有官方分数，直接返回
        2. 解析 tasks/ 目录下的 markdown 文件，提取 prompt 和 grade 函数
        3. 对每个任务：创建隔离 workspace → NanoBotAgent 执行 → 调用 grade() 评分
        4. 汇总所有任务的平均分
        """
        if model_key in OFFICIAL_SCORES:
            return {"score": OFFICIAL_SCORES[model_key], "passed": 0, "total": 23, "source": "official"}

        NanoBotAgent = import_nanobot_agent()
        tasks = self._load_tasks()
        if not tasks:
            return {"score": 0, "total": 0, "error": "no tasks found"}

        if sample and sample < len(tasks):
            import random
            random.seed(42)
            tasks = random.sample(tasks, sample)

        out_dir = self.results_dir / "pinchbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []

        for task in tasks:
            tid = task["id"]
            result_file = out_dir / f"{tid}.json"

            # 跳过已完成的任务
            if result_file.exists():
                try:
                    ex = json.loads(result_file.read_text())
                    if ex.get("status") == "success":
                        results.append(ex)
                        continue
                except Exception:
                    pass

            workspace = Path(f"/tmp/eval_pinch_{model_key}/{tid}")
            if workspace.exists():
                shutil.rmtree(workspace)
            workspace.mkdir(parents=True, exist_ok=True)

            r = {"task_id": tid, "model_key": model_key, "status": "error", "scores": {}, "mean": 0.0}

            try:
                agent = NanoBotAgent(
                    model=config["model"], api_url=config["api_url"],
                    api_key=config["api_key"], workspace=workspace,
                    timeout=task.get("timeout", 120),
                )
                result = agent.execute(
                    task["prompt"],
                    session_id=f"pinch_{model_key}_{tid}",
                )
                transcript = result.transcript if result.transcript else []

                # 执行内嵌的 grade() 函数
                if task.get("grade_code"):
                    scores = self._run_grade(task["grade_code"], transcript, str(workspace))
                    mean_score = sum(scores.values()) / len(scores) if scores else 0
                    r["status"] = "success"
                    r["scores"] = scores
                    r["mean"] = round(mean_score, 4)
                else:
                    # 无 grade 函数时，检查 agent 是否成功执行
                    r["status"] = "success" if result.status == "success" else "error"
                    r["mean"] = 1.0 if result.status == "success" else 0.0

            except Exception as e:
                r["error"] = str(e)[:300]

            result_file.write_text(json.dumps(r, indent=2, ensure_ascii=False))
            shutil.rmtree(workspace, ignore_errors=True)
            results.append(r)

        # 汇总：所有任务的平均分 × 100
        means = [r["mean"] for r in results if r.get("status") == "success"]
        overall = round(sum(means) / len(means) * 100, 1) if means else 0
        final = {"score": overall, "passed": len(means), "total": len(tasks), "details": results}
        self.save_result("pinchbench", model_key, final, "result.json")
        return final

    # 旧目录名 → 新 model key 映射
    LEGACY_KEYS = {
        "gemini-3.1-pro": "gemini-3-pro-preview-new",
    }

    def collect(self, model_key: str) -> dict | None:
        if model_key in OFFICIAL_SCORES:
            return {"score": OFFICIAL_SCORES[model_key], "total": 23, "source": "official"}
        result_dir = self._find_result_dir("pinchbench")
        if not result_dir:
            return None
        for key in [model_key, self.LEGACY_KEYS.get(model_key, "")]:
            if not key:
                continue
            result_f = result_dir / key / "result.json"
            if result_f.exists():
                try:
                    data = json.loads(result_f.read_text())
                    score = data.get("score")
                    if score is not None:
                        return {"score": score, "total": 23}
                except Exception:
                    pass
        return None

    def _load_tasks(self) -> list:
        """解析 tasks/*.md → [{"id", "prompt", "grade_code", "timeout"}, ...]

        每个 task markdown 结构:
        - YAML frontmatter（--- ... ---）: id, timeout_seconds 等
        - ## Prompt 部分: 给 agent 的指令
        - ## Automated Checks 中的 ```python ... ```: grade() 函数代码
        """
        tasks_dir = self.base_dir / "benchmarks" / "pinchbench" / "tasks"
        if not tasks_dir.exists():
            return []

        tasks = []
        for md in sorted(tasks_dir.glob("*.md")):
            content = md.read_text(encoding="utf-8")

            # 解析 frontmatter
            frontmatter = {}
            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                for line in fm_match.group(1).splitlines():
                    if ":" in line:
                        key, val = line.split(":", 1)
                        frontmatter[key.strip()] = val.strip()

            # 提取 ## Prompt 部分
            prompt = ""
            prompt_match = re.search(
                r"## Prompt\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL
            )
            if prompt_match:
                prompt = prompt_match.group(1).strip()

            # 提取 ## Automated Checks 中的 Python 代码
            grade_code = ""
            checks_match = re.search(
                r"## Automated Checks.*?```python\s*\n(.*?)```", content, re.DOTALL
            )
            if checks_match:
                grade_code = checks_match.group(1).strip()

            tid = frontmatter.get("id", md.stem)
            timeout = int(frontmatter.get("timeout_seconds", "120"))

            tasks.append({
                "id": tid,
                "prompt": prompt,
                "grade_code": grade_code,
                "timeout": timeout,
            })

        return tasks

    def _run_grade(self, grade_code: str, transcript: list, workspace_path: str) -> dict:
        """执行内嵌的 grade(transcript, workspace_path) 函数，返回评分字典。

        grade_code 是从 task markdown 的 ```python 块中提取的代码，
        定义了一个 grade(transcript, workspace_path) → dict 函数。
        """
        namespace = {}
        try:
            exec(grade_code, namespace)
            if "grade" in namespace:
                return namespace["grade"](transcript, workspace_path)
        except Exception:
            pass
        return {}
