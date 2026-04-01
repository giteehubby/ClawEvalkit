#!/usr/bin/env python3
"""
Direct Tools Package
Direct implementations of tools without MCP server overhead for faster execution
"""

from .search_tool import tavily_search
from .research_tools import (
    extract_code_from_url,
    retrieve_extracted_code,
    quick_introspect,
    runtime_probe_snippet,
    parse_local_package,
    query_knowledge_graph
)
from .workspace_tools import (
    execute_code,
    read_file,
    install_dependencies,
    check_installed_packages,
    check_package_version,
    save_file,
    execute_shell_command,
    create_and_execute_script
)

__all__ = [
    # Search tools
    "tavily_search",
    # Research tools
    "extract_code_from_url",
    "retrieve_extracted_code",
    "quick_introspect",
    "runtime_probe_snippet",
    "parse_local_package",
    "query_knowledge_graph",
    # Workspace tools
    "execute_code",
    "read_file",
    "install_dependencies",
    "check_installed_packages",
    "check_package_version",
    "save_file",
    "execute_shell_command",
    "create_and_execute_script",
]

# Memory tools are NOT imported by default to avoid side effects at import time
# (creates mem0 instance, requires OPENAI_API_KEY, SUPABASE_DATABASE_URL, Neo4j)
# Import directly when needed:
#   from mcp_servers_and_tools.direct_tools.memory_tools import search_memory, save_to_memory