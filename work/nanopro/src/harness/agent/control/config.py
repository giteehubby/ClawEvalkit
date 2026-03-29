"""
Control 配置模块 - Recipe T2: Single-agent control
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PlanFirstConfig:
    """Plan-first 配置

    策略：
    1. task_start 触发：在任务开始时生成初始计划
    2. on_failure 触发：失败后生成恢复计划
    3. 所有计划都暴露给模型，帮助模型理解和执行任务
    """
    enabled: bool = False
    # 何时生成计划: "always" | "task_start" | "on_failure"
    trigger: Literal["always", "task_start", "on_failure"] = "task_start"
    # 计划最大长度（token 估算）
    max_plan_length: int = 500
    # 是否要求模型先输出计划再执行（目前未使用）
    require_explicit_plan: bool = False


@dataclass
class ReplanConfig:
    """Replan 触发配置"""
    enabled: bool = False
    # 触发重规划的信号数量阈值
    signal_threshold: int = 3
    # 信号类型: "error" | "repeated_action" | "tool_mismatch" | "low_confidence"
    signals: list[str] = field(default_factory=lambda: ["error", "repeated_action"])
    # 最大重规划次数
    max_replans: int = 2
    # 两次重规划之间的最小迭代间隔
    min_iterations_between_replans: int = 2


@dataclass
class RetryConfig:
    """Retry 策略配置"""
    enabled: bool = False
    # 最大重试次数（单工具）
    max_retries: int = 2
    # 重试间隔: "constant" | "exponential"
    backoff: Literal["constant", "exponential"] = "exponential"
    # 基础延迟秒数
    base_delay: float = 1.0
    # 需要重试的错误类型
    retryable_errors: list[str] = field(default_factory=lambda: ["rate_limit", "timeout", "transient"])
    # 永久失败的错误类型（不重试）
    fatal_errors: list[str] = field(default_factory=lambda: ["invalid_params", "auth_failed", "permission_denied"])


@dataclass
class ReflectionConfig:
    """Failure Reflection 配置"""
    enabled: bool = False
    # 何时触发反思: "on_failure" | "on_consecutive_failures" | "manual"
    trigger: Literal["on_failure", "on_consecutive_failures", "manual"] = "on_failure"
    # 连续失败次数阈值（仅当 trigger=consecutive 时）
    consecutive_failure_threshold: int = 2
    # 反思最大长度
    max_reflection_length: int = 300


@dataclass
class ControlConfig:
    """Control 总配置"""
    enabled: bool = False
    plan_first: PlanFirstConfig = field(default_factory=PlanFirstConfig)
    replan: ReplanConfig = field(default_factory=ReplanConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    reflection: ReflectionConfig = field(default_factory=ReflectionConfig)
    # Preflight check 配置
    preflight_enabled: bool = False
    # 是否在每次工具调用前检查参数
    preflight_check_params: bool = True
    # 是否检查工具是否适合当前任务
    preflight_check_suitability: bool = False
