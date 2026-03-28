"""
Procedural Event - Recipe T4: Procedural Support

Dataclass for structured event logging in procedural support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProceduralEvent:
    """Structured event for procedural support tracking."""
    event_type: str  # "skill_triggered", "skill_expanded", "skill_cached"
    skill_name: str
    matched_keywords: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type,
            "skill_name": self.skill_name,
            "matched_keywords": self.matched_keywords,
            "data": self.data,
            "timestamp": self.timestamp,
        }
