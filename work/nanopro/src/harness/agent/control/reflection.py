"""
FailureReflection 模块 - 失败后进行反思
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("control.reflection")


@dataclass
class ReflectionResult:
    """反思结果"""
    reflection_text: str
    root_cause: str | None = None
    suggested_correction: str | None = None
    should_retry: bool = True
    confidence: float = 0.5  # 0.0 - 1.0


@dataclass
class FailureRecord:
    """失败记录"""
    iteration: int
    tool_name: str | None
    error_message: str
    error_type: str
    timestamp: float
    context: str = ""


class FailureReflection:
    """失败反思模块

    专注于反思分析，帮助模型从失败中学习和恢复。
    """

    def __init__(self, config: "ReflectionConfig", llm_fn: Any | None = None):
        """初始化 FailureReflection。

        Args:
            config: ReflectionConfig 配置
            llm_fn: 异步 LLM 调用函数，签名为:
                    async def llm_fn(prompt: str, max_tokens: int, temperature: float) -> str
        """
        self.config = config
        self.llm_fn = llm_fn
        self.failure_history: list[FailureRecord] = []
        self.consecutive_failures = 0
        self.last_reflection_time = 0.0
        self._last_reflected_failure_count = 0

    def record_failure(
        self,
        iteration: int,
        tool_name: str | None,
        error_message: str,
        error_type: str = "unknown",
        context: str = "",
    ) -> None:
        """记录一次失败"""
        if not self.config.enabled:
            return

        record = FailureRecord(
            iteration=iteration,
            tool_name=tool_name,
            error_message=error_message,
            error_type=error_type,
            timestamp=time.time(),
            context=context,
        )
        self.failure_history.append(record)
        self.consecutive_failures += 1
        logger.debug(f"Recorded failure: {error_type} at iteration {iteration}")

    def record_success(self) -> None:
        """记录一次成功，重置连续失败计数"""
        self.consecutive_failures = 0

    def should_reflect(self) -> bool:
        """判断是否应该进行反思"""
        if not self.config.enabled:
            return False

        has_new_failure = len(self.failure_history) > self._last_reflected_failure_count
        if not has_new_failure:
            return False

        if self.config.trigger == "on_failure":
            return True
        elif self.config.trigger == "on_consecutive_failures":
            return self.consecutive_failures >= self.config.consecutive_failure_threshold
        elif self.config.trigger == "manual":
            return False  # 手动触发

        return False

    def _get_last_iteration(self) -> int:
        """获取最后一次失败的迭代号"""
        if not self.failure_history:
            return 0
        return self.failure_history[-1].iteration

    async def reflect(self, current_plan: str = "") -> ReflectionResult:
        """执行反思"""
        import time

        start_time = time.time()

        if self.llm_fn and self.config.enabled:
            result = await self._llm_reflect(current_plan)
        else:
            result = self._rule_based_reflect()

        result.reflection_text = result.reflection_text[:self.config.max_reflection_length]
        self.last_reflection_time = time.time() - start_time
        self._last_reflected_failure_count = len(self.failure_history)
        logger.info(f"Reflection completed in {self.last_reflection_time:.2f}s: {result.root_cause}")

        return result

    def _rule_based_reflect(self) -> ReflectionResult:
        """基于规则的简单反思"""
        if not self.failure_history:
            return ReflectionResult(reflection_text="No failures recorded.")

        last_failure = self.failure_history[-1]

        # 简单的根因分析
        error_type = last_failure.error_type.lower()
        if "timeout" in error_type:
            root_cause = "Tool execution timed out"
            correction = "Consider increasing timeout or simplifying the operation"
        elif "rate_limit" in error_type or "429" in error_type:
            root_cause = "API rate limit hit"
            correction = "Wait before retrying or reduce request frequency"
        elif "invalid" in error_type or "param" in error_type:
            root_cause = "Invalid parameters passed to tool"
            correction = "Review tool parameter requirements"
        elif "auth" in error_type or "permission" in error_type:
            root_cause = "Authentication or permission error"
            correction = "Check credentials and permissions"
        elif "not found" in error_type or "404" in error_type:
            root_cause = "Resource not found"
            correction = "Verify resource exists before attempting operation"
        else:
            root_cause = f"Unknown error: {last_failure.error_type}"
            correction = "Review error details and consider alternative approach"

        return ReflectionResult(
            reflection_text=f"Last failure: {last_failure.error_message}. Root cause: {root_cause}",
            root_cause=root_cause,
            suggested_correction=correction,
            should_retry=True,
            confidence=0.6,
        )

    async def _llm_reflect(self, current_plan: str) -> ReflectionResult:
        """使用 LLM 进行反思"""
        failure_summary = self._summarize_failures()

        prompt = f"""Analyze the following failures and provide a brief reflection:

{failure_summary}

Current Plan:
{current_plan}

Provide a brief reflection (max 300 tokens) covering:
1. Root cause of the failure(s)
2. Suggested correction
3. Whether retry is advisable
"""

        try:
            response = await self.llm_fn(
                prompt=prompt,
                max_tokens=self.config.max_reflection_length,
                temperature=0.3,
            )

            text = response.strip() if response else ""

            # 简单解析
            lines = text.split("\n")
            root_cause = None
            correction = None
            should_retry = True

            for line in lines:
                line = line.strip().lower()
                if "root cause" in line or "原因" in line:
                    root_cause = line.split(":", 1)[-1].strip() if ":" in line else line
                elif "suggested" in line or "correction" in line or "建议" in line:
                    correction = line.split(":", 1)[-1].strip() if ":" in line else line
                elif "retry" in line and "no" in line:
                    should_retry = False

            return ReflectionResult(
                reflection_text=text,
                root_cause=root_cause,
                suggested_correction=correction,
                should_retry=should_retry,
                confidence=0.7,
            )
        except Exception as e:
            logger.warning(f"LLM reflection failed: {e}")
            return self._rule_based_reflect()

    def _summarize_failures(self) -> str:
        """总结失败历史"""
        if not self.failure_history:
            return "No failures"

        recent = self.failure_history[-5:]  # 最近 5 次
        parts = []
        for f in recent:
            parts.append(f"[Iter {f.iteration}] {f.tool_name}: {f.error_type} - {f.error_message[:100]}")

        return "\n".join(parts)

    def get_failure_stats(self) -> dict[str, Any]:
        """获取失败统计"""
        error_types = Counter(f.error_type for f in self.failure_history)
        return {
            "total_failures": len(self.failure_history),
            "consecutive_failures": self.consecutive_failures,
            "error_types": dict(error_types),
            "last_failure_time": self.failure_history[-1].timestamp if self.failure_history else None,
        }

    def clear(self) -> None:
        """清除失败历史"""
        self.failure_history = []
        self.consecutive_failures = 0
        self._last_reflected_failure_count = 0


# 前向引用
from .config import ReflectionConfig
