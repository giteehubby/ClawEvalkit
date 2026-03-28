"""
EpisodicMemoryStore - Core memory storage and retrieval.
"""

import logging
import time
import uuid
from typing import List, Optional

from .config import MemoryConfig
from .item import MemoryItem
from .policy import RetrievalPolicy, should_write_to_memory


class EpisodicMemoryStore:
    """Task-local episodic memory store.

    Stores tool results and errors to help the agent remember
    context across iterations within a single task.
    """

    _logger = logging.getLogger("memory.store")

    def __init__(self, config: MemoryConfig):
        self.config = config
        self._items: List[MemoryItem] = []
        self._iteration = 0
        self._enabled = config.enabled

    def reset(self) -> None:
        """Reset memory for new task."""
        self._items = []
        self._iteration = 0
        self._logger.debug("[EpisodicMemoryStore] Reset for new task")

    def increment_iteration(self) -> None:
        """Increment the iteration counter."""
        self._iteration += 1

    def write(
        self,
        content: str,
        source: str,
        source_detail: str = "",
        memory_type: str = "result",
    ) -> Optional[MemoryItem]:
        """Write a memory item.

        Args:
            content: The content to store
            source: Source type ("tool_result", "error", "user_prompt")
            source_detail: Additional source info (e.g., tool name)
            memory_type: Memory type ("fact", "instruction", "error", "result")

        Returns:
            The created MemoryItem, or None if not written
        """
        if not self._enabled:
            return None

        # Check budget
        if len(self._items) >= self.config.max_items:
            # Remove oldest item to make space
            self._items.pop(0)
            self._logger.debug(f"[EpisodicMemoryStore] Budget exceeded, removed oldest item")

        item = MemoryItem(
            id=str(uuid.uuid4())[:8],
            content=content[:2000],  # Truncate very long content
            source=source,
            source_detail=source_detail,
            iteration=self._iteration,
            memory_type=memory_type,
            created_at=time.time(),
        )
        self._items.append(item)
        self._logger.debug(f"[EpisodicMemoryStore] Wrote item: {item.id} ({source}, {memory_type})")
        return item

    def retrieve(self, max_items: Optional[int] = None) -> List[MemoryItem]:
        """Retrieve relevant memory items.

        Args:
            max_items: Maximum items to retrieve (default from config)

        Returns:
            List of retrieved MemoryItems
        """
        if not self._enabled or not self._items:
            return []

        if max_items is None:
            max_items = self.config.retrieval_max

        # Sort by policy
        items = self._sort_by_policy(self._items.copy())

        # Touch accessed items
        current_time = time.time()
        retrieved = []
        for item in items[:max_items]:
            item.touch(current_time)
            retrieved.append(item)

        self._logger.debug(f"[EpisodicMemoryStore] Retrieved {len(retrieved)} items")
        return retrieved

    def _sort_by_policy(self, items: List[MemoryItem]) -> List[MemoryItem]:
        """Sort items by retrieval policy."""
        if self.config.retrieval_policy == RetrievalPolicy.RECENT:
            # Most recent first (higher iteration, then later in list)
            return sorted(items, key=lambda x: (x.iteration, x.created_at), reverse=True)
        elif self.config.retrieval_policy == RetrievalPolicy.FREQUENCY:
            # Most accessed first
            return sorted(items, key=lambda x: x.access_count, reverse=True)
        elif self.config.retrieval_policy == RetrievalPolicy.HYBRID:
            # Hybrid: recent + frequency boost
            return sorted(
                items,
                key=lambda x: (x.iteration * 0.7 + x.access_count * 0.3, x.created_at),
                reverse=True,
            )
        return items

    def format_for_prompt(self, items: Optional[List[MemoryItem]] = None) -> str:
        """Format memory items as a string for injection into prompt.

        Args:
            items: Items to format. If None, retrieves based on config.

        Returns:
            Formatted memory context string
        """
        if items is None:
            items = self.retrieve()

        if not items:
            return ""

        lines = ["[CONTEXT FROM PREVIOUS STEPS - Memory]"]
        for i, item in enumerate(items, 1):
            source_tag = f"[{item.source}]"
            detail = f" ({item.source_detail})" if item.source_detail else ""
            # Truncate long content
            content = item.content
            if len(content) > 300:
                content = content[:300] + "..."
            lines.append(f"{i}. {source_tag}{detail} -> \"{content}\"")
        lines.append("[END Memory]")

        return "\n".join(lines)

    def get_summary(self) -> dict:
        """Get memory summary for logging/transcript."""
        return {
            "total_items": len(self._items),
            "current_iteration": self._iteration,
            "enabled": self._enabled,
            "write_policy": self.config.write_policy.value,
            "retrieval_policy": self.config.retrieval_policy.value,
        }

    def should_write_event(self, event_type: str, content: str = "") -> bool:
        """Check if an event should be written based on write policy.

        Args:
            event_type: Type of event
            content: Content to potentially write

        Returns:
            True if should write
        """
        if not self._enabled:
            return False
        return should_write_to_memory(
            self.config.write_policy,
            event_type,
            content,
            self.config.long_content_threshold,
        )

    @property
    def item_count(self) -> int:
        """Current number of items in memory."""
        return len(self._items)

    @property
    def is_enabled(self) -> bool:
        """Whether memory is enabled."""
        return self._enabled
