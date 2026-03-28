"""
Procedural Expander - Recipe T4: Procedural Support

Formats skill card content for prompt injection.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .config import SkillCard
from .event import ProceduralEvent

logger = logging.getLogger("agent.procedure.expander")


class ProceduralExpander:
    """Formats skill card content for prompt injection."""

    def __init__(self):
        self._events: List[ProceduralEvent] = []

    def format(
        self,
        card: SkillCard,
        include_examples: bool = True,
    ) -> str:
        """Format a skill card for injection into the prompt.

        Args:
            card: The skill card to format
            include_examples: Whether to include examples in the output

        Returns:
            Formatted string suitable for prompt injection
        """
        lines = [
            f"\n## Skill: {card.name}",
            f"**Description**: {card.description}",
            "",
            "**Steps**:",
        ]

        for i, step in enumerate(card.steps, 1):
            lines.append(f"  {i}. {step}")

        if include_examples and card.examples:
            lines.append("")
            lines.append("**Examples**:")
            for example in card.examples:
                lines.append(f"  - {example}")

        formatted = "\n".join(lines)

        event = ProceduralEvent(
            event_type="skill_expanded",
            skill_name=card.name,
            data={"formatted_length": len(formatted), "step_count": len(card.steps)},
        )
        self._events.append(event)

        logger.debug(f"[ProceduralExpander] Expanded skill '{card.name}' ({len(formatted)} chars)")

        return formatted

    def format_multiple(
        self,
        cards: List[SkillCard],
        include_examples: bool = True,
    ) -> str:
        """Format multiple skill cards for injection.

        Args:
            cards: List of skill cards to format
            include_examples: Whether to include examples

        Returns:
            Combined formatted string
        """
        if not cards:
            return ""

        formatted_parts = []
        for card in cards:
            formatted_parts.append(self.format(card, include_examples=include_examples))

        return "\n".join([
            "\n## Available Procedures",
            "(Use these procedures when relevant to the task)\n",
        ] + formatted_parts)

    def format_skill_list(
        self,
        cards: List[SkillCard],
    ) -> str:
        """Format a compact skill list for display.

        Args:
            cards: List of skill cards

        Returns:
            Compact list as string
        """
        if not cards:
            return ""

        lines = ["\n## Available Skills"]
        for card in cards:
            compact = card.compact or card.description[:50]
            lines.append(f"- **{card.name}**: {compact}")

        return "\n".join(lines)

    def get_events(self) -> List[ProceduralEvent]:
        """Get all events recorded."""
        return self._events.copy()
