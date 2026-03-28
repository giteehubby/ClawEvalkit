"""
Collaboration Event - Recipe T3: Minimal Collaboration

Dataclass for structured event logging in collaboration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CollabEvent:
    """Structured event for collaboration tracking."""
    event_type: str  # "plan_generated", "step_executed", "handoff", "critique", "revision"
    role: str  # "planner", "executor", "verifier"
    iteration: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type,
            "role": self.role,
            "iteration": self.iteration,
            "data": self.data,
            "timestamp": self.timestamp,
        }
