"""
Procedural Config - Recipe T4: Procedural Support

Configuration for compact skill/procedure cards with on-demand expansion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class SkillCard:
    """A skill/procedure card with trigger keywords and steps.

    Attributes:
        name: Unique identifier for the skill
        description: Human-readable description
        trigger_keywords: Keywords that trigger this skill's expansion
        steps: Ordered list of steps to execute
        examples: Example use cases
        compact: One-line summary for non-trigger use (shown in listings)
    """
    name: str
    description: str
    trigger_keywords: List[str]
    steps: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    compact: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "trigger_keywords": self.trigger_keywords,
            "steps": self.steps,
            "examples": self.examples,
            "compact": self.compact,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillCard":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            trigger_keywords=data.get("trigger_keywords", []),
            steps=data.get("steps", []),
            examples=data.get("examples", []),
            compact=data.get("compact", ""),
        )


@dataclass
class ProceduralConfig:
    """Configuration for procedural support module (T4)."""
    enabled: bool = False
    # Directory containing skill card files (YAML/JSON)
    cards_dir: str = ""
    # Maximum number of triggered cards to expand per iteration
    max_expansions_per_iteration: int = 3
    # Whether to show compact skill list in prompt
    show_skill_list: bool = True
    # Whether to cache triggered skills across iterations
    cache_triggers: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "cards_dir": self.cards_dir,
            "max_expansions_per_iteration": self.max_expansions_per_iteration,
            "show_skill_list": self.show_skill_list,
            "cache_triggers": self.cache_triggers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProceduralConfig":
        """Create from dictionary."""
        return cls(**data)
