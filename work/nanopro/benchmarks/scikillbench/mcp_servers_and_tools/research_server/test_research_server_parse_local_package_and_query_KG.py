#!/usr/bin/env python3
"""
Test for parse_local_package MCP tool to check pip show package path detection.
"""
import asyncio
import json
import subprocess
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def get_server_params() -> StdioServerParameters:
    # Provide minimal env to allow server startup
    import os
    return StdioServerParameters(
        command="python",
        args=["-u", "src/research_mcp.py"],
        cwd=str(Path(__file__).parent),
        env={
            **os.environ,  # Pass all current environment variables
            "SUPABASE_URL": os.environ.get("SUPABASE_URL", "dummy"),
            "SUPABASE_SERVICE_KEY": os.environ.get("SUPABASE_SERVICE_KEY", "dummy"),
            "NEO4J_URI": os.environ.get("NEO4J_URI"),
            "NEO4J_USER": os.environ.get("NEO4J_USER"),
            "NEO4J_PASSWORD": os.environ.get("NEO4J_PASSWORD"),
            "USE_KNOWLEDGE_GRAPH": "true",
            "GENERATE_CODE_SUMMARY": "true",
            "TRANSPORT": "stdio"
        }
    )


async def test_parse_local_package():
    """Test parse_local_package MCP tool with mlip package"""
    print("\n🧪 Testing parse_local_package MCP tool...")
    
    server_params = get_server_params()
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("\n=== Testing parse_local_package ===")
            try:
                result = await session.call_tool("parse_local_package", {
                    "package_path": "mp_api"
                })
                
                if result.content:
                    text = result.content[0].text
                    print("📄 MCP tool result:")
                    
                    # Try to parse as JSON to see the structure
                    try:
                        data = json.loads(text)
                        print(f"✅ Success: {data.get('success', 'unknown')}")
                        
                        if 'package_path' in data:
                            print(f"📍 Package path detected by MCP tool: {data['package_path']}")
                        
                        if 'error' in data:
                            print(f"❌ Error: {data['error']}")
                            
                        # Print first 500 chars of response for overview
                        print(f"\n📋 Response preview (first 1500 chars):")
                        print(text[:500] + "..." if len(text) > 1500 else text)
                        
                    except json.JSONDecodeError:
                        print("📄 Raw result (not JSON):")
                        print(text[:1500] + "..." if len(text) > 1500 else text)
                        
                else:
                    print("❌ No content returned from MCP tool")
                    
            except Exception as e:
                print(f"❌ MCP tool call failed: {e}")
            
            # After testing parse_local_package, test knowledge graph queries
            await test_query_knowledge_graph(session)


async def test_query_knowledge_graph(session):
    """Test query_knowledge_graph to explore mp_api repository and find BondsRester"""
    print("\n=== Testing query_knowledge_graph for mp_api ===")
    
    try:
        # First, check if mp_api repository exists
        print("🔍 Checking available repositories...")
        repos_result = await session.call_tool("query_knowledge_graph", {
            "command": "repos"
        })
        
        if repos_result.content:
            repos_text = repos_result.content[0].text
            print("📋 Available repositories:")
            print(repos_text[:300] + "..." if len(repos_text) > 300 else repos_text)
            
            # Check if mp_api is in the repositories
            repos_data = json.loads(repos_text)
            if repos_data.get('success') and 'mp_api' in repos_data.get('data', {}).get('repositories', []):
                print("✅ mp_api repository found!")
                
                # Explore mp_api repository
                print("\n🔍 Exploring mp_api repository...")
                explore_result = await session.call_tool("query_knowledge_graph", {
                    "command": "explore mp_api"
                })
                
                if explore_result.content:
                    explore_text = explore_result.content[0].text
                    explore_data = json.loads(explore_text)
                    print(f"📊 mp_api statistics: {explore_data.get('data', {}).get('statistics', {})}")
                
                # Search for classes in mp_api
                print("\n🔍 Searching for classes in mp_api...")
                classes_result = await session.call_tool("query_knowledge_graph", {
                    "command": "classes mp_api"
                })
                
                if classes_result.content:
                    classes_text = classes_result.content[0].text
                    classes_data = json.loads(classes_text)
                    classes_list = classes_data.get('data', {}).get('classes', [])
                    print(f"📋 Found {len(classes_list)} classes in mp_api")
                    
                    # Look for BondsRester specifically
                    bonds_rester_classes = [cls for cls in classes_list if 'bondsrester' in cls.get('name', '').lower()]
                    if bonds_rester_classes:
                        print(f"🎯 Found BondsRester-related classes: {[cls['name'] for cls in bonds_rester_classes]}")
                        
                        # Get detailed info for the first BondsRester class
                        for cls in bonds_rester_classes:
                            print(f"\n🔍 Exploring class: {cls['name']}")
                            class_result = await session.call_tool("query_knowledge_graph", {
                                "command": f"class {cls['name']}"
                            })
                            
                            if class_result.content:
                                class_text = class_result.content[0].text
                                class_data = json.loads(class_text)
                                if class_data.get('success'):
                                    class_info = class_data.get('data', {}).get('class', {})
                                    methods = class_info.get('methods', [])
                                    print(f"📋 Class {cls['name']} has {len(methods)} methods:")
                                    for method in methods[:5]:  # Show first 5 methods
                                        print(f"  - {method['name']}({', '.join(method.get('parameters', []))})")
                                    if len(methods) > 5:
                                        print(f"  ... and {len(methods) - 5} more methods")
                            break
                    else:
                        print("🔍 No BondsRester-related classes found. Showing first 10 classes:")
                        for cls in classes_list[:10]:
                            print(f"  - {cls['name']}")
                        
                        # Try a custom query to search for 'BondsRester' in class names
                        print("\n🔍 Searching for 'BondsRester' in class names using custom query...")
                        search_result = await session.call_tool("query_knowledge_graph", {
                            "command": "query \"MATCH (r:Repository {name: 'mp_api'})-[:CONTAINS]->(f:File)-[:DEFINES]->(c:Class) WHERE toLower(c.name) CONTAINS 'bondsrester' OR toLower(c.full_name) CONTAINS 'bondsrester' RETURN c.name as class_name, c.full_name as full_name LIMIT 10\""
                        })
                        
                        if search_result.content:
                            search_text = search_result.content[0].text
                            search_data = json.loads(search_text)
                            if search_data.get('success'):
                                results = search_data.get('data', {}).get('results', [])
                                if results:
                                    print(f"🎯 Found {len(results)} classes containing 'BondsRester':")
                                    for result in results:
                                        print(f"  - {result['class_name']} ({result['full_name']})")
                                else:
                                    print("❌ No classes containing 'BondsRester' found")
            else:
                print("❌ mp_api repository not found in available repositories")
                
    except Exception as e:
        print(f"❌ Query knowledge graph failed: {e}")


async def main() -> None:
    print("=" * 60)
    print("🔬 Testing parse_local_package Package Path Detection")
    print("=" * 60)
    
    # First check what pip show returns directly
    # check_pip_show_location()
    
    # Then test the MCP tool
    await test_parse_local_package()
    
    print("\n" + "=" * 60)
    print("✅ Test completed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

