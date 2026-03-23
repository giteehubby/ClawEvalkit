#!/usr/bin/env python3
"""
Test research-server quick_introspect tool

This script will:
1. Connect to MCP server
2. Call quick_introspect with provided code content
"""

import asyncio
import json
import subprocess
import sys
import os
from pathlib import Path
from typing import Dict, Any

# MCP client related imports
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import TextContent
except ImportError:
    print("❌ Need to install MCP client library")
    print("Please run: pip install mcp")
    sys.exit(1)

async def test_quick_introspect():
    """Test quick_introspect tool with provided code content"""
    
    print("🚀 Starting quick_introspect test...")
    
    # Code content to test
    code_content = """import os
from mp_api import MPRester
from pymatgen.computed_entries import Computedentries
from pymatgen.core import composition"""
    
    print("\n" + "="*60)
    print("1. Connect to MCP server and test quick_introspect")
    print("="*60)
    
    try:
        # Set server parameters
        server_params = StdioServerParameters(
            command="python",
            args=["src/research_mcp.py"],
            cwd=str(Path(__file__).parent),
            env={
                **os.environ,  # Pass all current environment variables
                "SUPABASE_URL": os.environ.get("SUPABASE_URL"),
                "SUPABASE_SERVICE_KEY": os.environ.get("SUPABASE_SERVICE_KEY"),
                "NEO4J_URI": os.environ.get("NEO4J_URI"),
                "NEO4J_USER": os.environ.get("NEO4J_USER"),
                "NEO4J_PASSWORD": os.environ.get("NEO4J_PASSWORD"),
                "USE_KNOWLEDGE_GRAPH": "true",
                "GENERATE_CODE_SUMMARY": "true",
                "TRANSPORT": "stdio"
            }
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                print("✓ Successfully connected to MCP server")
                
                # Get server information (optional)
                print("\n📋 Getting server information...")
                try:
                    info = await session.initialize()
                    server_name = getattr(info, 'server_name', 'Unknown')
                    server_version = getattr(info, 'server_version', 'Unknown')
                    print(f"Server name: {server_name}")
                    print(f"Server version: {server_version}")
                except Exception as e:
                    print(f"⚠️  Failed to get server information: {e}")

                # Test 1: quick_introspect tool with code_content
                print("\n🧠 Test 1: quick_introspect with code_content...")
                print(f"Code content to analyze:")
                print("-" * 40)
                print(code_content)
                print("-" * 40)
                
                try:
                    qi_inputs = {
                        "code_content": code_content,
                        "repo_hint": "mp_api",
                        "max_suggestions": 3,
                        "method_hint": "chemsys",
                        "no_imports": False,
                    }
                    qi_result = await session.call_tool("quick_introspect", qi_inputs)
                    if qi_result.content:
                        try:
                            qi_data = json.loads(qi_result.content[0].text)
                            print("✓ quick_introspect result:")
                            print(f"  Success: {qi_data.get('success')}")
                            report = qi_data.get("report", "")
                            print("  Report:")
                            print(report)
                        except json.JSONDecodeError:
                            print("  Raw quick_introspect result:")
                            print(qi_result.content[0].text)
                    else:
                        print("  ⚠️  No return result from quick_introspect")
                except Exception as e:
                    print(f"  ❌ quick_introspect failed: {e}")
                    import traceback
                    traceback.print_exc()

                # Test 2: quick_introspect with repo_hint and method_hint (no code_content)
                print("\n🧠 Test 2: quick_introspect with repo_hint and method_hint...")
                print("Testing: package_path='mp_api', method_hint='search'")
                
                try:
                    qi_inputs_2 = {
                        "package_path": "mp_api",
                        "method_hint": "search",
                        "class_hint": "synthesis",
                        "max_suggestions": 3,
                        "no_imports": False,
                    }
                    qi_result_2 = await session.call_tool("quick_introspect", qi_inputs_2)
                    if qi_result_2.content:
                        try:
                            qi_data_2 = json.loads(qi_result_2.content[0].text)
                            print("✓ quick_introspect result:")
                            print(f"  Success: {qi_data_2.get('success')}")
                            report_2 = qi_data_2.get("report", "")
                            print("  Report:")
                            print(report_2)
                        except json.JSONDecodeError:
                            print("  Raw quick_introspect result:")
                            print(qi_result_2.content[0].text)
                    else:
                        print("  ⚠️  No return result from quick_introspect")
                except Exception as e:
                    print(f"  ❌ quick_introspect failed: {e}")
                    import traceback
                    traceback.print_exc()

                print("\n" + "="*60)
                print("Test completed")
                print("="*60)
                
    except Exception as e:
        print(f"❌ Error occurred during testing: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function"""
    print("quick_introspect test")
    print("=" * 50)
    
    asyncio.run(test_quick_introspect())

if __name__ == "__main__":
    main() 