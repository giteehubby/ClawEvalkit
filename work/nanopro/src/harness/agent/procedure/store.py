"""
Procedural Store - Recipe T4: Procedural Support

In-memory storage for skill/procedure cards.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .config import ProceduralConfig, SkillCard

logger = logging.getLogger("agent.procedure.store")


class ProceduralStore:
    """In-memory store for skill cards.

    Loads skill cards from YAML/JSON files and provides lookup by ID.
    """

    def __init__(self, config: ProceduralConfig):
        self.config = config
        self._cards: Dict[str, SkillCard] = {}
        self._trigger_index: Dict[str, List[str]] = {}  # keyword -> [skill_names]

        if config.enabled and config.cards_dir:
            self._load_cards(config.cards_dir)

    def _load_cards(self, cards_dir: str) -> None:
        """Load skill cards from directory.

        Supports both YAML and JSON files.
        """
        cards_path = Path(cards_dir)
        if not cards_path.exists():
            logger.warning(f"[ProceduralStore] Cards directory does not exist: {cards_dir}")
            return

        loaded_count = 0
        for file_path in cards_path.glob("*.yaml"):
            cards = self._load_from_file(file_path)
            for card in cards:
                self._add_card(card)
                loaded_count += 1

        for file_path in cards_path.glob("*.json"):
            if file_path.name.endswith(".skill.json"):  # Skip any non-skill JSON
                continue
            cards = self._load_from_file(file_path)
            for card in cards:
                self._add_card(card)
                loaded_count += 1

        logger.info(f"[ProceduralStore] Loaded {loaded_count} skill cards from {cards_dir}")

    def _load_from_file(self, file_path: Path) -> List[SkillCard]:
        """Load skill cards from a single file."""
        try:
            content = file_path.read_text(encoding="utf-8")

            if file_path.suffix == ".yaml" or file_path.suffix == ".yml":
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)

            if isinstance(data, dict):
                # Single card
                return [SkillCard.from_dict(data)]
            elif isinstance(data, list):
                # Multiple cards
                return [SkillCard.from_dict(item) for item in data]
            else:
                logger.warning(f"[ProceduralStore] Unknown format in {file_path}")
                return []

        except Exception as e:
            logger.error(f"[ProceduralStore] Failed to load {file_path}: {e}")
            return []

    def _add_card(self, card: SkillCard) -> None:
        """Add a card to the store and update trigger index."""
        self._cards[card.name] = card

        # Update trigger index
        for keyword in card.trigger_keywords:
            keyword_lower = keyword.lower()
            if keyword_lower not in self._trigger_index:
                self._trigger_index[keyword_lower] = []
            if card.name not in self._trigger_index[keyword_lower]:
                self._trigger_index[keyword_lower].append(card.name)

    def get(self, skill_name: str) -> Optional[SkillCard]:
        """Get a skill card by name."""
        return self._cards.get(skill_name)

    def get_all(self) -> List[SkillCard]:
        """Get all skill cards."""
        return list(self._cards.values())

    def get_compact_list(self) -> List[Dict[str, str]]:
        """Get compact list of all skills for display."""
        return [
            {"name": card.name, "compact": card.compact or card.description[:50]}
            for card in self._cards.values()
        ]

    def search_by_keyword(self, keyword: str) -> List[str]:
        """Search for skill names that match a keyword."""
        keyword_lower = keyword.lower()
        return self._trigger_index.get(keyword_lower, [])

    def get_card_count(self) -> int:
        """Get total number of cards."""
        return len(self._cards)
