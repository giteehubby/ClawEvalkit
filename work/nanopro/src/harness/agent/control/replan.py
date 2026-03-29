"""
ReplanTrigger 模块 - 检测需要重新规划的信号并触发重规划
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("control.replan")


@dataclass
class ReplanSignal:
    """重规划信号"""
    signal_type: str  # "error" | "repeated_action" | "tool_mismatch" | "low_confidence"
    description: str
    timestamp: float
    iteration: int
    tool_name: str | None = None
    action: str | None = None


@dataclass
class ReplanDecision:
    """重规划决策"""
    should_replan: bool
    reason: str | None
    new_plan: "ExecutionPlan | None" = None
    signals: list[ReplanSignal] = field(default_factory=list)


class ReplanTrigger:
    """重规划触发器"""

    def __init__(self, config: "ReplanConfig"):
        self.config = config
        self.signals: list[ReplanSignal] = []
        self.last_replan_iteration = 0
        self.last_replan_time = 0.0
        self.replan_count = 0
        self._action_history: list[str] = []

    def record_signal(self, signal_type: str, description: str, iteration: int,
                     tool_name: str | None = None, action: str | None = None) -> None:
        """记录一个信号"""
        if not self.config.enabled:
            return

        if signal_type not in self.config.signals:
            return

        signal = ReplanSignal(
            signal_type=signal_type,
            description=description,
            timestamp=time.time(),
            iteration=iteration,
            tool_name=tool_name,
            action=action,
        )
        self.signals.append(signal)
        logger.debug(f"Recorded signal: {signal_type} - {description}")

    def record_action(self, action: str) -> None:
        """记录执行的动作，用于检测重复"""
        if not self.config.enabled:
            return

        self._action_history.append(action)

        # 检测重复动作
        action_count = Counter(self._action_history)
        recent_actions = list(self._action_history[-10:])  # 最近 10 个动作

        for act, count in action_count.items():
            if count >= 3 and act in recent_actions[-3:]:
                self.record_signal(
                    signal_type="repeated_action",
                    description=f"Action '{act}' repeated {count} times",
                    iteration=len(self._action_history),
                    action=act,
                )

    def record_error(self, error: str, iteration: int, tool_name: str | None = None) -> None:
        """记录错误"""
        self.record_signal(
            signal_type="error",
            description=error,
            iteration=iteration,
            tool_name=tool_name,
        )

    def record_tool_mismatch(self, expected: str, actual: str, iteration: int) -> None:
        """记录工具不匹配"""
        self.record_signal(
            signal_type="tool_mismatch",
            description=f"Expected tool '{expected}' but got '{actual}'",
            iteration=iteration,
            tool_name=actual,
        )

    def should_replan(self, current_iteration: int) -> ReplanDecision:
        """判断是否应该重规划"""
        if not self.config.enabled:
            return ReplanDecision(should_replan=False, reason=None)

        # 检查重规划次数限制
        if self.replan_count >= self.config.max_replans:
            return ReplanDecision(
                should_replan=False,
                reason=f"Max replans ({self.config.max_replans}) reached"
            )

        # 检查两次重规划之间的最小迭代间隔
        iterations_since_last = current_iteration - self.last_replan_iteration
        if iterations_since_last < self.config.min_iterations_between_replans:
            return ReplanDecision(
                should_replan=False,
                reason=f"Too soon since last replan ({iterations_since_last} < {self.config.min_iterations_between_replans})"
            )

        # 获取最近的信号
        recent_signals = self._get_recent_signals()

        # 检查信号数量是否达到阈值
        if len(recent_signals) >= self.config.signal_threshold:
            # 按类型分组统计
            signal_types = Counter(s.signal_type for s in recent_signals)
            reason = f"Signal threshold reached: {dict(signal_types)}"
            logger.info(f"Replan triggered: {reason}")
            return ReplanDecision(
                should_replan=True,
                reason=reason,
                signals=recent_signals,
            )

        return ReplanDecision(should_replan=False, reason=None)

    def _get_recent_signals(self, window_seconds: float = 60.0) -> list[ReplanSignal]:
        """获取最近的信号"""
        now = time.time()
        return [s for s in self.signals if now - s.timestamp <= window_seconds]

    def confirm_replan(self) -> None:
        """确认已执行重规划"""
        self.replan_count += 1
        if self.signals:
            # 使用最新信号的 iteration 作为 last_replan_iteration，避免重复触发
            self.last_replan_iteration = max(s.iteration for s in self.signals)
            self.last_replan_time = time.time()
        # 保留最后一次重规划的信号用于分析
        self.signals = []
        self._action_history = []

    def get_replan_stats(self) -> dict[str, Any]:
        """获取重规划统计"""
        return {
            "replan_count": self.replan_count,
            "total_signals": len(self.signals),
            "signal_types": dict(Counter(s.signal_type for s in self.signals)),
            "last_replan_iteration": self.last_replan_iteration,
            "action_history_length": len(self._action_history),
        }

    def reset(self) -> None:
        """重置状态"""
        self.signals = []
        self.last_replan_iteration = 0
        self.last_replan_time = 0.0
        self.replan_count = 0
        self._action_history = []


# 前向引用
from .plan_first import ExecutionPlan
