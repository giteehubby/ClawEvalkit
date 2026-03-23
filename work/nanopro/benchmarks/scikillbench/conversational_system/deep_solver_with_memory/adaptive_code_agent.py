#!/usr/bin/env python3
"""
Adaptive Code Execution Agent
Dynamically sets output_type to enable both tool calling and structured output
"""
from agents import Agent, OpenAIChatCompletionsModel

# Import from the original code_agent
from .code_agent import CodeAgent, CODE_AGENT_PROMPT, MODEL_NAME, client
from .output_types import ExecutionReport

# Import memory tools
from mcp_servers_and_tools.direct_tools.memory_tools import search_memory

# Import direct tools
from mcp_servers_and_tools.direct_tools import (
    check_installed_packages,
    install_dependencies,
    execute_code,
    tavily_search,
    extract_code_from_url,
    retrieve_extracted_code,
)


# NOTE: When using MCP-based AdaptiveCodeAgent, uncomment the block below and comment out the generic Agent below with direct tools.

# class AdaptiveCodeAgent(CodeAgent):
class AdaptiveCodeAgent(Agent):
    """Adaptive Code Agent with dynamic output_type

    Workflow:
    1. Start with output_type=None to allow tool calling
    2. SDK will detect target_output_type when tools are done
    3. SDK automatically injects output_type and runs again
    4. Final round outputs structured data
    """

    def __init__(self, *args, **kwargs):
        # Store the target output type from kwargs before modifying it
        self.target_output_type = kwargs.get('output_type', ExecutionReport)

        # Start with no output_type to allow tool calling
        kwargs['output_type'] = None

        super().__init__(*args, **kwargs)


async def create_adaptive_code_agent() -> AdaptiveCodeAgent:
    """Create adaptive code agent"""
    try:
        # NOTE: When using MCP-based AdaptiveCodeAgent, uncomment the block below and comment out the generic Agent below with direct tools.

        # agent = AdaptiveCodeAgent(
        #     name="AdaptiveCodeAgent",
        #     instructions=CODE_AGENT_PROMPT,
        #     model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
        #     output_type=ExecutionReport
        # )

        # Direct-tools Agent (kept active for running without MCP servers)
        agent = AdaptiveCodeAgent(
            name="AdaptiveCodeAgent",
            instructions=CODE_AGENT_PROMPT,
            model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
            output_type=ExecutionReport,
            tools=[
                search_memory,
                check_installed_packages,
                install_dependencies,
                execute_code,
                tavily_search,
                extract_code_from_url,
                retrieve_extracted_code,
            ]
        )

        return agent

    except Exception as e:
        print(f"❌ Error creating adaptive code agent: {e}")
        raise


# Export
__all__ = [
    "AdaptiveCodeAgent",
    "create_adaptive_code_agent"
]
