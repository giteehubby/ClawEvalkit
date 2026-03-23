"""
Free-form agent overrides for deep problem-solving workflow.

These agents use free-form output instead of structured Pydantic models,
allowing for more detailed explanations and flexible responses.

Set USE_ADAPTIVE_AGENTS=true to use adaptive agents for local/self-hosted models.
"""

import os

# Check if adaptive agents should be used (for local/self-hosted models)
USE_ADAPTIVE_AGENTS = os.getenv('USE_ADAPTIVE_AGENTS', 'false').lower() == 'true'

if USE_ADAPTIVE_AGENTS:
    # Use adaptive agents for local/self-hosted models
    from .adaptive_solution_researcher import create_adaptive_solution_researcher as create_solution_researcher_agent
    from .adaptive_code_agent import create_adaptive_code_agent as create_code_agent
    from .adaptive_debug_agent import create_adaptive_debug_agents as create_debug_agents
    print("Using adaptive agents for local/self-hosted models")
else:
    # Use standard agents for OpenAI models
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
