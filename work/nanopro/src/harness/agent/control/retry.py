"""
RetryPolicy 模块 - 失败重试策略
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger("control.retry")


@dataclass
class RetryDecision:
    """重试决策"""
    should_retry: bool
    retry_count: int
    delay: float
    reason: str | None
    fatal: bool = False


@dataclass
class RetryAttempt:
    """重试记录"""
    attempt_number: int
    error: str
    error_type: str
    timestamp: float
    delay_used: float = 0.0


@dataclass
class RetryState:
    """重试状态"""
    tool_name: str
    total_attempts: int = 0
    successful: bool = False
    attempts: list[RetryAttempt] = field(default_factory=list)
    last_error: str | None = None
    last_error_type: str | None = None


class RetryPolicy:
    """重试策略模块"""

    def __init__(self, config: "RetryConfig"):
        self.config = config
        self._states: dict[str, RetryState] = {}

    def should_retry(self, tool_name: str, error: str, error_type: str = "unknown") -> RetryDecision:
        """判断是否应该重试"""
        if not self.config.enabled:
            return RetryDecision(should_retry=False, retry_count=0, delay=0, reason="Retry disabled")

        # 检查是否是不应重试的错误
        for fatal in self.config.fatal_errors:
            if fatal in error_type.lower() or fatal in error.lower():
                self._record_attempt(tool_name, error, error_type, fatal=True)
                return RetryDecision(
                    should_retry=False,
                    retry_count=self._get_state(tool_name).total_attempts,
                    delay=0,
                    reason=f"Fatal error: {fatal}",
                    fatal=True,
                )

        # 获取当前状态
        state = self._get_state(tool_name)

        # 检查重试次数
        if state.total_attempts >= self.config.max_retries:
            return RetryDecision(
                should_retry=False,
                retry_count=state.total_attempts,
                delay=0,
                reason=f"Max retries ({self.config.max_retries}) reached",
            )

        # 检查错误是否可重试
        retryable = any(
            err in error_type.lower() or err in error.lower()
            for err in self.config.retryable_errors
        )

        if not retryable and self.config.retryable_errors:
            # 如果配置了可重试错误列表但当前错误不在其中
            return RetryDecision(
                should_retry=False,
                retry_count=state.total_attempts,
                delay=0,
                reason=f"Error type '{error_type}' not in retryable list",
            )

        # 计算延迟
        delay = self._calculate_delay(state.total_attempts)

        return RetryDecision(
            should_retry=True,
            retry_count=state.total_attempts,
            delay=delay,
            reason=f"Retryable error: {error_type}",
        )

    def _calculate_delay(self, attempt: int) -> float:
        """计算重试延迟"""
        if self.config.backoff == "exponential":
            return self.config.base_delay * (2 ** attempt)
        else:  # constant
            return self.config.base_delay

    def _get_state(self, tool_name: str) -> RetryState:
        """获取工具的重试状态"""
        if tool_name not in self._states:
            self._states[tool_name] = RetryState(tool_name=tool_name)
        return self._states[tool_name]

    def _record_attempt(
        self,
        tool_name: str,
        error: str,
        error_type: str,
        fatal: bool = False,
        delay_used: float = 0.0,
    ) -> None:
        """记录一次重试尝试"""
        state = self._get_state(tool_name)
        state.total_attempts += 1
        state.last_error = error
        state.last_error_type = error_type
        state.attempts.append(RetryAttempt(
            attempt_number=state.total_attempts,
            error=error,
            error_type=error_type,
            timestamp=time.time(),
            delay_used=delay_used,
        ))
        logger.debug(f"Retry attempt {state.total_attempts} for {tool_name}: {error_type}")

    async def execute_with_retry(
        self,
        tool_name: str,
        func: Callable[..., Awaitable[Any]],
        *args,
        **kwargs,
    ) -> tuple[bool, Any]:
        """执行带重试的函数"""
        if not self.config.enabled:
            result = await func(*args, **kwargs)
            return True, result

        last_error = None
        last_error_type = "unknown"

        while True:
            try:
                result = await func(*args, **kwargs)
                self._mark_success(tool_name)
                return True, result

            except Exception as e:
                last_error = str(e)
                last_error_type = self._classify_error(e)

                decision = self.should_retry(tool_name, last_error, last_error_type)

                if not decision.should_retry:
                    logger.warning(f"Retry exhausted for {tool_name}: {last_error}")
                    return False, last_error

                # 执行延迟
                if decision.delay > 0:
                    logger.info(f"Retrying {tool_name} in {decision.delay:.1f}s (attempt {decision.retry_count + 1})")
                    await asyncio.sleep(decision.delay)
                    self._record_attempt(tool_name, last_error, last_error_type, delay_used=decision.delay)

    def _mark_success(self, tool_name: str) -> None:
        """标记成功"""
        if tool_name in self._states:
            self._states[tool_name].successful = True

    @staticmethod
    def _classify_error(e: Exception) -> str:
        """分类错误类型"""
        error_str = str(e).lower()
        error_type = type(e).__name__.lower()

        if "timeout" in error_str or "timed out" in error_str:
            return "timeout"
        elif "rate limit" in error_str or "429" in error_str or "too many requests" in error_str:
            return "rate_limit"
        elif "401" in error_str or "403" in error_str or "auth" in error_str:
            return "auth_failed"
        elif "404" in error_str or "not found" in error_str:
            return "not_found"
        elif "invalid" in error_str or "param" in error_str:
            return "invalid_params"
        elif "permission" in error_str or "denied" in error_str:
            return "permission_denied"
        elif "transient" in error_str or "temporary" in error_str:
            return "transient"
        else:
            return error_type

    def get_retry_stats(self) -> dict[str, Any]:
        """获取重试统计"""
        stats = {}
        for tool_name, state in self._states.items():
            stats[tool_name] = {
                "total_attempts": state.total_attempts,
                "successful": state.successful,
                "last_error": state.last_error,
                "last_error_type": state.last_error_type,
            }
        return stats

    def reset(self, tool_name: str | None = None) -> None:
        """重置重试状态"""
        if tool_name:
            self._states.pop(tool_name, None)
        else:
            self._states.clear()


# 前向引用
from .config import RetryConfig
