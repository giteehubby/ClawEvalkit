#!/usr/bin/env python3
"""
Test for Memory Server MCP tools.
Tests search_memory and save_to_memory tools.
"""
import asyncio
import os
import sys
import logging
from pathlib import Path

# Suppress noisy logging from external libraries
logging.basicConfig(level=logging.WARNING)
for logger_name in ["httpx", "openai", "mcp", "supabase", "neo4j", "mem0", "vecs"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

# Load environment variables from project root
project_root = Path(__file__).parent.parent
load_dotenv(project_root / '.env')


def get_server_params() -> StdioServerParameters:
    """Get server parameters for MCP client connection."""
    return StdioServerParameters(
        command="python",
        args=["-u", "src/memory_mcp.py"],
        cwd=str(Path(__file__).parent),
        env={
            **os.environ,  # Pass all current environment variables
            "SUPABASE_DATABASE_URL": os.environ.get("SUPABASE_DATABASE_URL", ""),
            "NEO4J_URI": os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            "NEO4J_USER": os.environ.get("NEO4J_USER", "neo4j"),
            "NEO4J_PASSWORD": os.environ.get("NEO4J_PASSWORD", "password"),
            "ENABLE_GRAPH_MEMORY": os.environ.get("ENABLE_GRAPH_MEMORY", "true"),
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        }
    )


async def test_list_tools(session: ClientSession) -> None:
    """Test listing available tools."""
    print("\n" + "=" * 60)
    print("TEST: List Available Tools")
    print("=" * 60)

    tools = await session.list_tools()
    print(f"Found {len(tools.tools)} tools:")
    for tool in tools.tools:
        print(f"  - {tool.name}: {tool.description[:80]}...")

    # Verify expected tools exist
    tool_names = [t.name for t in tools.tools]
    expected_tools = ["search_memory", "save_to_memory"]
    for expected in expected_tools:
        if expected in tool_names:
            print(f"  ✅ {expected} found")
        else:
            print(f"  ❌ {expected} NOT found")


async def test_save_memory(session: ClientSession, user_id: str) -> None:
    """Test saving memory."""
    print("\n" + "=" * 60)
    print("TEST: Save Memory")
    print("=" * 60)

    test_content = """Ac₂InGa is Heusler structured and crystallizes in the cubic Fm̅3m space group. Ac is bonded in a body-centered cubic geometry to four equivalent In and four equivalent Ga atoms. All Ac-In bond lengths are 3.49 Å. All Ac-Ga bond lengths are 3.49 Å. In is bonded in a body-centered cubic geometry to eight equivalent Ac atoms. Ga is bonded in a body-centered cubic geometry to eight equivalent Ac atoms."""

    print(f"Saving test content for user: {user_id}")
    print(f"Content: {test_content}")

    result = await session.call_tool("save_to_memory", {
        "content": test_content,
        "user_id": user_id
    })

    if result.content:
        print(f"Result: {result.content[0].text}")
    else:
        print("No content returned")


async def test_search_memory(session: ClientSession, user_id: str) -> None:
    """Test searching memory."""
    print("\n" + "=" * 60)
    print("TEST: Search Memory")
    print("=" * 60)

    queries = [
        "space group of Ac₂InGa"
    ]

    for query in queries:
        print(f"\nSearching for: '{query}'")
        result = await session.call_tool("search_memory", {
            "query": query,
            "user_id": user_id
        })

        if result.content:
            text = result.content[0].text
            # Truncate long results
            if len(text) > 500:
                text = text[:500] + "..."
            print(f"Result:\n{text}")
        else:
            print("No content returned")


async def main() -> None:
    """Main test function."""
    print("=" * 60)
    print("Memory Server MCP Test")
    print("=" * 60)

    # Check required environment variables
    required_vars = ["SUPABASE_DATABASE_URL", "OPENAI_API_KEY"]
    missing_vars = [v for v in required_vars if not os.environ.get(v)]

    if missing_vars:
        print(f"⚠️  Missing required environment variables: {missing_vars}")
        print("Please set these in your .env file")
        print("Continuing with limited testing...")

    # Use a test user ID
    test_user_id = "test_user_memory_server"

    server_params = get_server_params()

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                print("\n🚀 Initializing MCP session...")
                await session.initialize()
                print("✅ Session initialized successfully")

                # Run tests
                await test_list_tools(session)

                # Only run data tests if we have the required env vars
                if not missing_vars:
                    await test_save_memory(session, test_user_id)

                    # Wait a moment for the save to complete
                    print("\n⏳ Waiting for memory to be processed...")
                    await asyncio.sleep(2)

                    await test_search_memory(session, test_user_id)
                else:
                    print("\n⚠️  Skipping data tests due to missing environment variables")

                print("\n" + "=" * 60)
                print("✅ All tests completed!")
                print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
