"""
Control 模块 - Recipe T2: Single-agent control

提供 agent 控制机制：
- PlanFirst: 任务开始前生成执行计划
- ReplanTrigger: 检测需要重新规划的信号
- FailureReflection: 失败后进行反思
- PreflightCheck: 工具调用前检查
- RetryPolicy: 失败重试策略
"""

from __future__ import annotations

from .config import ControlConfig, PlanFirstConfig, ReplanConfig, RetryConfig, ReflectionConfig
from .plan_first import PlanFirst, ExecutionPlan
from .replan import ReplanTrigger
from .reflection import FailureReflection
from .preflight import PreflightCheck
from .retry import RetryPolicy

__all__ = [
    "ControlConfig",
    "PlanFirstConfig",
    "ReplanConfig",
    "RetryConfig",
    "ReflectionConfig",
    "PlanFirst",
    "ReplanTrigger",
    "FailureReflection",
    "PreflightCheck",
    "RetryPolicy",
    "ExecutionPlan",
    "get_control_summary",
]


def get_control_summary(plan_summary: dict, replan_stats: dict, failure_stats: dict, retry_stats: dict, preflight_stats: dict) -> dict:
    """Get a summary dict from all control submodules.

    Args:
        plan_summary: Output from PlanFirst.get_plan_summary()
        replan_stats: Output from ReplanTrigger.get_replan_stats()
        failure_stats: Output from FailureReflection.get_failure_stats()
        retry_stats: Output from RetryPolicy.get_retry_stats()
        preflight_stats: Output from PreflightCheck.get_check_stats()

    Returns:
        dict with aggregated control metrics
    """
    return {
        "plan": plan_summary,
        "replan": replan_stats,
        "failure": failure_stats,
        "retry": retry_stats,
        "preflight": preflight_stats,
    }
