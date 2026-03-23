#!/usr/bin/env python3
"""
Deep Solver Agents

The 4-agent multi-agent system for computational materials science tasks:
- Solution Researcher: Research solutions using web search and code extraction
- Code Agent: Write and execute Python code
- Debug Agent: Systematic debugging with multiple strategies
- Output Processor: Select best result and format output

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
    from .adaptive_solution_researcher import AdaptiveSolutionResearcher as SolutionResearcherAgent
    from .adaptive_code_agent import AdaptiveCodeAgent as CodeAgent
    from .adaptive_debug_agent import AdaptiveDebugAgent as DebugAgent
    print("Using adaptive agents for local/self-hosted models")
else:
    # Use standard agents for OpenAI models
    from .solution_researcher import create_solution_researcher_agent, SolutionResearcherAgent
    from .code_agent import create_code_agent, CodeAgent
    from .debug_agent import create_debug_agents, DebugAgent

from .output_processor_agent import create_output_processor_agent, OutputProcessorAgent
from .output_types import FinalResult, SolutionResponse, ExecutionReport, DebugResult

__all__ = [
    # Agent factories
    "create_solution_researcher_agent",
    "create_code_agent",
    "create_debug_agents",
    "create_output_processor_agent",
    # Agent classes
    "SolutionResearcherAgent",
    "CodeAgent",
    "DebugAgent",
    "OutputProcessorAgent",
    # Output types
    "FinalResult",
    "SolutionResponse",
    "ExecutionReport",
    "DebugResult",
]
