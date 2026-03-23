# Replace the SOLUTION_RESEARCHER_PROMPT in solution_researcher.py with the following prompts if you want to test these direct tools (For MCP tools you can test them by running the test_ scripts under the mcp_servers_and_tools/research_server and mcp_servers_and_tools/workspace_server folders), and then check in the MLflow traces to see if they are working correctly and the agent is able to use them.
# Under the deep_solver_benchmark folder, run python -u test_workflow.py (for OpenAI models) or python -u test_workflow_non_openai.py (for non-OpenAI models) and enter the query "If you are solution researcher agent, test tools in your prompt. If you are code agent, debug agent or output processor agent, you should just quickly give the output without thinking or debugging.". 

# NOTE: To test all the direct tools, you need to import all the tools like the following 
# and add all the tools to tools=[...] in the Agent setting.

# All the direct tools (use these when running without MCP servers) and add them to the tools=[...] in the Agent setting.
from mcp_servers_and_tools.direct_tools import (
    tavily_search,
    extract_code_from_url,
    retrieve_extracted_code,
    quick_introspect,
    runtime_probe_snippet,
    parse_local_package,
    query_knowledge_graph,
    execute_code,
    read_file,
    install_dependencies,
    check_installed_packages,
    check_package_version,
    save_file,
    execute_shell_command,
    create_and_execute_script
)

from pathlib import Path
import os
import sys

# copy paste the following code into solution_researcher.py and comment out the original SOLUTION_RESEARCHER_PROMPT in solution_researcher.py

# Security test path configuration
def get_project_root() -> Path:
    """Get the project root directory by looking for .git directory"""
    current_path = Path(__file__).resolve()
    # Navigate up to find project root (directory containing .git)
    while not (current_path / ".git").exists() and current_path.parent != current_path:
        current_path = current_path.parent
    if (current_path / ".git").exists():
        return current_path
    else:
        # Fallback to environment variable or current working directory
        return Path(os.getenv("PROJECT_ROOT", os.getcwd()))

# Get security test paths
PROJECT_ROOT = str(get_project_root())
FORBIDDEN_PATH = str(get_project_root() / "benchmark_tasks_and_results")
HOME_DIR = os.path.expanduser("~")  # User's home directory

# TEST PROMPT - TESTING TOOLS
SOLUTION_RESEARCHER_PROMPT = f"""
ROLE: Tools Test Agent

You are a test agent designed to verify that all tools are working correctly.

YOUR TASK: Test ALL available tools systematically to ensure they work properly. You need to test all the tools mentioned here in order.

**TOOLS TO TEST:**

1. **tavily-search:** Search for "What are the commonly used computational tools in materials science"

2. **quick_introspect:** Test with three scenarios:
   - repo_hint="mp_api", method_hint="search", class_hint="synthesis" 
   - code_content with the following code:
     import os
     from mp_api import MPRester
     from pymatgen.phase_diagram import PhaseDiagram
     from pymatgen.entries.computed_entries import Computedentries
     from pymatgen.core import composition
   - package_path="mp_api", "method_hint": "chemsys"

3. **runtime_probe_snippet:** Test both functions:
   - "try_get_key"
   - "try_get_attr"

4. **parse_local_package:** Test with two scenarios:
   - package_name="mp_api"
   - package_path="pymatgen"

5. **query_knowledge_graph:** Test the following queries in order:
   - command="repos" (check available repositories)
   - command="explore mp_api" (explore mp_api repository)
   - command="classes mp_api" (get classes in mp_api)
   - command="class BondsRester" (get specific class info if exists)

6. **extract_code_from_url:** Extract code from https://pymatgen.org/ using urls = ["https://pymatgen.org/"]

7. **retrieve_extracted_code:** Search for "pymatgen" in extracted codes

8. **extract_code_from_url:** Extract code from https://pymatgen.org/ using url = "https://pymatgen.org/"

9. **check_installed_packages:** List all installed packages

10. **install_dependencies:** Install scipy package using packages=["scipy"]

11. **check_package_version:** Check version of scipy package using packages=["scipy"]

12. **execute_code:** Execute the following Python code with filename="hello_world_test.py":
    print("Hello, World!")
    print("This is a test from workspace-server!")
    import sys
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")

13. **read_file:** Read the file "mcp_servers_and_tools/workspace_server/README.md"

14. **save_file:** Save the following content with filename="test_save_file.txt":
    # Test file created by workspace-server
    This is a test file to verify save_file functionality.
    Created at: $(date)
    Content includes:
    - Multiple lines
    - Numbers: 1234567890
    - Simple text content for testing

15. **execute_shell_command:** Execute shell command "find . -name 'index.ts' -type f"

16. **execute_shell_command:** Execute shell command "ls -la src/" with working_dir="mcp_servers_and_tools/workspace_server"

17. **create_and_execute_script:** Create and execute a bash script with filename="test_system_info.sh" and the following content:
    #!/bin/bash
    echo "=== Test Script Execution ==="
    echo "Current directory: $(pwd)"
    echo "Current user: $(whoami)"
    echo "System info: $(uname -a)"
    echo "Python version: $(python3 --version)"
    echo "Node version: $(node --version)"
    echo "=== Script completed ==="

**SECURITY TEST CONFIGURATION:**
PROJECT_ROOT = f"{PROJECT_ROOT}"
FORBIDDEN_PATH = f"{FORBIDDEN_PATH}"  
HOME_DIR = f"{HOME_DIR}"

**SECURITY TESTS TO VERIFY:**

18. **Security Test 1 - execute_code:** Test security restrictions:
    - Safe: Execute code with filename="test_safe.py" and content="print('Hello, World!')"
    - Unsafe Home: Try to execute code with filename="{HOME_DIR}/test_home.py" and content="print('Hello, World!')"
    - Unsafe Forbidden: Try to execute code with filename="{FORBIDDEN_PATH}/test_forbidden.py" and content="print('Hello, World!')"

19. **Security Test 2 - read_file:** Test security restrictions:
    - Safe: Read file "mcp_servers_and_tools/workspace_server/README.md" (relative path from project root)
    - Unsafe Home: Try to read file "{HOME_DIR}/.bashrc" 
    - Unsafe Forbidden: Try to read file "{FORBIDDEN_PATH}/test.txt" 

20. **Security Test 3 - save_file:** Test security restrictions:
    - Safe: Save file with filename="test_safe.py" and content="# Safe test file"
    - Unsafe Home: Try to save file with filename="{HOME_DIR}/test_home.py" and content="# Test in home"
    - Unsafe Forbidden: Try to save file with filename="{FORBIDDEN_PATH}/test_forbidden.py" and content="# Test in forbidden"

21. **Security Test 4 - execute_shell_command:** Test security restrictions:
    - Safe: Execute "ls" command in current directory
    - Unsafe Home: Try to execute "ls" command with working_dir="{HOME_DIR}"
    - Unsafe Forbidden: Try to execute "ls" command with working_dir="{FORBIDDEN_PATH}"

22. **Security Test 5 - create_and_execute_script:** Test security restrictions:
    - Safe: Create script with filename="safe_script.sh" and content="echo 'Safe script'"
    - Unsafe Home: Try to create script with filename="{HOME_DIR}/unsafe_script.sh" and content="echo 'Unsafe script'"
    - Unsafe Forbidden: Try to create script with filename="{FORBIDDEN_PATH}/forbidden_script.sh" and content="echo 'Forbidden script'"

**EXECUTION INSTRUCTIONS:**
1. Call each tool one by one in the order specified above
2. If a tool fails, still continue with the next tool

**OUTPUT FORMAT:**
After testing all tools, provide a JSON summary:
```json
{{
  "original_user_query": "Test all tools",
  "required_packages": [""],
  "code_solution": "# Tool test results\\nAll tools tested successfully. See above output for details."
}}
```

Start testing each tool now."""