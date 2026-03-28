"""
MemoryConfig dataclass for memory module configuration.
"""

from dataclasses import dataclass, field
from .policy import WritePolicy, RetrievalPolicy


@dataclass
class MemoryConfig:
    """Configuration for episodic memory."""

    enabled: bool = False
    max_items: int = 20  # Maximum memory items to store
    retrieval_max: int = 5  # Maximum items to retrieve per LLM call
    write_policy: WritePolicy = field(default_factory=lambda: WritePolicy.TOOL_RESULT_OR_ERROR)
    retrieval_policy: RetrievalPolicy = field(default_factory=lambda: RetrievalPolicy.RECENT)
    long_content_threshold: int = 500  # Min content length for LONG_CONTENT write policy

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "max_items": self.max_items,
            "retrieval_max": self.retrieval_max,
            "write_policy": self.write_policy.value,
            "retrieval_policy": self.retrieval_policy.value,
            "long_content_threshold": self.long_content_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryConfig":
        """Create from dictionary."""
        from .policy import WritePolicy, RetrievalPolicy

        data = data.copy()
        if "write_policy" in data and isinstance(data["write_policy"], str):
            data["write_policy"] = WritePolicy(data["write_policy"])
        if "retrieval_policy" in data and isinstance(data["retrieval_policy"], str):
            data["retrieval_policy"] = RetrievalPolicy(data["retrieval_policy"])
        return cls(**data)
