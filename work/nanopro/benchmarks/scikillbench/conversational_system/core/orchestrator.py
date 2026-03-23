"""
Orchestrator Agent - Main Conversation Controller

The Orchestrator is the primary agent that interacts with users in natural conversation.
It intelligently routes between:
- Quick solution path (for simple problems with good memory matches)
- Deep solver path (for complex problems requiring research)

Features:
- Memory integration for user preferences and past solutions
- Direct package management and code execution
- Intelligent path selection based on problem complexity
- Multi-turn conversation with user feedback handling
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel

# Add project root to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
conversational_system_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(conversational_system_dir)
sys.path.insert(0, project_root)

# Set workspace paths for conversational system BEFORE importing workspace_tools
# This ensures execute_code uses conversational_system directories, not deep_solver_benchmark
if not os.getenv("CODE_STORAGE_DIR"):
    os.environ["CODE_STORAGE_DIR"] = os.path.join(conversational_system_dir, "temp_code")
if not os.getenv("SAVED_FILES_DIR"):
    os.environ["SAVED_FILES_DIR"] = os.path.join(conversational_system_dir, "saved_code")

# Import direct tools for package management and code execution
from mcp_servers_and_tools.direct_tools.workspace_tools import (
    check_installed_packages,
    install_dependencies,
    execute_code
)

# Import memory tools
from mcp_servers_and_tools.direct_tools.memory_tools import search_memory, save_to_memory

# Import prompts
from ..config.prompts import get_orchestrator_prompt


# Model configuration (configurable via environment variables)
# OpenAI: use defaults or set AGENT_MODEL_NAME=gpt-4o, o3, etc.
# Local/self-hosted models: set OPENAI_BASE_URL, AGENT_MODEL_NAME, and REQUIRE_OPENAI_API_KEY=false
MODEL_NAME = os.getenv("AGENT_MODEL_NAME", "o3")
_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
_require_api_key = os.getenv("REQUIRE_OPENAI_API_KEY", "true").lower() == "true"

client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY") if _require_api_key else "EMPTY",  # vLLM doesn't need real API key
    base_url=_base_url,
    timeout=500.0,
    max_retries=3,
)


class OrchestratorAgent(Agent):
    """
    Orchestrator Agent with memory integration and intelligent path selection.

    This agent doesn't use structured output (no output_type) to allow
    natural, flexible conversation with users.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


async def create_orchestrator(
    deep_solver_tool: Any
) -> OrchestratorAgent:
    """
    Create the Orchestrator agent with all integrated tools.

    Args:
        deep_solver_tool: The solve_with_deep_solver function tool (required)

    Returns:
        Configured Orchestrator agent
    """
    try:
        # Check API key
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        # Build tools list
        tools = [
            search_memory,             # Memory search
            check_installed_packages,  # List all installed packages (from workspace_tools)
            install_dependencies,      # Package installation (from workspace_tools)
            execute_code,              # Direct code execution (from workspace_tools)
            save_to_memory,            # Save successful solutions
            deep_solver_tool           # Deep problem-solving workflow (PATH B)
        ]

        # Create agent with dynamic prompt (fresh timestamp each time)
        agent = OrchestratorAgent(
            name="MaterialsScienceAssistant",
            instructions=get_orchestrator_prompt(),  # Generate fresh prompt with current date
            model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
            tools=tools
            # No output_type - allows free-form conversation
        )

        return agent

    except Exception as e:
        print(f"Error creating Orchestrator agent: {e}")
        raise


# Export
__all__ = [
    'OrchestratorAgent',
    'create_orchestrator'
]
