#!/usr/bin/env python3
"""
Adaptive Debug Agent
Dynamically sets output_type to enable both tool calling and structured output
"""
from agents import Agent, OpenAIChatCompletionsModel

# Import from the original debug_agent
from .debug_agent import DebugAgent, DEBUG_AGENT_PROMPT, MODEL_NAME, client
from .output_types import DebugResult

# Import memory tools
from mcp_servers_and_tools.direct_tools.memory_tools import search_memory

# Import direct tools
from mcp_servers_and_tools.direct_tools import (
    execute_code,
    create_and_execute_script,
    execute_shell_command,
    read_file,
    check_installed_packages,
    install_dependencies,
    tavily_search,
    extract_code_from_url,
    retrieve_extracted_code,
    quick_introspect,
    runtime_probe_snippet,
    parse_local_package,
    query_knowledge_graph,
    check_package_version,
)


# NOTE: When using MCP-based AdaptiveDebugAgent, uncomment the block below and comment out the generic Agent below with direct tools.

# class AdaptiveDebugAgent(DebugAgent):
class AdaptiveDebugAgent(Agent):
    """Adaptive Debug Agent with dynamic output_type

    Workflow:
    1. Start with output_type=None to allow tool calling
    2. SDK will detect target_output_type when tools are done
    3. SDK automatically injects output_type and runs again
    4. Final round outputs structured data
    """

    def __init__(self, *args, **kwargs):
        # Store the target output type from kwargs before modifying it
        self.target_output_type = kwargs.get('output_type', DebugResult)

        # Start with no output_type to allow tool calling
        kwargs['output_type'] = None

        super().__init__(*args, **kwargs)


async def create_adaptive_debug_agent(agent_id: int = 1) -> AdaptiveDebugAgent:
    """Create adaptive debug agent"""
    try:
        # NOTE: When using MCP-based AdaptiveDebugAgent, uncomment the block below and comment out the generic Agent below with direct tools.

        # agent = AdaptiveDebugAgent(
        #     name=f"AdaptiveDebugAgent{agent_id}",
        #     instructions=DEBUG_AGENT_PROMPT,
        #     model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
        #     output_type=DebugResult
        # )

        # Direct-tools Agent (kept active for running without MCP servers)
        agent = AdaptiveDebugAgent(
            name=f"AdaptiveDebugAgent{agent_id}",
            instructions=DEBUG_AGENT_PROMPT,
            model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
            output_type=DebugResult,
            tools=[
                search_memory,
                check_installed_packages,
                install_dependencies,
                check_package_version,
                execute_code,
                create_and_execute_script,
                execute_shell_command,
                read_file,
                tavily_search,
                extract_code_from_url,
                retrieve_extracted_code,
                quick_introspect,
                runtime_probe_snippet,
                parse_local_package,
                query_knowledge_graph,
            ]
        )

        return agent

    except Exception as e:
        print(f"❌ Error creating adaptive debug agent: {e}")
        raise


async def create_adaptive_debug_agents():
    """Create three adaptive debug agent instances"""
    agents = []
    for i in range(1, 4):
        agent = await create_adaptive_debug_agent(i)
        agents.append(agent)
    return agents


# Export
__all__ = [
    "AdaptiveDebugAgent",
    "create_adaptive_debug_agent",
    "create_adaptive_debug_agents"
]
