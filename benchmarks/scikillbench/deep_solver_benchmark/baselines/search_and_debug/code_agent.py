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
import mlflow

# MLflow configuration is centralized in test_workflow.py

# Import output types
from .output_types import ExecutionReport

# Direct tools (for running without MCP servers)
from mcp_servers_and_tools.direct_tools import (
    execute_code,
    check_installed_packages,
    install_dependencies,
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

CODE_AGENT_PROMPT = """
ROLE: Python Code Execution Specialist

You are an expert Python code executor/debugger for computational materials science and chemistry tasks

CRITICAL: YOU MUST EXECUTE CODE, NOT JUST ANALYZE IT

**INPUT FORMAT:**
You will receive:
- Original user query (with output format and unit requirements)
- Required packages list
- Code solution to execute

**OUTPUT FORMAT:**
```json
{
  "original_user_query": "exact text of the user's query",
  "executed_code": "# The actual code that was executed\nimport package1\nimport package2\n\n# Code here...",
  "execution_output": "Raw output from code execution including results, logs, errors"
}
```
**CRITICAL REQUIREMENTS:**
- Output EXACTLY ONE JSON object with fields: original_user_query, executed_code, execution_output
- Do NOT output multiple JSON objects or any text before/after the JSON
- The output must be a single, valid, parseable JSON object

You MUST determine if debugging is needed based on execution results. If debugging is needed, you should debug and re-run the code before giving the final response (max 30 attempts)

CRITICAL RULES:
- When you receive ANY code, IMMEDIATELY call `check_installed_packages` to get all installed packages
- IF any required packages are missing, call `install_dependencies` with missing packages
- WAIT for installation to complete before proceeding
- After you have installed all the required packages, you MUST directly execute it using `execute_code` tool
- You CANNOT just provide explanations or analysis

Your response must include actual tool calls and execution results

**CRITICAL DEBUGGING LIMITATION: You cannot debug infinitely. You are limited to a maximum of 30 debugging attempts. Once you have successfully fixed and executed the code OR reached the 30-debugging-attempt limit, you must stop debugging and output your structured response. Do not continue debugging or making additional modifications when you already have a working solution**
"""

class CodeAgent(Agent):
    """Code Agent with MCP servers for basic code execution."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._servers_initialized = False
        self._server_init_lock = asyncio.Lock()
        self._message_printed = False
        
        # Get workspace root directory
        # Calculate the path to the project root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        workspace_root = os.path.dirname(os.path.dirname(parent_dir))  # project root
        
        # Set up directories relative to workspace root
        self._temp_dir = os.path.join(workspace_root, "deep_solver_benchmark", "temp_code")
        self._saved_dir = os.path.join(workspace_root, "deep_solver_benchmark", "saved_code")
        self._mcp_workspace_path = os.path.join(workspace_root, "mcp_servers_and_tools/workspace_server", "build", "index.js")
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
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            workspace_root = os.path.dirname(os.path.dirname(parent_dir))  # project root
            
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
        # Let MLflow autolog handle tool call tracing automatically
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
                check_installed_packages,
                install_dependencies,
                execute_code,
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