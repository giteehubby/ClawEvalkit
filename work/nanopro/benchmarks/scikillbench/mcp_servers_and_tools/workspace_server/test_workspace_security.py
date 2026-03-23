#!/usr/bin/env python3
"""
Security test for workspace server MCP tools.
Tests that all tools are properly restricted to PROJECT_ROOT and forbidden from accessing FORBIDDEN_PATH.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("❌ Need to install MCP client library")
    print("Please run: pip install mcp")
    sys.exit(1)

def get_project_root():
    """Get project root by looking for .git directory"""
    current_path = Path(__file__).resolve()
    while not (current_path / ".git").exists() and current_path.parent != current_path:
        current_path = current_path.parent
    if (current_path / ".git").exists():
        return current_path
    else:
        raise FileNotFoundError("Could not find project root (no .git directory found)")

def get_workspace_server_params():
    project_root = get_project_root()
    workspace_server_path = project_root / "mcp_servers_and_tools/workspace_server" / "build" / "index.js"
    temp_code_dir = project_root / "deep_solver_benchmark" / "temp_code"
    saved_files_dir = project_root / "deep_solver_benchmark" / "saved_code"
    venv_path = project_root / ".venv"
    
    # Create directories if they don't exist
    temp_code_dir.mkdir(parents=True, exist_ok=True)
    saved_files_dir.mkdir(parents=True, exist_ok=True)
    
    # Prefer user-space Node 18+ via nvm if available
    nvm_node = Path.home() / ".nvm" / "versions" / "node" / "v18.20.8" / "bin" / "node"
    node_cmd = str(nvm_node) if nvm_node.exists() else "node"
    
    return StdioServerParameters(
        command=node_cmd,
        args=[str(workspace_server_path)],
        cwd=str(project_root),
        env={
            **os.environ,  # Pass all current environment variables
            "CODE_STORAGE_DIR": str(temp_code_dir),
            "SAVED_FILES_DIR": str(saved_files_dir),
            "ENV_TYPE": "venv",
            "VENV_PATH": str(venv_path),
            "PROJECT_ROOT": str(project_root),
            "FORBIDDEN_PATH": str(project_root / "benchmark_tasks_and_results"),
            "MCP_QUIET": "1",
            "NODE_ENV": "production"
        }
    )

# Test configuration
project_root = get_project_root()
PROJECT_ROOT = str(project_root)
FORBIDDEN_PATH = str(project_root / "benchmark_tasks_and_results")
HOME_DIR = os.path.expanduser("~")  # User's home directory

print(f"🔒 Security Test Configuration:")
print(f"   PROJECT_ROOT: {PROJECT_ROOT}")
print(f"   FORBIDDEN_PATH: {FORBIDDEN_PATH}")
print(f"   HOME_DIR: {HOME_DIR}")
print()

async def test_tool_security():
    """Test security restrictions for all workspace server tools."""
    
    # Start the workspace server
    server_params = get_workspace_server_params()
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                print("✅ Successfully connected to workspace-server")
                
                # List available tools
                tools_result = await session.list_tools()
                available_tools = {tool.name: tool for tool in tools_result.tools}
                print(f"📋 Available tools: {list(available_tools.keys())}")
                print()
                
                # Test cases for each tool (only tools that actually exist in workspace server)
                test_cases = [
                    {
                        "tool": "execute_code",
                        "safe_params": {"code": "print('Hello, World!')", "filename": "test_safe.py"},
                        "unsafe_home_params": {"code": "print('Hello, World!')", "filename": f"{HOME_DIR}/test_home.py"},
                        "unsafe_forbidden_params": {"code": "print('Hello, World!')", "filename": f"{FORBIDDEN_PATH}/test_forbidden.py"},
                        "description": "Execute code tool"
                    },
                    {
                        "tool": "read_file",
                        "safe_params": {"file_path": f"{PROJECT_ROOT}/deep_solver_benchmark/deep_solver/output_types.py"},
                        "unsafe_home_params": {"file_path": f"{HOME_DIR}/.bashrc"},
                        "unsafe_forbidden_params": {"file_path": f"{FORBIDDEN_PATH}/test.txt"},
                        "description": "Read file tool"
                    },
                    {
                        "tool": "save_file", 
                        "safe_params": {"filename": "test_safe.py", "content": "# Safe test file"},
                        "unsafe_home_params": {"filename": f"{HOME_DIR}/test_home.py", "content": "# Test in home"},
                        "unsafe_forbidden_params": {"filename": f"{FORBIDDEN_PATH}/test_forbidden.py", "content": "# Test in forbidden"},
                        "description": "Save file tool"
                    },
                    {
                        "tool": "execute_shell_command",
                        "safe_params": {"command": "cd mcp_servers_and_tools && ls", "working_dir": PROJECT_ROOT},
                        "unsafe_home_params": {"command": "ls", "working_dir": HOME_DIR},
                        "unsafe_forbidden_params": {"command": "ls", "working_dir": FORBIDDEN_PATH},
                        "description": "Execute shell command tool"
                    },
                    {
                        "tool": "create_and_execute_script",
                        "safe_params": {"script_content": "echo 'Safe script'", "filename": "safe_script.sh"},
                        "unsafe_home_params": {"script_content": "echo 'Unsafe script'", "filename": f"{HOME_DIR}/unsafe_script.sh"},
                        "unsafe_forbidden_params": {"script_content": "echo 'Forbidden script'", "filename": f"{FORBIDDEN_PATH}/forbidden_script.sh"},
                        "description": "Create and execute script tool"
                    }
                ]
                
                # Run security tests
                for test_case in test_cases:
                    tool_name = test_case["tool"]
                    if tool_name not in available_tools:
                        print(f"⚠️  Tool '{tool_name}' not available, skipping...")
                        continue
                    
                    print(f"🔍 Testing {tool_name} ({test_case['description']})")
                    print("=" * 60)
                    
                    # Test 1: Safe operation (should succeed)
                    print(f"✅ Test 1: Safe operation in PROJECT_ROOT")
                    print(f"   Parameters: {test_case['safe_params']}")
                    try:
                        result = await session.call_tool(tool_name, test_case["safe_params"])
                        print(f"   Raw Result: {result.content[0].text}")
                    except Exception as e:
                        print(f"   Exception: {e}")
                    print()
                    
                    # Test 2: Unsafe operation - HOME directory (should be blocked)
                    print(f"🚫 Test 2: Unsafe operation - HOME directory access")
                    print(f"   Parameters: {test_case['unsafe_home_params']}")
                    try:
                        result = await session.call_tool(tool_name, test_case["unsafe_home_params"])
                        print(f"   Raw Result: {result.content[0].text}")
                    except Exception as e:
                        print(f"   Exception: {e}")
                    print()
                    
                    # Test 3: Unsafe operation - FORBIDDEN_PATH (should be blocked)
                    print(f"🚫 Test 3: Unsafe operation - FORBIDDEN_PATH access")
                    print(f"   Parameters: {test_case['unsafe_forbidden_params']}")
                    try:
                        result = await session.call_tool(tool_name, test_case["unsafe_forbidden_params"])
                        print(f"   Raw Result: {result.content[0].text}")
                    except Exception as e:
                        print(f"   Exception: {e}")
                    print()
                    
                    print("-" * 60)
                    print()
                
                print("🎯 Security test completed!")
                print("=" * 60)
                print("SUMMARY:")
                print("- All tool calls and their raw results are displayed above")
                print("- You can now analyze the results to verify security restrictions")
                print("- Safe operations in PROJECT_ROOT should succeed")
                print("- Unsafe operations (HOME/FORBIDDEN_PATH) should be blocked")
                
    except Exception as e:
        print(f"❌ Security test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_tool_security())
