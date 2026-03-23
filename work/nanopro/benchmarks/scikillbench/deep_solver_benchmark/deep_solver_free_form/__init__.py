"""
Deep Solver (Free-Form Output)

Same 4-agent architecture as deep_solver/, but with free-form text output
instead of structured Pydantic models. Use this for demonstrations and
human-readable results where detailed explanations are preferred.
"""

from .solution_researcher import create_solution_researcher_agent
from .code_agent import create_code_agent
from .debug_agent import create_debug_agents
from .output_processor_agent import create_output_processor_agent

__all__ = [
    'create_solution_researcher_agent',
    'create_code_agent',
    'create_debug_agents',
    'create_output_processor_agent'
]
