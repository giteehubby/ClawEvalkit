from pydantic import BaseModel, Field
from typing import Optional, List, Any, Callable, TypeVar, Dict
import json
import re
import os
import sys
import asyncio
import subprocess
import time
from pathlib import Path

from agents import Agent, OpenAIChatCompletionsModel, ModelSettings
from openai.types.shared import Reasoning
from openai import AsyncOpenAI
from agents.mcp import MCPServerStdio
from mcp.server.fastmcp import Context
from dotenv import load_dotenv
from utils.retry_utils import retry_mcp_server_connect
from utils.mcp_server_manager import get_or_create_mcp_server, get_mcp_server_info

# Import output types
from .output_types import SolutionResponse

# direct tools (use these when running without MCP servers)
from mcp_servers_and_tools.direct_tools import (
    tavily_search,
)

T = TypeVar('T')

# Model configuration
# OpenAI: use defaults or set AGENT_MODEL_NAME=gpt-4o, o3, etc.
# Local/self-hosted models: set OPENAI_BASE_URL, AGENT_MODEL_NAME, and REQUIRE_OPENAI_API_KEY=false
MODEL_NAME = os.getenv("AGENT_MODEL_NAME", "o3")
_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
_require_api_key = os.getenv("REQUIRE_OPENAI_API_KEY", "true").lower() == "true"

client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY") if _require_api_key else "EMPTY",
    base_url=_base_url,
    timeout=500.0,
    max_retries=3,
)

# Prompt for the solution researcher agent
SOLUTION_RESEARCHER_PROMPT = """
ROLE: Materials Science Solution Researcher

You are a materials science and chemistry researcher who specializes in finding code solutions through web search

NOTE: All the requests here require code implementation. Your primary goal is to provide working code solutions with accurate package dependencies

**OUTPUT FORMAT:**
```json
{
  "original_user_query": "exact text of the user's query",
  "required_packages": ["package1", "package2", "package3"],
  "code_solution": "# Complete Python code\nimport package1\nimport package2\n\n# Your solution code here..."
}
```
**CRITICAL REQUIREMENTS:**
- Output EXACTLY ONE JSON object with fields: original_user_query, required_packages, code_solution
- Do NOT output multiple JSON objects or any text before/after the JSON
- The output must be a single, valid, parseable JSON object

You can use 'tavily-search' to help you synthesize the code solution

CRITICAL REQUIREMENTS FOR YOUR RESPONSE:
    - You MUST provide the complete original user query exactly as received
    - You MUST identify and list ALL required packages needed for the solution
    - You MUST provide complete, executable, correct and relevant Python code based on verified sources
    - Your code MUST include environment variable setup where needed (e.g., os.getenv("MP_API_KEY") for Materials Project queries. Note: this is not provided in the user query but are stored in the environment variables exactly called 'MP_API_KEY')
    - When using MPRester, you MUST use the code 'from mp_api.client import MPRester' with os.getenv('MP_API_KEY') instead of 'from pymatgen.ext.matproj import MPRester'
    - Ensure the code follows patterns verified from your research. No hallucinations are allowed

Your ultimate goal is to provide a complete, researched code solution that addresses the user's needs

**CRITICAL TOOL USAGE LIMITATION: You cannot use tools infinitely. You are limited to a maximum of 20 tool calls (tavily-search). Once you have gathered sufficient information to provide a complete solution OR reached the 20-tool limit, you must stop using tools and output your structured response. Do not over-research or continue searching when you already have enough information to synthesize the solution**
"""

class SolutionResearcherAgent(Agent):
    """Solution Researcher Agent with MCP servers for web search."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._servers_initialized = False
        self._server_init_lock = asyncio.Lock()
        self._message_printed = False
        
        # Get workspace root directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        self._workspace_root = os.path.dirname(os.path.dirname(parent_dir))  # project root
        
        # Set up directories relative to workspace root
        self._mcp_research_path = os.path.join(self._workspace_root, "mcp_servers_and_tools/research_server", "src", "research_mcp.py")
    
    def reset_message_flags(self):
        """Reset message flags to allow showing connection info again."""
        self._message_printed = False
    
    async def _initialize_servers(self):
        """Initialize MCP servers with proper locking."""
        # Use lock to prevent multiple simultaneous initializations
        async with self._server_init_lock:
            if self._servers_initialized:
                # Always show connection info if message flag is reset
                if not self._message_printed:
                    print("\n✅ Solution researcher connected to MCP servers:")
                    for server in self.mcp_servers:
                        print(f"   • {server.name}")
                    self._message_printed = True
                return

            servers = []
            
            # Tavily Search Server
            try:
                tavily_server_config = {
                    "name": "tavily-search",
                    "client_session_timeout_seconds": 500,
                    "params": {
                        "command": "npx",
                        "args": ["-y", "tavily-mcp@0.2.1"],
                        "env": {
                            "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
                            "MCP_QUIET": "1",
                            "NODE_ENV": "production"
                        },
                    }
                }
                
                tavily_server = await get_or_create_mcp_server("tavily-search", tavily_server_config, working_dir=self._workspace_root)
                servers.append(tavily_server)
            except Exception as e:
                print(f"⚠️  Tavily search unavailable: {e}")
            
            self.mcp_servers = servers
            self._servers_initialized = True

            # Always print the message when servers are first initialized
            print("\n✅ Solution researcher connected to MCP servers:")
            for server in self.mcp_servers:
                print(f"   • {server.name}")
            self._message_printed = True
    
    async def get_mcp_tools(self, run_context):
        """Get MCP tools, ensuring servers are initialized first."""
        await self._initialize_servers()
        return await super().get_mcp_tools(run_context)
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        # Let MLflow autolog handle tool call tracing automatically
        return await super().call_tool(tool_name, arguments)


async def create_solution_researcher_agent() -> SolutionResearcherAgent:
    """Create and return a solution researcher agent with web search capabilities."""
    try:
        # # Check API key availability (commented out for non-OpenAI models)
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        # NOTE: When using MCP-based SolutionResearcherAgent, uncomment the block below and comment out the generic Agent below with direct tools.

        # agent = SolutionResearcherAgent(
        #     name="SolutionResearcherAgent",
        #     instructions=SOLUTION_RESEARCHER_PROMPT,
        #     model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
        #     output_type=SolutionResponse,
        # )

        # Direct-tools Agent (kept active for running without MCP servers)
        
        agent = Agent(
            name="SolutionResearcherAgent",
            instructions=SOLUTION_RESEARCHER_PROMPT,
            model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
            output_type=SolutionResponse,
            tools=[
                tavily_search,
            ],
            # Only set this model_settings for OpenAI GPT-5's reasoning models (gpt-5, gpt-5-mini, or gpt-5-nano), for other models, do not set this model_settings
            # model_settings=ModelSettings(reasoning=Reasoning(effort="medium"), verbosity="low")
        )
        
        return agent
        
    except Exception as e:
        print(f"Error creating solution researcher agent: {e}")
        raise

# Export the necessary functions and classes
__all__ = [
    "SolutionResearcherAgent",
    "create_solution_researcher_agent"
]