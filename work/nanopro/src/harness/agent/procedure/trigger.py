"""
Procedural Trigger - Recipe T4: Procedural Support

Matches task description/context against skill card trigger keywords.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Set, Tuple

from .config import ProceduralConfig, SkillCard
from .event import ProceduralEvent
from .store import ProceduralStore

logger = logging.getLogger("agent.procedure.trigger")


class ProceduralTrigger:
    """Matches task/context against skill card trigger keywords."""

    def __init__(
        self,
        config: ProceduralConfig,
        store: ProceduralStore,
    ):
        self.config = config
        self.store = store
        self._events: List[ProceduralEvent] = []
        self._cached_triggers: Set[str] = set()  # skill names that were triggered
        self._iteration = 0

    def increment_iteration(self) -> None:
        """Increment iteration counter."""
        self._iteration += 1
        if not self.config.cache_triggers:
            self._cached_triggers.clear()

    def check(
        self,
        task: str,
        context: str | None = None,
    ) -> List[Tuple[SkillCard, List[str]]]:
        """Check if task/context matches any skill card triggers.

        Args:
            task: The current task description
            context: Optional additional context

        Returns:
            List of (SkillCard, matched_keywords) tuples, limited by max_expansions_per_iteration
        """
        if not self.config.enabled:
            return []

        # Combine task and context for matching
        text_to_check = task
        if context:
            text_to_check += " " + context

        text_lower = text_to_check.lower()

        # Find all matching skill cards
        matches: List[Tuple[SkillCard, List[str]]] = []

        for card in self.store.get_all():
            matched_keywords = self._find_matched_keywords(card, text_lower)
            if matched_keywords:
                matches.append((card, matched_keywords))
                self._cached_triggers.add(card.name)

                event = ProceduralEvent(
                    event_type="skill_triggered",
                    skill_name=card.name,
                    matched_keywords=matched_keywords,
                    data={"task_preview": task[:100]},
                )
                self._events.append(event)

        # Sort by number of matched keywords (most specific first)
        matches.sort(key=lambda x: len(x[1]), reverse=True)

        # Limit expansions
        max_expansions = self.config.max_expansions_per_iteration
        limited_matches = matches[:max_expansions]

        if limited_matches:
            logger.info(f"[ProceduralTrigger] Triggered {len(limited_matches)} skills: {[m[0].name for m in limited_matches]}")

        return limited_matches

    def _find_matched_keywords(self, card: SkillCard, text_lower: str) -> List[str]:
        """Find which keywords from a card match in the text."""
        matched = []

        for keyword in card.trigger_keywords:
            keyword_lower = keyword.lower()

            # Check for exact word boundary match
            pattern = r'\b' + re.escape(keyword_lower) + r'\b'
            if re.search(pattern, text_lower):
                matched.append(keyword)
                continue

            # Check for substring match (for longer keywords)
            if len(keyword_lower) >= 5 and keyword_lower in text_lower:
                matched.append(keyword)

        return matched

    def get_triggered_skills(self) -> Set[str]:
        """Get set of skill names that have been triggered."""
        return self._cached_triggers.copy()

    def get_events(self) -> List[ProceduralEvent]:
        """Get all events recorded."""
        return self._events.copy()

    def reset(self) -> None:
        """Reset trigger state."""
        self._cached_triggers.clear()
        self._events.clear()
        self._iteration = 0
