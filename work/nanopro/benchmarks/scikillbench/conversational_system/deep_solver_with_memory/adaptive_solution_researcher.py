#!/usr/bin/env python3
"""
Adaptive Solution Researcher
Dynamically sets output_type to enable both tool calling and structured output
"""
from agents import Agent, OpenAIChatCompletionsModel

# Import from the original solution_researcher
from .solution_researcher import SolutionResearcherAgent, SOLUTION_RESEARCHER_PROMPT, MODEL_NAME, client
from .output_types import SolutionResponse

# Import memory tools
from mcp_servers_and_tools.direct_tools.memory_tools import search_memory

# Import direct tools
from mcp_servers_and_tools.direct_tools import (
    tavily_search,
    extract_code_from_url,
    retrieve_extracted_code,
    quick_introspect,
)


# NOTE: When using MCP-based AdaptiveSolutionResearcher, uncomment the block below and comment out the generic Agent below with direct tools.

# class AdaptiveSolutionResearcher(SolutionResearcherAgent):
class AdaptiveSolutionResearcher(Agent):
    """Adaptive Solution Researcher with dynamic output_type

    Workflow:
    1. Start with output_type=None to allow tool calling
    2. SDK will detect target_output_type when tools are done
    3. SDK automatically injects output_type and runs again
    4. Final round outputs structured data
    """

    def __init__(self, *args, **kwargs):
        # Store the target output type from kwargs before modifying it
        self.target_output_type = kwargs.get('output_type', SolutionResponse)

        # Start with no output_type to allow tool calling
        kwargs['output_type'] = None

        super().__init__(*args, **kwargs)


async def create_adaptive_solution_researcher() -> AdaptiveSolutionResearcher:
    """Create adaptive solution researcher"""
    try:
        # NOTE: When using MCP-based AdaptiveSolutionResearcher, uncomment the block below and comment out the generic Agent below with direct tools.

        # agent = AdaptiveSolutionResearcher(
        #     name="AdaptiveSolutionResearcher",
        #     instructions=SOLUTION_RESEARCHER_PROMPT,
        #     model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
        #     output_type=SolutionResponse
        # )

        # Direct-tools Agent (kept active for running without MCP servers)
        agent = AdaptiveSolutionResearcher(
            name="AdaptiveSolutionResearcher",
            instructions=SOLUTION_RESEARCHER_PROMPT,
            model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
            output_type=SolutionResponse,
            tools=[
                search_memory,
                tavily_search,
                extract_code_from_url,
                retrieve_extracted_code,
                quick_introspect,
            ]
        )

        return agent

    except Exception as e:
        print(f"❌ Error creating adaptive solution researcher: {e}")
        raise


# Export
__all__ = [
    "AdaptiveSolutionResearcher",
    "create_adaptive_solution_researcher"
]
