#!/usr/bin/env python3
"""
Direct Tavily Search Tool
A direct implementation of Tavily search without MCP server overhead
"""

import os
from agents import function_tool
from tavily import TavilyClient


# Global Tavily client instance
_tavily_client = None


def get_tavily_client():
    """Get Tavily client instance"""
    global _tavily_client
    if _tavily_client is None:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError("TAVILY_API_KEY environment variable is not set")
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


@function_tool(name_override="tavily-search")
def tavily_search(
    query: str,
    search_depth: str = "advanced",
    max_results: int = 5
) -> str:
    """
    Perform a web search using Tavily and return a summarized result.
    
    Args:
        query: The search query string
        search_depth: Search depth - "basic" or "advanced" (default: "advanced")
        max_results: Maximum number of results to return (default: 5)
    
    Returns:
        Search results as a formatted string
    """
    try:
        tavily_client = get_tavily_client()
        
        response = tavily_client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results
        )
        
        results = response.get("results", [])
        return results or "No results found."
        
    except Exception as e:
        return f"Search error: {str(e)}"

# Export the tool for easy importing
__all__ = ["tavily-search"]

