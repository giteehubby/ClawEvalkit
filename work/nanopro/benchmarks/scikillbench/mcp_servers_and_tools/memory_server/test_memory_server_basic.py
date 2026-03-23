#!/usr/bin/env python3
"""
Basic test for Memory Server - tests MCP structure without database connection.
"""
import asyncio
import sys

# Test 1: Import test
print("=" * 60)
print("TEST 1: Import Memory Server Module")
print("=" * 60)

try:
    sys.path.insert(0, 'src')
    from memory_mcp import (
        mcp,
        search_memory,
        save_to_memory,
        MATERIALS_SCIENCE_EXTRACTION_PROMPT,
        MATERIALS_SCIENCE_GRAPH_PROMPT,
        ENABLE_GRAPH_MEMORY
    )
    print("✅ All imports successful")
    print(f"   - Server name: {mcp.name}")
    print(f"   - Graph memory enabled: {ENABLE_GRAPH_MEMORY}")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test 2: Check prompts are defined
print("\n" + "=" * 60)
print("TEST 2: Check Custom Prompts")
print("=" * 60)

if MATERIALS_SCIENCE_EXTRACTION_PROMPT:
    print(f"✅ Extraction prompt defined ({len(MATERIALS_SCIENCE_EXTRACTION_PROMPT)} chars)")
    print(f"   Preview: {MATERIALS_SCIENCE_EXTRACTION_PROMPT[:100]}...")
else:
    print("❌ Extraction prompt not defined")

if MATERIALS_SCIENCE_GRAPH_PROMPT:
    print(f"✅ Graph prompt defined ({len(MATERIALS_SCIENCE_GRAPH_PROMPT)} chars)")
    print(f"   Preview: {MATERIALS_SCIENCE_GRAPH_PROMPT[:100]}...")
else:
    print("❌ Graph prompt not defined")

# Test 3: Check MCP tools are registered
print("\n" + "=" * 60)
print("TEST 3: Check MCP Tools Registration")
print("=" * 60)

# FastMCP stores tools in _tool_manager
try:
    if hasattr(mcp, '_tool_manager'):
        tools = mcp._tool_manager._tools
        print(f"✅ Found {len(tools)} registered tools:")
        for name, tool in tools.items():
            print(f"   - {name}")
    else:
        # Alternative way to check
        print("⚠️  Cannot directly access tool manager, checking decorated functions...")
        print("   - search_memory: defined" if search_memory else "   - search_memory: NOT defined")
        print("   - save_to_memory: defined" if save_to_memory else "   - save_to_memory: NOT defined")
except Exception as e:
    print(f"⚠️  Tool check error: {e}")

print("\n" + "=" * 60)
print("✅ Basic structure tests completed!")
print("=" * 60)
print("\nNote: To test actual memory operations, ensure:")
print("  1. SUPABASE_DATABASE_URL is correctly set")
print("  2. OPENAI_API_KEY is set")
print("  3. (Optional) Neo4j is running for graph memory")
