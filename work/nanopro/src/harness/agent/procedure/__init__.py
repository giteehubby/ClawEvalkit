"""
Procedural Support module - Recipe T4: Procedural Support

Provides compact skill/procedure cards with on-demand expansion.
"""

from .config import ProceduralConfig, SkillCard
from .event import ProceduralEvent
from .store import ProceduralStore
from .trigger import ProceduralTrigger
from .expander import ProceduralExpander

__all__ = [
    "ProceduralConfig",
    "SkillCard",
    "ProceduralEvent",
    "ProceduralStore",
    "ProceduralTrigger",
    "ProceduralExpander",
    "get_procedure_summary",
]


def get_procedure_summary(trigger_events: list[ProceduralEvent], expander_events: list[ProceduralEvent]) -> dict:
    """Get a summary dict from procedural events.

    Args:
        trigger_events: List of ProceduralEvent from triggers
        expander_events: List of ProceduralEvent from expanders

    Returns:
        dict with event counts and triggered skills
    """
    all_events = trigger_events + expander_events

    triggered_skills = set()
    for event in trigger_events:
        if event.event_type == "skill_triggered":
            triggered_skills.add(event.skill_name)

    return {
        "total_events": len(all_events),
        "triggered_skills": list(triggered_skills),
        "trigger_count": len(trigger_events),
        "expansion_count": len(expander_events),
    }
