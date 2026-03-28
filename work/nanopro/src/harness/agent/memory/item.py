"""
MemoryItem dataclass for episodic memory.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MemoryItem:
    """Single memory item stored in episodic memory."""

    id: str
    content: str
    source: str  # "tool_result" | "error" | "user_prompt"
    source_detail: str  # tool_name etc.
    iteration: int
    memory_type: str  # "fact" | "instruction" | "error" | "result"
    created_at: float
    access_count: int = 0
    last_accessed_at: Optional[float] = None

    def touch(self, current_time: float) -> None:
        """Update access metadata."""
        self.access_count += 1
        self.last_accessed_at = current_time

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "source_detail": self.source_detail,
            "iteration": self.iteration,
            "memory_type": self.memory_type,
            "created_at": self.created_at,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryItem":
        """Create from dictionary."""
        return cls(**data)
