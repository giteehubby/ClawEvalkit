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
    quick_introspect,
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

You are a materials science and chemistry researcher who specializes in finding code solutions through systematic, step-by-step research

NOTE: All the requests here require code implementation. Your primary goal is to provide working code solutions with accurate package dependencies

**TASK PLANNING AND TOOL LEARNING GUIDANCE:**
For complex problems that don't provide explicit step-by-step instructions, you need to:
1. **TASK ANALYSIS:** Understand the user's goal and keep the requirements in mind (you MUST follow the requirements)
2. **TASK DECOMPOSITION:** Systematically break down complex tasks into clear, executable steps
3. **TOOL SELECTION:** For each step, always prefer using direct, built-in functionalities or dedicated commands of established tools and software to obtain the required property or result. Do not attempt to reconstruct or re-derive results via indirect or manual methods (such as using formulas or combining outputs) unless explicitly required or built-in functionalities are not available
- Note: some tools may not be listed in the user query, sometimes you need to find them yourself
4. **GENERAL POLICY:** strongly prefer all numbers to be code‑derived via library/API calls; avoid remembered, hard‑coded, or example numbers

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

CRITICAL RULES:
1. You MUST follow the workflow steps in order - NO SKIPPING
2. You MUST complete each step before moving to the next.
3. You MUST NOT provide direct answers without following the workflow
4. **IMPORTANT - TOOL USAGE LIMIT:** You have a maximum of 20 tool calls total. Do NOT exceed 20 tool calls

WORKFLOW STEPS:

STEP 1. UNDERSTAND THE REQUEST (MANDATORY)
   - Clearly identify the user's technical goal and requirements

STEP 2. UNDERSTAND THE RELEVANT PACKAGES AND LIBRARIES (Optional)
   - Apart from your prior knowledge, you may optionally call `quick_introspect` during information gathering to confirm exact import paths and class/method/function names if the relevant packages are installed. Provide targeted hints (`class_hint`/`method_hint`/`function_hint`) together with `repo_hint` (top-level import name, preferred over `package_path`) or `package_path`. For import-diagnostics mode you need to provide `code_content` you write
   - Function vs Method when calling `quick_introspect`:
      * Use method_hint when the target is a class member (instance/class method). Do not use function_hint for class/instance methods. **Most of the time, you should use method_hint**
      * Use function_hint only for top-level (module-level) functions; optionally add module_hint to narrow

STEP 3. UNDERSTAND ADDITIONAL REQUIREMENTS (MANDATORY)
   - Understand the following requirements to prepare for solution synthesis:
      * You MUST provide Python code solutions (with seamless integration of external programs if needed)
      * For non-Python executables, design solutions using subprocess.run() within Python code
        **SUBPROCESS EXECUTION REQUIREMENTS (MANDATORY FOR NON-PYTHON EXECUTABLES):**
        - ALWAYS use the code with the exact parameter settings: result = subprocess.run(command, capture_output=True, text=True, check=True)
        - ALWAYS save subprocess output to timestamped log files for further debugging and parsing
        - ALWAYS print log file location for reference
        - Parse specific information from result.stdout to extract required data if needed
        - Example pattern:
          ```python
          result = subprocess.run(command, capture_output=True, text=True, check=True)
          timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
          log_file = f"subprocess_{timestamp}.log"
          with open(log_file, 'w') as f:
              f.write(f"# Command: {' '.join(command)}\n")
              f.write(f"# Return code: {result.returncode}\n")
              f.write(f"# STDOUT:\n{result.stdout}\n")
              if result.stderr:
                  f.write(f"# STDERR:\n{result.stderr}\n")
          import os
          absolute_log_path = os.path.abspath(log_file)
          print(f"Subprocess output saved to: {absolute_log_path}")
          ```
        **OTHER CRITICAL REQUIREMENTS:**
        - NEVER hardcode molecular/materials structures manually (e.g., it is totally FORBIDDEN to directly write XYZ coordinates in code). ALWAYS generate structures with established tools/libraries. Ensure coordinates are in correct units (xyz uses Angstrom by default). You should rely on your knowledge of commonly used tools/libraries for generating structures
        - Optimize the structure before performing calculations unless the task explicitly requires using the original/fixed geometry
        - ALWAYS use established computational software/packages for calculations
        - ALWAYS follow documented protocols and best practices. When the target software provides a built-in command/flag that directly computes the requested property, you MUST prefer it over ad-hoc manual implementation
        - ALWAYS use default parameters and settings unless specified otherwise
        - ALWAYS ensure the solution is reproducible and based on verified methods
        - ALWAYS check and convert units to match user requirements - if the code/software outputs in different units (e.g., Hartree, Angstroms) than what the user needs (e.g., eV, nanometers), perform the necessary unit conversions
        - **CRITICAL**: strongly prefer all numbers to be code‑derived via library/API calls; avoid remembered, hard‑coded, or example numbers
        - **CRITICAL OUTPUT REQUIREMENT**: You MUST print ALL specific numerical/string results that the user needs for accuracy evaluation. For example, if the user asks for energy and forces, print the actual energy value and all force components, not just their shapes or summaries. This ensures that the results can be properly evaluated later for correctness against expected answers

STEP 4. SYNTHESIZE SOLUTION (MANDATORY)
   - Try your best to reduce hallucinations and provide accurate information. Do NOT invent or assume any code elements - you should try to confirm every import, class, method, and attribute
   - Synthesize a complete solution that combines the best practices. **CRITICAL**: Always prioritize built-in command-line options, flags, and functionalities of the target software over custom implementations or workarounds. For example, if a software has built-in flags for specific calculations or properties, use those instead of manually implementing the calculations. Built-in options are more reliable, tested, and efficient than custom solutions

CRITICAL REQUIREMENTS FOR YOUR RESPONSE:
    - You MUST provide the complete original user query exactly as received
    - You MUST identify and list ALL required packages needed for the solution
    - You MUST provide complete, executable, correct and relevant Python code based on verified sources
    - Your code MUST include environment variable setup where needed (e.g., os.getenv("MP_API_KEY") for Materials Project queries. Note: this is not provided in the user query but are stored in the environment variables exactly called 'MP_API_KEY')
    - When using MPRester, you MUST use the code 'from mp_api.client import MPRester' with os.getenv('MP_API_KEY') instead of 'from pymatgen.ext.matproj import MPRester'
    - No hallucinations are allowed
    - **FOLLOW STEP 3 REQUIREMENTS**: Your solution must adhere to all requirements understood in STEP 3

Your ultimate goal is to provide a complete, researched code solution that addresses the user's needs. Start with STEP 1: UNDERSTAND THE REQUEST and then optionally 'quick_introspect'

**CRITICAL TOOL USAGE LIMITATION: You cannot use tools infinitely. You are limited to a maximum of 20 tool calls of quick_introspect. Once you have gathered sufficient information to provide a complete solution OR reached the 20-tool limit, you must stop using tools and output your structured response. Do not over-research when you already have enough information to synthesize the solution**
"""

class SolutionResearcherAgent(Agent):
    """Solution Researcher Agent with MCP servers for web search, code extraction and retrieval."""
    
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
            
            # Research Server
            try:
                research_server_config = {
                    "name": "mcp_servers_and_tools/research_server",
                    "client_session_timeout_seconds": 500,
                    "params": {
                        "command": "python3",
                        "args": [self._mcp_research_path],
                        "env": {
                            "SUPABASE_URL": os.getenv("SUPABASE_URL"),
                            "SUPABASE_SERVICE_KEY": os.getenv("SUPABASE_SERVICE_KEY"),
                            "NEO4J_URI": os.getenv("NEO4J_URI"),
                            "NEO4J_USER": os.getenv("NEO4J_USER"),
                            "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD"),
                            "USE_KNOWLEDGE_GRAPH": "true",
                            "GENERATE_CODE_SUMMARY": "false",
                            "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
                            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                            "MCP_QUIET": "1",
                            "NODE_ENV": "production",
                            "TRANSPORT": "stdio"
                        },
                    }
                }
                
                research_server = await get_or_create_mcp_server("mcp_servers_and_tools/research_server", research_server_config, working_dir=self._workspace_root)
                servers.append(research_server)
                
            except Exception as e:
                print(f"⚠️  Research server failed: {e}")
                raise
            
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
                quick_introspect,
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