from __future__ import annotations

import os
import logging
from agents import Agent, OpenAIChatCompletionsModel, ModelSettings
from openai.types.shared import Reasoning
from agents.mcp import MCPServerStdio
from openai import AsyncOpenAI
import asyncio
import tempfile
import subprocess
import time
from typing import Any, Callable, TypeVar, Optional
from utils.retry_utils import retry_mcp_server_connect
from utils.mcp_server_manager import get_or_create_mcp_server, get_mcp_server_info

# Import output types
from .output_types import ExecutionReport

# Import memory tools
import sys
import os
# Add core to path for memory_tools import
core_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'core')
if core_path not in sys.path:
    sys.path.insert(0, core_path)

# Import memory tools from direct_tools
from mcp_servers_and_tools.direct_tools.memory_tools import search_memory

# Direct tools (for running without MCP servers)
from mcp_servers_and_tools.direct_tools import (
    execute_code,
    check_installed_packages,
    install_dependencies,
    tavily_search,
    extract_code_from_url,
    retrieve_extracted_code,
)

T = TypeVar('T')

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

CODE_AGENT_PROMPT = """
ROLE: Python Code Execution Specialist

You are an expert Python code executor for computational materials science and chemistry tasks

CRITICAL: YOU MUST EXECUTE CODE, NOT JUST ANALYZE IT

**INPUT FORMAT:**
You will receive:
- User ID (used for memory search)
- Original user query
- Required packages list
- Code solution to execute

**OUTPUT FORMAT:**
```json
{
  "user_id": "User identifier for memory search",
  "original_user_query": "exact text of the user's query",
  "executed_code": "# The actual code that was executed\nimport package1\nimport package2\n\n# Code here...",
  "execution_output": "Raw output from code execution including results, logs, errors",
  "needs_debugging": True or False (boolean)
}
```
**CRITICAL REQUIREMENTS:**
- Output EXACTLY ONE JSON object with fields: user_id, original_user_query, executed_code, execution_output, needs_debugging
- Do NOT output multiple JSON objects or any text before/after the JSON
- The output must be a single, valid, parseable JSON object
- needs_debugging is a boolean: use False if code executed successfully and meets user requirements, use True if errors occurred or results are incorrect/incomplete

CRITICAL RULES:
- Execute Python code using `execute_code` tool. You CANNOT skip tool calls and provide text-only responses
- For non-Python executables, use result = subprocess.run(command, capture_output=True, text=True, check=True) within Python code to call external programs so you can still execute the code
- Research and reference to meet all the requirements in STEP 2: `tavily-search`, `extract_code_from_url`, `retrieve_extracted_code`
- You can ONLY make necessary modifications to the code BEFORE execution to satisfy STEP 2 requirements (e.g., env variables, required prints for final results, subprocess logging scaffold, necessary unit conversions, preferred built-in command/flag usage, etc.)
- After you think the code meets all the requirements in STEP 2, you MUST execute the code ONLY ONCE (single `execute_code` call). Do NOT retry, re-run, or self-debug
- **IMPORTANT - TOOL USAGE LIMIT:** You have a maximum of 10 tool calls total. Do NOT exceed 10 tool calls

WORKFLOW STEPS:

**MEMORY SEARCH (OPTIONAL):**
- You can use 'search_memory' tool to find similar past solutions or user preferences
- Use user_id as one of the arguments for search_memory calls

STEP 1: ANALYZE INPUT (MANDATORY)
- EXTRACT the original user query, required packages, and code solution
- UNDERSTAND what the code is supposed to do
- If the code does Not include the correct environment variable setup where needed (e.g., os.getenv("MP_API_KEY") for Materials Project queries. Note: this is not provided in the user query but are stored in the environment variables exactly called 'MP_API_KEY'), you MUST correct the code to include the correct environment variable setup before code execution
- When using MPRester, ALWAYS make sure to use from mp_api.client import MPRester (with api_key=os.getenv('MP_API_KEY')) instead of from pymatgen.ext.matproj import MPRester
- **CRITICAL OUTPUT REQUIREMENT**: If the code does not print ALL specific numerical/string results that the user needs (e.g., energy, forces, etc.), you MUST modify the code to include proper print statements that output the complete results. This ensures that the results can be further processed by the output processor agent for proper analysis

STEP 2: SOLUTION REQUIREMENTS VERIFICATION (MANDATORY)
Before executing, you MUST ensure the solution (code and approach) meets these requirements. If unclear, you may use `tavily-search`, `extract_code_from_url`, and `retrieve_extracted_code` to consult official docs/examples:
- NEVER hardcode molecular/materials structures manually (e.g., it is totally FORBIDDEN to directly write XYZ coordinates in code). ALWAYS generate structures with established tools/libraries. Ensure coordinates are in correct units (xyz uses Angstrom by default). You can use `tavily-search`, `extract_code_from_url`, and `retrieve_extracted_code` to find the commonly used tool/library for generating structures with official code examples
- Optimize the structure before performing calculations unless the task explicitly requires using the original/fixed geometry
- ALWAYS use established computational software/packages for calculations
- ALWAYS follow documented protocols and best practices. When the target software provides a built-in command/flag that directly computes the requested property, you MUST prefer it over ad-hoc manual implementations
- If the current code uses a custom implementation (e.g., deriving the property by definition), you MUST use `tavily-search`, `extract_code_from_url`, and `retrieve_extracted_code` to see if you can find the official built-in command/flag to compute the requested property (very likely you can find it). If so, modify the code to replace the custom implementation before code execution
- ALWAYS use default parameters and settings unless specified otherwise
- ALWAYS ensure the solution is reproducible and based on verified methods
- ALWAYS check and convert units to match user requirements - if the code/software outputs in different units (e.g., Hartree, Angstroms) than what the user needs (e.g., eV, nanometers), perform the necessary unit conversions
- **CRITICAL**: strongly prefer all numbers to be code‑derived via library/API calls; avoid remembered, hard‑coded, or example numbers
- **CRITICAL OUTPUT REQUIREMENT**: You MUST print ALL specific numerical/string results that the user needs. For example, if the user asks for energy and forces, print the actual energy value and all force components, not just their shapes or summaries. This ensures that the results are clearly presented and can be properly understood by the user
- SUBPROCESS EXECUTION VERIFICATION: If the code uses subprocess.run(), ensure it uses capture_output=True, text=True, check=True, saves output to a timestamped log file, prints the log path, and parses results as needed. Example:
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
If any requirement is not met, revise the code BEFORE proceeding.

STEP 3: PACKAGE MANAGEMENT (MANDATORY)
- IMMEDIATELY call `check_installed_packages` to get all installed packages
- IF any required packages are missing, call `install_dependencies` with missing packages
- WAIT for installation to complete before proceeding

STEP 4: CODE EXECUTION (MANDATORY)
- IMMEDIATELY call `execute_code` tool with the prepared code
- YOU MUST EXECUTE THE CODE EXACTLY ONCE - NO RETRIES, NO SELF-DEBUGGING

STEP 5: RESULT EVALUATION (MANDATORY)
- IF execution succeeds WITHOUT errors AND meets user requirements:
  * Set needs_debugging = False
  * Provide the raw execution output
- IF execution fails OR does not meet user requirements:
  * Set needs_debugging = True
  * Provide the raw execution output for debug agents
  * Do NOT modify the code or attempt any fixes—stop after a single execution, you should immediately output EXACTLY ONE JSON object with the required fields

ABSOLUTELY FORBIDDEN:
- Providing code analysis without execution
- Skipping tool calls and giving text-only responses
- Proceeding to STEP 3 without verifying the code meets all the requirements in STEP 2
- **CRITICAL**: Attempting to debug or fix code yourself (let debug agents handle this)
- Making unecessary changes to the provided code before execution

SUCCESS CRITERIA:
- Code executed using the `execute_code` tool with the exact provided code
- Code meets all the requirements in STEP 2
- Raw execution results captured
- Correct assessment of whether debugging is needed

Your response must include actual tool calls and execution results. Start immediately with STEP 1

**CRITICAL TOOL USAGE LIMITATION: You cannot use tools infinitely. You are limited to a maximum of 10 tool calls (including execute_code, check_installed_packages, install_dependencies, etc.). You must execute the code and output results either when you are satisfied with the code OR when you reach the 10-tool limit. You must accurately determine whether debugging is needed based on the execution results**
"""

class CodeAgent(Agent):
    """Code Agent with MCP servers for basic code execution."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._servers_initialized = False
        self._server_init_lock = asyncio.Lock()
        self._message_printed = False
        
        # Get project root directory
        current_dir = os.path.dirname(os.path.abspath(__file__))  # deep_solver_with_memory/
        conversational_system_dir = os.path.dirname(current_dir)  # conversational_system/
        workspace_root = os.path.dirname(conversational_system_dir)  # project root

        # Set up directories relative to workspace root
        self._temp_dir = os.path.join(workspace_root, "conversational_system", "temp_code")
        self._saved_dir = os.path.join(workspace_root, "conversational_system", "saved_code")
        self._mcp_workspace_path = os.path.join(workspace_root, "mcp_servers_and_tools", "workspace_server", "build", "index.js")
        self._mcp_memory_path = os.path.join(workspace_root, "mcp_servers_and_tools", "memory_server", "src", "memory_mcp.py")
        self._venv_path = os.path.join(workspace_root, ".venv")
        
        # Create directories if they don't exist
        os.makedirs(self._temp_dir, exist_ok=True)
        os.makedirs(self._saved_dir, exist_ok=True)
    
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
                    print("\n💻 Code agent connected to MCP servers:")
                    for server in self.mcp_servers:
                        print(f"   • {server.name}")
                    self._message_printed = True
                return

            servers = []
            
            # Calculate the path to the project root (needed for multiple servers)
            current_dir = os.path.dirname(os.path.abspath(__file__))  # deep_solver_with_memory/
            conversational_system_dir = os.path.dirname(current_dir)  # conversational_system/
            workspace_root = os.path.dirname(conversational_system_dir)  # project root
            
            # Workspace Server
            try:
                # Prefer user-space Node 18+ via nvm if available
                nvm_dir = os.path.join(os.path.expanduser("~"), ".nvm", "versions", "node")
                node_cmd = "node"
                try:
                    if os.path.isdir(nvm_dir):
                        # pick the highest semantic version directory starting with 'v'
                        candidates = [d for d in os.listdir(nvm_dir) if d.startswith("v")]
                        if candidates:
                            latest = sorted(candidates, key=lambda s: [int(p) for p in s.lstrip('v').split('.')])[-1]
                            maybe = os.path.join(nvm_dir, latest, "bin", "node")
                            if os.path.exists(maybe):
                                node_cmd = maybe
                except Exception:
                    pass
                
                workspace_server_config = {
                    "name": "mcp_servers_and_tools/workspace_server",
                    "client_session_timeout_seconds": 500,
                    "params": {
                        "command": node_cmd,
                        "args": [self._mcp_workspace_path],
                        "env": {
                            "CODE_STORAGE_DIR": self._temp_dir,
                            "SAVED_FILES_DIR": self._saved_dir,
                            "ENV_TYPE": "venv-uv",
                            "UV_VENV_PATH": self._venv_path,
                            "PROJECT_ROOT": workspace_root,
                            "FORBIDDEN_PATH": os.path.join(workspace_root, "benchmark_tasks_and_results"),
                            "MCP_QUIET": "1",
                            "NODE_ENV": "production",
                            "MP_API_KEY": os.getenv("MP_API_KEY", ""),
                        },
                    }
                }
                
                workspace_server = await get_or_create_mcp_server("mcp_servers_and_tools/workspace_server", workspace_server_config, working_dir=workspace_root)
                servers.append(workspace_server)
                
            except Exception as e:
                print(f"❌ Workspace Server failed: {e}")
                raise

            # Tavily Search Server
            try:
                tavily_server_config = {
                    "name": "tavily-search",
                    "client_session_timeout_seconds": 500,
                    "params": {
                        "command": "npx",
                        "args": ["-y", "tavily-mcp@0.2.1"],
                        "env": {
                            "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY", ""),
                            "MCP_QUIET": "1",
                            "NODE_ENV": "production"
                        },
                    }
                }
                
                tavily_server = await get_or_create_mcp_server("tavily-search", tavily_server_config, working_dir=workspace_root)
                servers.append(tavily_server)
            except Exception as e:
                print(f"⚠️  Tavily search unavailable: {e}")

            # Research Server
            try:
                # Use the workspace_root calculated above
                mcp_research_path = os.path.join(workspace_root, "mcp_servers_and_tools/research_server", "src", "research_mcp.py")
                
                research_server_config = {
                    "name": "mcp_servers_and_tools/research_server",
                    "client_session_timeout_seconds": 500,
                    "params": {
                        "command": "python3",
                        "args": [mcp_research_path],
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
                
                research_server = await get_or_create_mcp_server("mcp_servers_and_tools/research_server", research_server_config, working_dir=workspace_root)
                servers.append(research_server)
            except Exception as e:
                print(f"⚠️  Research server unavailable: {e}")

            # Memory Server
            try:
                mcp_memory_path = os.path.join(workspace_root, "mcp_servers_and_tools", "memory_server", "src", "memory_mcp.py")

                memory_server_config = {
                    "name": "mcp_servers_and_tools/memory_server",
                    "client_session_timeout_seconds": 500,
                    "params": {
                        "command": "python3",
                        "args": [mcp_memory_path],
                        "env": {
                            "SUPABASE_URL": os.getenv("SUPABASE_URL"),
                            "SUPABASE_SERVICE_KEY": os.getenv("SUPABASE_SERVICE_KEY"),
                            "SUPABASE_DATABASE_URL": os.getenv("SUPABASE_DATABASE_URL"),
                            "NEO4J_URI": os.getenv("NEO4J_URI"),
                            "NEO4J_USER": os.getenv("NEO4J_USER"),
                            "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD"),
                            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                            "MCP_QUIET": "1",
                            "TRANSPORT": "stdio"
                        },
                    }
                }

                memory_server = await get_or_create_mcp_server("mcp_servers_and_tools/memory_server", memory_server_config, working_dir=workspace_root)
                servers.append(memory_server)
            except Exception as e:
                print(f"⚠️  Memory server unavailable: {e}")

            self.mcp_servers = servers
            self._servers_initialized = True

            # Always print the message when servers are first initialized
            print("\n💻 Code agent connected to MCP servers:")
            for server in self.mcp_servers:
                print(f"   • {server.name}")
            self._message_printed = True
        
    async def get_mcp_tools(self, run_context):
        """Get MCP tools, ensuring servers are initialized first."""
        await self._initialize_servers()
        return await super().get_mcp_tools(run_context)
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        return await super().call_tool(tool_name, arguments)

async def create_code_agent() -> CodeAgent:
    """Create a code agent focused on code execution."""
    try:
        # # Check API key availability (commented out for non-OpenAI models)
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        # NOTE: When using MCP-based CodeAgent, uncomment the block below and comment out the generic Agent below with direct tools.

        # agent = CodeAgent(
        #     name="CodeExecutionAgent",
        #     instructions=CODE_AGENT_PROMPT,
        #     model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),   
        #     output_type=ExecutionReport,
        # )

        # Direct-tools Agent (kept active for running without MCP servers)
        agent = Agent(
            name="CodeExecutionAgent",
            instructions=CODE_AGENT_PROMPT,
            model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),   
            output_type=ExecutionReport,
            tools=[
                search_memory,  # Memory search for past solutions
                check_installed_packages,
                install_dependencies,
                execute_code,
                tavily_search,
                extract_code_from_url,
                retrieve_extracted_code,
            ],
            # Only set this model_settings for OpenAI GPT-5's reasoning models (gpt-5, gpt-5-mini, or gpt-5-nano), for other models, do not set this model_settings
            # model_settings=ModelSettings(reasoning=Reasoning(effort="medium"), verbosity="low")
        )

        return agent
        
    except Exception as e:
        print(f"Error creating code agent: {e}")
        raise

# Export the necessary functions and classes
__all__ = [
    "CodeAgent",
    "create_code_agent"
]