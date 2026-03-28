"""
Collaboration module - Recipe T3: Minimal Collaboration

Provides lightweight two-agent collaboration (planner-executor or executor-verifier).
"""

from .config import CollabConfig, HandoffPolicy, RoleDefinition
from .event import CollabEvent
from .roles import PlannerRole, ExecutorRole, VerifierRole
from .handoff import HandoffManager

__all__ = [
    "CollabConfig",
    "HandoffPolicy",
    "RoleDefinition",
    "CollabEvent",
    "PlannerRole",
    "ExecutorRole",
    "VerifierRole",
    "HandoffManager",
    "get_collab_summary",
]


def get_collab_summary(events: list[CollabEvent]) -> dict:
    """Get a summary dict from collaboration events.

    Args:
        events: List of CollabEvent from a collaboration session

    Returns:
        dict with event counts by type and role
    """
    summary = {
        "total_events": len(events),
        "by_type": {},
        "by_role": {},
    }

    for event in events:
        event_type = event.event_type
        role = event.role

        summary["by_type"][event_type] = summary["by_type"].get(event_type, 0) + 1
        summary["by_role"][role] = summary["by_role"].get(role, 0) + 1

    return summary
