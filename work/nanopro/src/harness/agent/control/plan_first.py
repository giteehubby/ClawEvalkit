"""
PlanFirst 模块 - 任务开始前生成执行计划
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("control.plan_first")


@dataclass
class PlanStep:
    """计划步骤"""
    step_id: int
    action: str
    tool: str | None = None
    expected_outcome: str | None = None
    rationale: str | None = None


@dataclass
class ExecutionPlan:
    """执行计划"""
    task: str
    steps: list[PlanStep] = field(default_factory=list)
    raw_plan: str | None = None
    created_at: float = 0.0

    def to_string(self) -> str:
        if not self.steps:
            return self.raw_plan or ""
        lines = ["## Execution Plan"]
        for step in self.steps:
            if step.rationale:
                lines.append(f"{step.step_id}. [{step.tool or '思考'}] {step.action} - {step.rationale}")
            else:
                lines.append(f"{step.step_id}. [{step.tool or '思考'}] {step.action}")
        return "\n".join(lines)

    def to_context(self) -> str:
        """转换为注入到 prompt 的格式"""
        if not self.steps:
            return ""
        lines = ["[EXECUTION PLAN]", f"Task: {self.task}", ""]
        for step in self.steps:
            lines.append(f"  Step {step.step_id}: {step.action}")
            if step.expected_outcome:
                lines.append(f"    Expected: {step.expected_outcome}")
        lines.append("[/EXECUTION PLAN]")
        return "\n".join(lines)


class PlanFirst:
    """Plan-first 控制模块"""

    def __init__(self, config: "PlanFirstConfig", llm_client: Any):
        self.config = config
        self.llm_client = llm_client
        self.current_plan: ExecutionPlan | None = None
        self.plan_history: list[ExecutionPlan] = []

    def should_generate_plan(self, trigger_reason: str) -> bool:
        """判断是否应该生成计划"""
        if not self.config.enabled:
            return False

        if self.config.trigger == "always":
            return True
        elif self.config.trigger == "task_start":
            return trigger_reason == "task_start"
        elif self.config.trigger == "on_failure":
            return trigger_reason == "failure"
        return False

    async def generate_plan(self, task: str, context: str = "") -> ExecutionPlan:
        """生成执行计划"""
        import time

        prompt = self._build_plan_prompt(task, context)

        try:
            response = await self.llm_client.complete(
                prompt=prompt,
                max_tokens=self.config.max_plan_length,
                temperature=0.3,  # 较低温度保证计划稳定性
            )

            plan_text = response.strip() if response else ""
            plan = self._parse_plan(task, plan_text)
            plan.created_at = time.time()
            self.current_plan = plan
            self.plan_history.append(plan)
            logger.info(f"Generated plan with {len(plan.steps)} steps")
            return plan
        except Exception as e:
            logger.warning(f"Plan generation failed: {e}")
            # 返回空计划
            return ExecutionPlan(task=task, raw_plan="")

    def _build_plan_prompt(self, task: str, context: str) -> str:
        """构建计划生成 prompt"""
        return f"""You are an execution planner. Break down the following task into clear, actionable steps.

Task: {task}

{context}

Generate a concise execution plan (max {self.config.max_plan_length} tokens). Format:
## Plan
1. [Action] - Brief rationale
2. [Action] - Brief rationale
...

Focus on:
- Required tools in correct order
- Expected outcomes of each step
- Critical checkpoints
"""

    def _parse_plan(self, task: str, plan_text: str) -> ExecutionPlan:
        """解析计划文本为结构化格式"""
        import re

        plan = ExecutionPlan(task=task, raw_plan=plan_text)

        # 简单解析：按行处理，以数字开头的是步骤
        lines = plan_text.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 匹配 "1. [Tool] Action" 或 "1. Action"
            match = re.match(r"^\d+\.\s*(?:\[([^\]]+)\])?\s*(.+?)(?:\s*-\s*(.+))?$", line)
            if match:
                tool = match.group(1)
                action = match.group(2)
                rationale = match.group(3)

                step = PlanStep(
                    step_id=len(plan.steps) + 1,
                    action=action,
                    tool=tool,
                    rationale=rationale,
                )
                plan.steps.append(step)

        return plan

    def get_current_plan(self) -> ExecutionPlan | None:
        """获取当前计划"""
        return self.current_plan

    def clear_plan(self) -> None:
        """清除当前计划"""
        self.current_plan = None

    def clear(self) -> None:
        """清除当前计划和历史"""
        self.current_plan = None
        self.plan_history.clear()
