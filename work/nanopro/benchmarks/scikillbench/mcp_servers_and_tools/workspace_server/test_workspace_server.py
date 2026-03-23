#!/usr/bin/env python3
"""
Test workspace-server MCP server functionality.

Tested Tools:
1. check_installed_packages - List all installed packages
2. install_dependencies - Install Python dependencies
3. check_package_version - Check specific package versions
4. execute_code - Execute Python code
5. read_file - Read file content
6. save_file - Save file content
7. execute_shell_command - Execute shell commands
8. create_and_execute_script - Create and execute scripts
"""

import asyncio
import sys
import json
import os
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
    
    print(f"get_workspace_server_params:")
    print(f"  project_root: {project_root}")
    print(f"  workspace_server_path: {workspace_server_path}")
    print(f"  temp_code_dir: {temp_code_dir}")
    print(f"  saved_files_dir: {saved_files_dir}")
    print(f"  venv_path: {venv_path}")
    
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
            "PROJECT_ROOT": str(project_root),  # Explicitly set project root
            "FORBIDDEN_PATH": str(project_root / "benchmark_tasks_and_results"),  # Set forbidden path
            "MCP_QUIET": "1",
            "NODE_ENV": "production"
        }
    )

async def test_check_installed_packages(session: ClientSession):
    print("\n=== Testing check_installed_packages ===")
    try:
        result = await session.call_tool("check_installed_packages", {})
        print("✓ check_installed_packages result:")
        response_data = json.loads(result.content[0].text)
        print(f"  Status: {response_data.get('status')}")
        print(f"  Environment Type: {response_data.get('env_type')}")
        print(f"  Package Manager: {response_data.get('package_manager')}")
        print(f"  Total Packages: {response_data.get('total_packages')}")
        
        # Show first 10 packages as sample
        packages = response_data.get('installed_packages', [])
        if packages:
            print(f"  Sample packages (first 10):")
            for i, pkg in enumerate(packages[:10]):
                print(f"    {i+1}. {pkg.get('name')} {pkg.get('version')}")
            if len(packages) > 10:
                print(f"    ... and {len(packages) - 10} more packages")
        else:
            print("  No packages found")
            
    except Exception as e:
        print(f"❌ check_installed_packages error: {e}")

async def test_install_dependencies(session: ClientSession, packages):
    print(f"\n=== Testing install_dependencies ===")
    print(f"Installing packages: {packages}")
    try:
        result = await session.call_tool("install_dependencies", {"packages": packages})
        print("✓ install_dependencies result:")
        response_data = json.loads(result.content[0].text)
        print(f"  Status: {response_data.get('status')}")
        if response_data.get('output'):
            print(f"  Output: {response_data.get('output')}...")
        if response_data.get('warnings'):
            print(f"  Warnings: {response_data.get('warnings')}...")
        if response_data.get('error'):
            print(f"  Error: {response_data.get('error')}")
            
    except Exception as e:
        print(f"❌ install_dependencies error: {e}")

async def test_check_package_version(session: ClientSession, package_names):
    print(f"\n=== Testing check_package_version ===")
    print(f"Checking packages: {package_names}")
    try:
        result = await session.call_tool("check_package_version", {"packages": package_names})
        print("✓ check_package_version result:")
        response_data = json.loads(result.content[0].text)
        print(f"  Status: {response_data.get('status')}")
        print(f"  Environment Type: {response_data.get('env_type')}")
        print(f"  Package Manager: {response_data.get('package_manager')}")
        
        package_details = response_data.get('package_details', [])
        for pkg in package_details:
            print(f"  Package: {pkg.get('package_name')}")
            print(f"    Version: {pkg.get('version')}")
            print(f"    Path: {pkg.get('package_path')}")
            print(f"    Location: {pkg.get('location')}")
            if pkg.get('error'):
                print(f"    Error: {pkg.get('error')}")
            print()
            
    except Exception as e:
        print(f"❌ check_package_version error: {e}")

async def test_execute_code(session: ClientSession, code, filename=None):
    print(f"\n=== Testing execute_code ===")
    print(f"Code to execute: {code[:100]}...")
    if filename:
        print(f"Filename: {filename}")
    
    try:
        args = {"code": code}
        if filename:
            args["filename"] = filename
            
        result = await session.call_tool("execute_code", args)
        print("✓ execute_code result:")
        response_data = json.loads(result.content[0].text)
        print(f"  Status: {response_data.get('status')}")
        print(f"  File Path: {response_data.get('file_path')}")
        if response_data.get('output'):
            print(f"  Output: {response_data.get('output')}")
        if response_data.get('error'):
            print(f"  Error: {response_data.get('error')}")
        
        return result
            
    except Exception as e:
        print(f"❌ execute_code error: {e}")
        return None

async def test_read_file(session: ClientSession, file_path):
    print(f"\n=== Testing read_file ===")
    print(f"Reading file: {file_path}")
    try:
        result = await session.call_tool("read_file", {"file_path": file_path})
        print("✓ read_file result:")
        response_data = json.loads(result.content[0].text)
        print(f"  Status: {response_data.get('status')}")
        if response_data.get('content'):
            content = response_data.get('content')
            print(f"  Content length: {len(content)} chars")
            print(f"  Content preview: {content[:200]}...")
        if response_data.get('error'):
            print(f"  Error: {response_data.get('error')}")
            
    except Exception as e:
        print(f"❌ read_file error: {e}")

async def test_save_file(session: ClientSession, content, filename):
    print(f"\n=== Testing save_file ===")
    print(f"Saving file: {filename}")
    print(f"Content: {content[:100]}...")
    try:
        result = await session.call_tool("save_file", {"content": content, "filename": filename})
        print("✓ save_file result:")
        response_data = json.loads(result.content[0].text)
        print(f"  Status: {response_data.get('status')}")
        print(f"  File Path: {response_data.get('file_path')}")
        if response_data.get('error'):
            print(f"  Error: {response_data.get('error')}")
            
    except Exception as e:
        print(f"❌ save_file error: {e}")

async def test_execute_shell_command(session: ClientSession, command, working_dir=None):
    print(f"\n=== Testing execute_shell_command ===")
    print(f"Command: {command}")
    if working_dir:
        print(f"Working directory: {working_dir}")
    try:
        args = {"command": command}
        if working_dir:
            args["working_dir"] = working_dir
            
        result = await session.call_tool("execute_shell_command", args)
        print("✓ execute_shell_command result:")
        response_data = json.loads(result.content[0].text)
        print(f"  Status: {response_data.get('status')}")
        if response_data.get('stdout'):
            print(f"  Output: {response_data.get('stdout')}")
        if response_data.get('stderr'):
            print(f"  Stderr: {response_data.get('stderr')}")
        if response_data.get('error'):
            print(f"  Error: {response_data.get('error')}")
            
    except Exception as e:
        print(f"❌ execute_shell_command error: {e}")

async def test_create_and_execute_script(session: ClientSession, script_content, filename):
    print(f"\n=== Testing create_and_execute_script ===")
    print(f"Creating script: {filename}")
    print(f"Script content: {script_content[:100]}...")
    try:
        result = await session.call_tool("create_and_execute_script", {"script_content": script_content, "filename": filename})
        print("✓ create_and_execute_script result:")
        response_data = json.loads(result.content[0].text)
        print(f"  Status: {response_data.get('status')}")
        print(f"  Script Path: {response_data.get('script_path')}")
        if response_data.get('stdout'):
            print(f"  Output: {response_data.get('stdout')}")
        if response_data.get('stderr'):
            print(f"  Stderr: {response_data.get('stderr')}")
        if response_data.get('error'):
            print(f"  Error: {response_data.get('error')}")
            
    except Exception as e:
        print(f"❌ create_and_execute_script error: {e}")

async def main():
    print("🚀 Starting workspace-server functionality test")
    
    server_params = get_workspace_server_params()
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                print("✓ Successfully connected to workspace-server")
                
                # Test 1: Check installed packages
                await test_check_installed_packages(session)
                
                # Test 2: Install ase package
                await test_install_dependencies(session, ["scipy"])
                
                # Test 3: Check ase package version
                await test_check_package_version(session, ["scipy"])
                
                # Test 4: Execute hello world code
                hello_world_code = """print("Hello, World!")
print("This is a test from workspace-server!")
import sys
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")"""
                
                result = await test_execute_code(session, hello_world_code, "hello_world_test.py")
                
                # Test 5: File operations
                print("\n" + "="*60)
                print("📁 Testing File Operations")
                print("="*60)
                
                # Test read_file - read README.md
                await test_read_file(session, "mcp_servers_and_tools/workspace_server/README.md")
                
                # Test save_file
                test_content = """# Test file created by workspace-server
This is a test file to verify save_file functionality.
Created at: $(date)
Content includes:
- Multiple lines
- Numbers: 1234567890
- Simple text content for testing"""
                await test_save_file(session, test_content, "test_save_file.txt")
                
                # Test 6: Shell operations
                print("\n" + "="*60)
                print("🐚 Testing Shell Operations")
                print("="*60)
                
                # Test execute_shell_command - find file, the default working directory is the project root
                await test_execute_shell_command(session, "find . -name 'index.ts' -type f")
                
                # Test execute_shell_command - list directory
                await test_execute_shell_command(session, "ls -la src/", "mcp_servers_and_tools/workspace_server")
                
                # Test execute_shell_command with working directory
                await test_execute_shell_command(session, "pwd && ls -la", "mcp_servers_and_tools")
                
                # Test create_and_execute_script
                script_content = '''#!/bin/bash
echo "=== Test Script Execution ==="
echo "Current directory: $(pwd)"
echo "Current user: $(whoami)"
echo "System info: $(uname -a)"
echo "Python version: $(python3 --version)"
echo "Node version: $(node --version)"
echo "=== Script completed ==="'''
                await test_create_and_execute_script(session, script_content, "test_system_info.sh")
                
                print("\n🎉 All tests completed!")
                
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
