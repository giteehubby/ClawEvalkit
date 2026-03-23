#!/usr/bin/env python3
"""
Minimal test for runtime_probe_snippet MCP tool.
Calls the tool with each snippet type and prints the returned snippet.
"""
import asyncio
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


async def main() -> None:
    server_params = get_server_params()
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            for kind in ["try_get_key", "try_get_attr"]:
                print("\n=== Request:", kind, "===")
                result = await session.call_tool("runtime_probe_snippet", {"snippet": kind})
                if result.content:
                    text = result.content[0].text
                    print(text)
                else:
                    print("No content returned")


if __name__ == "__main__":
    asyncio.run(main())
