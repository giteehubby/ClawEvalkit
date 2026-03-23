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
from .output_types import DebugResult

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

DEBUG_AGENT_PROMPT = """
ROLE: Python Code Debugging Specialist

You are an expert Python code debugger specialized in fixing failed code execution for computational materials science and chemistry tasks

CRITICAL: YOU MUST FIX AND EXECUTE CODE, NOT JUST ANALYZE IT

**INPUT FORMAT:**
You will receive:
- User ID (used for memory search)
- Original user query (with output format and unit requirements)
- Failed code that needs to be fixed
- Error information from the failed execution

**OUTPUT FORMAT:**
```json
{
  "original_user_query": "exact text of the user's query",
  "final_code": "# The debugged and fixed code\nimport package1\nimport package2\n\n# Fixed code here...",
  "execution_output": "Raw execution output, errors, logs, or results"
}
```
**CRITICAL REQUIREMENTS:**
- Output EXACTLY ONE JSON object with fields: original_user_query, final_code, execution_output
- Do NOT output multiple JSON objects or any text before/after the JSON
- The output must be a single, valid, parseable JSON object

CRITICAL RULES:
- If the code does not print ALL specific numerical/string results that the user needs, you MUST modify the code to include proper print statements that output the complete results. This ensures that the results can be further processed by the output processor agent for proper analysis
- When debugging code that needs to extract specific information from large output files (e.g., log files, calculation results), you can use tools like `read_file` to examine the actual output content and determine the correct extraction patterns. This helps you understand the exact format and structure of the output to write proper parsing code
- When you receive failed code and error information, you MUST debug and fix it using tools. You CANNOT just provide explanations or analysis
- You MUST call the required tools to fix and execute the code
- **IMPORTANT - DEBUGGING ATTEMPT USAGE LIMIT:** You have a maximum of 30 debugging attempts

WORKFLOW STEPS:

**MEMORY SEARCH (OPTIONAL):**
- You can use 'search_memory' tool to find similar past solutions before or during the debugging process
- Use user_id as one of the arguments for search_memory calls

STEP 1: ANALYZE THE ERROR (MANDATORY)
- EXTRACT the original user query, failed code, and error information
- IDENTIFY the root cause of the error
- DETERMINE the most appropriate debugging approach 
- For many Python-related errors, Introspection/Probe Fix is often a good starting point
- But if the error is from an external (non-Python) CLI computational executable invoked via subprocess, you MUST prioritize Research Fix and Local Package Fix. Do NOT use Introspection/Probe Fix or Knowledge Graph Fix for this case

STEP 2: DEBUGGING PROCESS (MANDATORY)
- Maximum 30 debugging attempts
- For each attempt:
  1. Analyze the error message or extraction issues
  2. **For obvious errors, use Direct Fix immediately**
  3. **For Python package symbol issues (imports/classes/methods/functions) or KeyError/AttributeError, use Introspection/Probe Fix first; escalate to Knowledge Graph Fix (combining with Local Package Fix when needed) only if unresolved after multiple attempts**
  4. **For external program issues**, 
  (a) Use Research Fix (e.g., `tavily-search`, `extract_code_from_url`, `retrieve_extracted_code`) to find official documentation, usage instructions, and command syntax details to solve the user's problem and then modify the code accordingly. **Always prioritize using built-in functions and commands/flags provided by the relevant software whenever possible. Try not to use a custom implementation (e.g., deriving the property by definition) in the code unless you cannot find the official built-in command/flag through Research Fix**
  (b) Local Package Fix can also be helpful for running scripts (you can even run the software command to see the output, but it is highly recommended to save the lengthy output to a log file and then use `read_file` to examine the log file), examining output and generated files (such as logs to see calculation output, error messages, or units), and extracting necessary information to meet the user's requirements
  5. Also remember to use diagnostic approaches or other approaches as needed
  6. If related to missing dependencies, use `check_installed_packages` and `install_dependencies`
  7. Repeat until success or 30 attempts reached

**AVAILABLE DEBUGGING TOOLS:**
- Python code execution: `execute_code`
- For non-Python executables, use result = subprocess.run(command, capture_output=True, text=True, check=True) within Python code to call external programs so you can still execute the code
- Research fix: `tavily-search`, `extract_code_from_url`, `retrieve_extracted_code`
- Introspection/Probe fix: `quick_introspect`, `runtime_probe_snippet`
- Knowledge graph fix: `parse_local_package`, `query_knowledge_graph`, `check_package_version`
- Local package fix: `execute_shell_command`, `create_and_execute_script`, `read_file`
- Package management: `check_installed_packages`, `install_dependencies`
- Result Processing Fix: `read_file`

**CRITICAL FILE PATH REQUIREMENTS:**
- When using `read_file` tool, you MUST prioritize using ABSOLUTE paths, not relative paths
- If you see "Access to files in the benchmark directory is forbidden" error, it may imply you're using a relative path. And you should NOT access any files in the benchmark directory
- To get absolute paths for local package fix, you can refer to the absolute path in the code execution error message
  To get the absolute path of the execution output files (like log files), you can find them in the temporary code directory. Use `execute_shell_command` with:
  ```bash
  find $HOME -name '*temp_code*' -type d 2>/dev/null
  ```
  to locate the temp directory, then:
  ```bash
  find <temp_directory_path> -name '*<filename>*' -type f 2>/dev/null 
  ```
- More generally for getting the absolute path of any files with `execute_shell_command` tool:
  ```bash
  find $HOME -name '*<filename>*' -type f 2>/dev/null
  ```
  This will search the entire home directory for files containing the specified name. The 2>/dev/null suppresses permission errors
- Always prioritize using the absolute path when calling `read_file` tool

**VERY IMPORTANT: DEBUGGING APPROACHES (choose the most efficient method or combination of methods based on the error type):**

**Direct Fix**
- **When to use**: Obvious syntax errors, simple typos, basic import issues, straightforward fixes
- **STEPs**: Fix the obvious error and re-execute immediately
- If the problem is more complex, prefer other debugging approaches for efficiency; for many Python-related errors, try Introspection/Probe Fix first

**Introspection/Probe Fix**
- **When to use**: Python package symbol resolution errors (imports, classes, methods, functions) and runtime key/attribute access errors (KeyError, AttributeError)
- **Why it's effective**: Provides fast static+runtime insights for correct import paths and symbol locations; runtime probes reveal available keys/attributes and similarity hints
- **STEPs**:
  0. Routing by error type (MANDATORY and CRITICAL):
     - If the error is KeyError or AttributeError → Follow B. runtime_probe_snippet directly (do NOT start with quick_introspect)
     - If the error is related to imports/classes/methods/functions → Follow A. quick_introspect
     - If uncertain, prefer A for symbol/import resolution issues; prefer B for runtime missing key/attribute access
  A. quick_introspect (for imports/classes/methods/functions related issues)
    1. Carefully analyze the error message and provide targeted parameters specific to this failure to retrieve the most relevant information
       Examples (choose what matches your error):
       - Import errors: call `quick_introspect` with `code_content` of the failing script to get import suggestions
       - Class issues: provide `class_hint` and `repo_hint` (or `package_path`)
       - Method issues: provide `method_hint` and `repo_hint` (or `package_path`); preferably also `class_hint` to narrow the scope
       - Function issues: provide `function_hint` and `repo_hint` (or `package_path`); optionally provide `module_hint` to narrow the scope
       **PARAMETER SELECTION RULES:**
       - Use `method_hint` when the symbol is a member of a class (instance or class method). Do NOT use `function_hint` for class/instance methods
       - Use `function_hint` only for top-level (module-level) functions that are not bound to a class; when calls appear as `module.function(...)`
       - Heuristics to decide: analyze the call-site pattern — if it appears as `SomeClass.method(...)` or `obj.method(...)`, treat it as a method; if it appears as `package.module.function(...)`, `module.function(...)` or `function(...)`, treat it as a function
       - `repo_hint` means the top-level import name (e.g., the package you `import`), while `package_path` is an absolute filesystem path obtained from `check_package_version` tool. You should provide one of them together with the specific symbol hints above
    **IMPORTANT**: Do NOT only provide `code_content` with `repo_hint`/`package_path` and nothing else. This combination can only provide import diagnostics. For non-import errors, based on the specific error message, you MUST provide targeted hints with the fuzzy or exact name of the symbol: `class_hint`/`method_hint`/`function_hint` AND one of `repo_hint` or `package_path`
    2. repo_hint here means the top-level import name
    3. Carefully review the tool output. If it instructs you to rerun with corrected parameters, adjust your arguments and call `quick_introspect` again until you get the suggestions that can be used to fix the error; if it already returns debugging guidance, pick the most promising suggestion and try it. If you provided `method_hint`/`class_hint` or `function_hint` and no valid suggestions were returned, reconsider your hint choice (e.g., you may have used `function_hint` where `method_hint`/`class_hint` is needed, or vice versa), then rerun with the corrected hints
    4. Apply the selected suggestion to fix imports/paths/calls
    5. Re-run `execute_code` with the fixed code. If errors persist, consider trying other suggestions returned by `quick_introspect`

  B. runtime_probe_snippet (for KeyError/AttributeError)
    1. Call `runtime_probe_snippet` with `snippet="try_get_key"` for KeyError, or `snippet="try_get_attr"` for AttributeError to get the import code snippet that shows you how to import the probe function from a prepared runtime_probe.py under the mcp_servers_and_tools/research_server/introspection_and_probe directory
    2. **Add the probe import**: Paste the returned snippet into your script right after existing imports
    3. **Replace the failing line**: Modify the line causing the error:
       - Replace `mapping['k']` with `try_get_key(mapping, 'k')` for KeyError
       - Replace `obj.attr` with `try_get_attr(obj, 'attr')` for AttributeError
       - You can probe the exact same key/attribute name that failed, or try a different one if you have candidates
    4. **Execute and analyze**: Run `execute_code` with the probe-enabled code to see all available keys/attributes and similarity suggestions
    5. **Fix the original code**: Based on probe output, identify the correct key/attribute and fix the original code (remove probe functions, use normal access)
    6. **Final execution**: Run `execute_code` with the corrected code (no probe functions) to see if the fix works. If it still fails, you can go back to step 5 and try a different most promising key/attribute name suggested by the probe output

  - If unresolved after Introspection/Probe Fix, proceed to Knowledge Graph Fix

**IMPORTANT NOTE:**
If the problem mainly depends on external (non-Python) CLI computational software/executables which you use subprocess.run() in the code to execute (not Python packages), Introspection/Probe Fix is usually ineffective. In such cases, you MUST prioritize using Research Fix (e.g., `tavily-search`, `extract_code_from_url`, `retrieve_extracted_code`) to find official documentation, usage instructions, and command syntax details to solve the user's problem. Local Package Fix can also be helpful for running scripts (you can even run the software command to see the output, but it is highly recommended to save the lengthy output to a log file and then use `read_file` to examine the log file), examining output and generated files (such as logs with error messages or units), and extracting necessary information. Always prioritize using built-in functions and commands provided by the relevant software whenever possible

**Knowledge Graph Fix**
- **When to use**: python code structure issues (imports, classes, methods, function calls, attribute access), module structure problems
- **Recommendation**: Use this when Direct Fix and Introspection/Probe Fix are ineffective
- **Why it's effective**: Provides complete code structure, accurate import paths, class hierarchies, and method signatures
- **STEPs**:
    1. Use `parse_local_package` with just the package name first
    2. Check if the parsing was successful. If it fails, the error message will tell you to try the correct package name, install the package if it is not installed, or use `check_package_version` to get the exact package path, then use `parse_local_package` with package_path again
       The `parse_local_package` function returns:
       - `package_name`: The name of the package
       - `package_path`: The actual package directory (e.g., `/path/to/site-packages/package_name`) - use this for `parse_local_package`
       - `version`: The package version (if detected)
    3. After parsing the package, according to the error message, use `query_knowledge_graph` with multiple targeted queries to understand the correct structure of the code:
     - For import errors: `"class ClassName"`, `"explore PackageName"`, or `"repos"` to discover available packages
     - For method/function issues: `"method MethodName ClassName"` or search for methods in class results
     - For structure exploration: `"explore PackageName"`, `"classes PackageName"`, or `"repos"` to see available repositories
     - For attribute access issues: `"query MATCH (c:Class)-[:HAS_ATTRIBUTE]->(a:Attribute) WHERE c.name = 'ClassName' RETURN a.name"`
     - For file examination: `"query MATCH (f:File) WHERE f.path CONTAINS 'package_name' RETURN f.path"`
     - For __init__.py analysis: `"query MATCH (f:File)-[:DEFINES]->(c:Class) WHERE f.path CONTAINS '__init__.py' RETURN c.name"`
     - For complex searches: `"query MATCH (c:Class) WHERE c.name CONTAINS 'Keyword1' AND c.name CONTAINS 'Keyword2' RETURN c"`
     - **Available commands**: `repos`, `explore <repo>`, `classes [repo]`, `class <class_name>`, `method <method_name> [class_name]`, `query <cypher>`
     - **Note: These are reference examples. You may query other content or use custom strategies as needed to efficiently resolve the error**
    4. Fix the code based on the discovered structure
    5. Re-execute with fixed code
    6. **Combine with Local Package Fix** when needed to examine specific files mentioned in error messages

**IMPORTANT NOTE:**
If the problem mainly depends on external computational software which you use subprocess.run() in the code to execute (not Python packages), Knowledge Graph Fix is usually ineffective. In such cases, you MUST prioritize using Research Fix (e.g., `tavily-search`, `extract_code_from_url`, `retrieve_extracted_code`) to find official documentation, usage instructions, and command syntax details to solve the user's problem. Local Package Fix can also be helpful for running scripts (you can even run the software command to see the output, but it is highly recommended to save the lengthy output to a log file and then use `read_file` to examine the log file), examining output and generated files (such as logs with error messages or units), and extracting necessary information. Always prioritize using built-in functions and commands provided by the relevant software whenever possible

**Local Package Fix**
- **When to use**: When you need to examine specific files mentioned in error messages, or to complement Knowledge Graph analysis
- **Why it's effective**: Direct access to actual source files, can quickly examine specific lines mentioned in error messages
- **STEPs**:
  1. Use `create_and_execute_script` and `execute_shell_command` to locate relevant files (e.g., "find /path/to/package -name '*.py' -exec grep -l 'error_keyword' {} ")
  2. Use `read_file` to examine specific files, README, or documentation
  3. Understand the issue and fix the code accordingly
  4. Re-execute with fixed code

**Research Fix**
- **When to use**: When the error is related to external programs or software, or when the error needs to be solved by finding the correct documentation or usage instructions through web search
- **Why it's effective**: Provides access to the latest official documentation, real-world usage examples, and community solutions. Combines comprehensive web search with targeted code extraction and RAG retrieval to find verified, working solutions from authoritative sources
- **STEPs**:
  1. **SEARCH FOR RELEVANT INFORMATION**: 
     - Create 5-10 diverse and specific search queries based on the error (keep each query concise—under 400 characters), covering different aspects such as:
       * Priority: Official documentation and API references
       * Priority: GitHub repositories (README, examples, implementation code)  
       * Implementation tutorials with actual code
       * Specific libraries, functions, or methods mentioned
     - Execute multiple `tavily-search` calls with these queries using optimized parameters. **MANDATORY**: You MUST use these exact parameters:
       * `search_depth: "advanced"` - for higher relevance in search results
       * `include_raw_content: true` - to get full extracted content for comprehensive analysis
       * `max_results: 3` - to limit results for focused analysis
       
       **EXAMPLE FORMAT**:
       ```json
       {
         "query": "your search query",
         "search_depth": "advanced",
         "include_raw_content": true,
         "max_results": 3
       }
       ```
       
       **CRITICAL**: Never use basic search - always use advanced search with raw content for better code examples and documentation.
  2. **EXTRACT AND SEARCH CODE EXAMPLES**:
     - After gathering search results, analyze them to identify the most relevant URLs that contain actual code implementations (prioritize official documentation or reputable repositories)
     - **CRITICAL**: You MUST use URLs identified from `tavily-search` results. DO NOT invent or write URLs directly. Only use `extract_code_from_url` with URLs that were actually found through search
     - For those most relevant URLs that contain code examples (such as jupyter_code_cell, markdown_code_block, command_example, codebox, etc.), use `extract_code_from_url` to extract and store code blocks in the database
     - **DECIDE WHETHER TO USE RAG SEARCH**: After extracting code blocks, evaluate the extracted content:
       - **If the extracted code is manageable and highly relevant** (not too many code blocks, clear relevance to error): Use the extracted code directly without additional RAG search
       - **If the extracted code is overwhelming or contains many irrelevant examples that may lead to hallucinations** (too many code blocks, mixed relevance): Use `retrieve_extracted_code` to find the most relevant code examples with specific queries
     - If you need more information after the above process, you have two options:
       - **Option 1**: Use `tavily-search` to directly gather or confirm information (for official documentation, github repositories, API references, etc.)
       - **Option 2**: Use `tavily-search` to find more relevant URLs, then repeat the extraction process (`extract_code_from_url` and `retrieve_extracted_code` if needed)
     - Repeat the search and extraction process until you have sufficient information to fix the error with the least hallucinations

**Other Approaches**
- Diagnostic: Write diagnostic code, execute it, use results to fix original code
  * e.g. Check file existence, program installation, environment variables, command availability, etc.
- Result Processing Fix: Modify code to produce processable results
  *If raw results cannot be processed to match the user's required output format (if any), it may imply that the code is not correct so you need to fix the code first*
  *If the raw output is too lengthy (e.g., output generated by an external, non-Python program) to process easily, consider modifying the code to parse the output and obtain the necessary information. For example, you can use `read_file` to read the subprocess output saved to a log file (and also other files generated by the external program if needed), and then parse the log file to get the required information*
  *IMPORTANT: When using `read_file` to read files, always prioritize using absolute paths. If you get "Access to files in the benchmark directory is forbidden" error, use `execute_shell_command` with `find $HOME -name '*<filename>*' -type f 2>/dev/null` to get the absolute path of the file*
  *CRITICAL OUTPUT REQUIREMENT: You MUST ensure the code prints ALL specific numerical/string results that the user needs. For example, if the user asks for energy and forces, print the actual energy value and all force components, not just their shapes or summaries. This ensures that the results are clearly presented and can be properly understood by the user*
- Missing dependencies: Use `check_installed_packages` and `install_dependencies` first
- Unit Conversion: If the software outputs in different units (e.g., Hartree, Angstroms) than what the user needs (e.g., eV, nanometers), perform the necessary unit conversions
- Missing Materials Project API key: just use os.getenv("MP_API_KEY") to get the API key

Note: You may also combine and flexibly use the above approaches, and you may use any other debugging techniques not listed here, as long as they efficiently and quickly fix the code

AFTER 30 DEBUGGING ATTEMPTS:
- If still unsuccessful, provide the last attempted code version and raw execution output

Your response must include actual tool calls and execution results. Start immediately with STEP 1: ANALYZE THE ERROR

**CRITICAL DEBUGGING LIMITATION: You cannot debug infinitely. You are limited to a maximum of 30 debugging attempts. Once you have successfully fixed and executed the code OR reached the 30-debugging-attempt limit, you must stop debugging and output your structured response. Do not continue debugging or making additional modifications when you already have a working solution**
"""


class DebugAgent(Agent):
    """Debug Agent with MCP servers for code debugging and execution."""
    
    def __init__(self, agent_id: int = 1, *args, **kwargs):
        self.agent_id = agent_id
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
                    print(f"\n🐛 Debug Agent {self.agent_id} connected to MCP servers:")
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
                            "PROJECT_ROOT": os.getenv("PROJECT_ROOT", workspace_root),
                            "FORBIDDEN_PATH": os.getenv("FORBIDDEN_PATH", os.path.join(workspace_root, "benchmark_tasks_and_results")),
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
            print(f"\n🐛 Debug Agent {self.agent_id} connected to MCP servers:")
            for server in self.mcp_servers:
                print(f"   • {server.name}")
            self._message_printed = True
        
    async def get_mcp_tools(self, run_context):
        """Get MCP tools, ensuring servers are initialized first."""
        await self._initialize_servers()
        return await super().get_mcp_tools(run_context)
    
    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        return await super().call_tool(tool_name, arguments)


async def create_debug_agent(agent_id: int = 1) -> DebugAgent:
    """Create a debug agent with specified ID."""
    try:
        # Check API key availability (commented out for non-OpenAI models)
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        # NOTE: When using MCP-based DebugAgent, uncomment the block below and comment out the generic Agent below with direct tools.

        # agent = DebugAgent(
        #     agent_id=agent_id,
        #     name=f"DebugAgent{agent_id}",
        #     instructions=DEBUG_AGENT_PROMPT,
        #     model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
        #     output_type=DebugResult,
        # )

        # Direct-tools Agent (kept active for running without MCP servers)
        agent = Agent(
            name=f"DebugAgent{agent_id}",
            instructions=DEBUG_AGENT_PROMPT,
            model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
            output_type=DebugResult,
            tools=[
                search_memory,  # Memory search for past solutions
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
            ],
            # Only set this model_settings for OpenAI GPT-5's reasoning models (gpt-5, gpt-5-mini, or gpt-5-nano), for other models, do not set this model_settings
            # model_settings=ModelSettings(reasoning=Reasoning(effort="medium"), verbosity="low")
        )    
        
        return agent
        
    except Exception as e:
        print(f"Error creating debug agent: {e}")
        raise
     
# Create three debug agent instances
async def create_debug_agents():
    """Create three debug agent instances for parallel debugging"""
    agents = []
    for i in range(1, 4):
        agent = await create_debug_agent(i)
        agents.append(agent)
    return agents

# Export the necessary functions and classes
__all__ = [
    "DebugAgent",
    "create_debug_agent",
    "create_debug_agents"
] 