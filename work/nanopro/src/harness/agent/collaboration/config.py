"""
Collaboration Config - Recipe T3: Minimal Collaboration

Configuration for lightweight two-agent collaboration (planner-executor or executor-verifier).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class RoleDefinition:
    """Definition of a collaboration role."""
    name: str
    description: str
    prompt_template: str = ""


@dataclass
class HandoffPolicy:
    """Policy for how roles hand off between each other."""
    # When to handoff: "always" | "on_error" | "on_success" | "manual"
    trigger: Literal["always", "on_error", "on_success", "manual"] = "on_error"
    # Maximum context length to pass (tokens)
    max_context_length: int = 2000
    # Whether to include full tool history in handoff
    include_tool_history: bool = True
    # Whether to include memory in handoff
    include_memory: bool = True


@dataclass
class CollabConfig:
    """Configuration for collaboration module (T3)."""
    enabled: bool = False
    # Collaboration mode
    mode: Literal["planner_executor", "executor_verifier"] = "planner_executor"
    # Critique frequency
    critique_frequency: Literal["on_error", "every_step", "never"] = "on_error"
    # Handoff policy
    handoff_policy: HandoffPolicy = field(default_factory=HandoffPolicy)
    # Maximum number of handoffs allowed
    max_handoffs: int = 3
    # Whether to use separate model for planner
    planner_model: str | None = None
    # Whether to use separate model for verifier
    verifier_model: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "critique_frequency": self.critique_frequency,
            "handoff_policy": {
                "trigger": self.handoff_policy.trigger,
                "max_context_length": self.handoff_policy.max_context_length,
                "include_tool_history": self.handoff_policy.include_tool_history,
                "include_memory": self.handoff_policy.include_memory,
            },
            "max_handoffs": self.max_handoffs,
            "planner_model": self.planner_model,
            "verifier_model": self.verifier_model,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CollabConfig":
        """Create from dictionary."""
        data = data.copy()
        if "handoff_policy" in data and isinstance(data["handoff_policy"], dict):
            hp_data = data["handoff_policy"]
            data["handoff_policy"] = HandoffPolicy(
                trigger=hp_data.get("trigger", "on_error"),
                max_context_length=hp_data.get("max_context_length", 2000),
                include_tool_history=hp_data.get("include_tool_history", True),
                include_memory=hp_data.get("include_memory", True),
            )
        return cls(**data)
