#!/usr/bin/env python3
"""
Utils Package
Shared utilities for MCP server management, retry logic, and database operations.
"""

from .mcp_server_manager import get_or_create_mcp_server
from .retry_utils import retry_with_backoff, call_tool_with_retry, retry_mcp_server_connect
from .quiet_utils import setup_quiet_mode, silence_external_output, reapply_quiet_mode
from .supabase_utils import get_supabase_client, clear_supabase_tables

__all__ = [
    # MCP server management
    "get_or_create_mcp_server",
    # Retry utilities
    "retry_with_backoff",
    "call_tool_with_retry",
    "retry_mcp_server_connect",
    # Output suppression
    "setup_quiet_mode",
    "silence_external_output",
    "reapply_quiet_mode",
    # Supabase utilities
    "get_supabase_client",
    "clear_supabase_tables",
]

# Other utilities available via direct import:
# from utils.check_neo4j import ...
# from utils.clean_neo4j_repo import ...
# from utils.clean_neo4j_memory import ...
# from utils.supabase_utils import view_supabase_tables, get_table_statistics
# from utils.check_supabase_connection import ...
