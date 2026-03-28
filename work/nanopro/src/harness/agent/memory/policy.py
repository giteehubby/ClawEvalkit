"""
Write and Retrieval policy enums for memory management.
"""

from enum import Enum


class WritePolicy(Enum):
    """When to write to episodic memory."""

    ALWAYS = "always"  # Write everything
    TOOL_RESULT_OR_ERROR = "tool_result_or_error"  # Default: write tool results and errors
    TOOL_RESULT = "tool_result"  # Only tool results
    ERROR = "error"  # Only errors
    LONG_CONTENT = "long_content"  # Only content exceeding threshold
    NEVER = "never"  # Never write


class RetrievalPolicy(Enum):
    """How to retrieve memories."""

    RECENT = "recent"  # Most recent first (default)
    FREQUENCY = "frequency"  # Most accessed first
    HYBRID = "hybrid"  # Combination of recent and frequency


def should_write_to_memory(
    policy: WritePolicy,
    event_type: str,
    content: str = "",
    long_content_threshold: int = 500,
) -> bool:
    """Determine if an event should be written to memory.

    Args:
        policy: The write policy to apply
        event_type: Type of event ("tool_result", "error", "user_prompt")
        content: Content of the event
        long_content_threshold: Min length for LONG_CONTENT policy

    Returns:
        True if should write to memory
    """
    if policy == WritePolicy.ALWAYS:
        return True
    elif policy == WritePolicy.NEVER:
        return False
    elif policy == WritePolicy.TOOL_RESULT_OR_ERROR:
        return event_type in ("tool_result", "error")
    elif policy == WritePolicy.TOOL_RESULT:
        return event_type == "tool_result"
    elif policy == WritePolicy.ERROR:
        return event_type == "error"
    elif policy == WritePolicy.LONG_CONTENT:
        return len(content) >= long_content_threshold
    return False
