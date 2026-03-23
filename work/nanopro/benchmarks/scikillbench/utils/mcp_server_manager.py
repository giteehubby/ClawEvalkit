#!/usr/bin/env python3
"""
MCP Server Manager - Manages MCP server connections with reuse capability.
"""

import os
import asyncio
import psutil
import time
from typing import Dict, List, Optional, Tuple
from agents.mcp import MCPServerStdio
from .retry_utils import retry_mcp_server_connect

class MCPServerManager:
    """Manages MCP server connections with reuse capability."""
    
    def __init__(self):
        self._servers: Dict[str, MCPServerStdio] = {}
        self._server_info: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._working_dir = os.getcwd()  # Track the working directory
    
    async def get_or_create_server(
        self, 
        server_name: str, 
        server_config: Dict,
        check_existing: bool = True,
        working_dir: str = None
    ) -> MCPServerStdio:
        """
        Get existing server or create new one.
        
        Args:
            server_name: Name of the server
            server_config: Configuration for creating the server
            check_existing: Whether to check for existing servers first
            working_dir: Working directory for isolation (defaults to current working directory)
        
        Returns:
            MCPServerStdio instance
        """
        if working_dir is None:
            working_dir = os.getcwd()
        
        # Create a unique key that includes the working directory
        server_key = f"{server_name}:{working_dir}"
        
        async with self._lock:
            # Check if we already have a server instance for this working directory
            if server_key in self._servers:
                server = self._servers[server_key]
                try:
                    # Test if the server is still responsive
                    await self._test_server_connection(server)
                    # print(f"✅ Reusing existing {server_name} server (working_dir: {working_dir})")
                    return server
                except Exception as e:
                    print(f"⚠️  Existing {server_name} server not responsive: {e}")
                    # Remove the unresponsive server
                    del self._servers[server_key]
                    if server_key in self._server_info:
                        del self._server_info[server_key]
            
            # Disabled existing process detection to avoid confusion
            # Each agent will create its own servers, but agents within the same process can reuse them
            
            # Create new server
            # print(f"🚀 Creating new {server_name} server (working_dir: {working_dir})...")
            server = MCPServerStdio(**server_config)
            await retry_mcp_server_connect(server, max_retries=3)
            
            # Store the server
            self._servers[server_key] = server
            self._server_info[server_key] = {
                'pid': await self._get_server_pid(server_name, server_config),
                'created_time': time.time(),
                'reused': False,
                'working_dir': working_dir
            }
            
            # print(f"✅ Created new {server_name} server (working_dir: {working_dir})")
            return server
    
    async def _test_server_connection(self, server: MCPServerStdio) -> bool:
        """Test if a server connection is still responsive."""
        try:
            # Try to list tools as a connection test
            # This is a lightweight operation that should work if the server is responsive
            tools = await server.list_tools()
            return True
        except Exception:
            return False
    
    async def _find_existing_server_process(
        self, 
        server_name: str, 
        server_config: Dict,
        working_dir: str
    ) -> Optional[int]:
        """Find existing server process by name and configuration."""
        try:
            current_pid = os.getpid()
            current_process = psutil.Process(current_pid)
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'ppid']):
                try:
                    if not proc.info['cmdline']:
                        continue
                    
                    cmdline = ' '.join(proc.info['cmdline'])
                    
                    # Check if this is the right type of server
                    if not self._matches_server_type(server_name, cmdline, server_config):
                        continue
                    
                    proc_obj = psutil.Process(proc.info['pid'])
                    
                    # Check if it's a recent process (started within last 5 minutes)
                    current_create_time = current_process.create_time()
                    proc_create_time = proc_obj.create_time()
                    time_diff = abs(proc_create_time - current_create_time)
                    
                    if time_diff > 300:  # 5 minutes
                        continue
                    
                    # Check if it's in the same process group, is a child, or is a sibling process
                    try:
                        current_pgid = os.getpgid(current_pid)
                        proc_pgid = os.getpgid(proc.info['pid'])
                        same_process_group = current_pgid == proc_pgid
                        is_child = proc.info['ppid'] == current_pid
                        
                        # For MCP servers, we want to detect servers started by any process in the same working directory
                        # This allows reuse across different single_question_runner processes
                        try:
                            proc_cwd = proc_obj.cwd()
                            if proc_cwd == working_dir:
                                # Accept if same working directory, regardless of process group
                                return proc.info['pid']
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            # Fall back to process group check if we can't get working directory
                            if same_process_group or is_child:
                                return proc.info['pid']
                    except (OSError, ProcessLookupError):
                        continue
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except Exception as e:
            print(f"⚠️  Error finding existing server process: {e}")
        
        return None
    
    def _matches_server_type(self, server_name: str, cmdline: str, server_config: Dict) -> bool:
        """Check if a process matches the server type we're looking for."""
        cmdline_lower = cmdline.lower()
        
        if server_name == "mcp_servers_and_tools/workspace_server":
            return "mcp_servers_and_tools/workspace_server" in cmdline_lower and "index.js" in cmdline_lower
        elif server_name == "tavily-search":
            return "tavily-mcp" in cmdline_lower
        elif server_name == "mcp_servers_and_tools/research_server":
            return "research_mcp.py" in cmdline_lower
        else:
            return server_name.lower() in cmdline_lower
    
    async def _connect_to_existing_process(
        self, 
        server_name: str, 
        server_config: Dict, 
        pid: int
    ) -> MCPServerStdio:
        """Try to connect to an existing server process."""
        # For now, we'll create a new connection
        # In the future, we could implement direct connection to existing processes
        server = MCPServerStdio(**server_config)
        await retry_mcp_server_connect(server, max_retries=2)  # Fewer retries for existing processes
        return server
    
    async def _get_server_pid(self, server_name: str, server_config: Dict) -> Optional[int]:
        """Get the PID of a newly created server."""
        try:
            # Wait a moment for the server to start
            await asyncio.sleep(0.5)
            
            # Find the most recent process that matches our server type
            current_pid = os.getpid()
            current_process = psutil.Process(current_pid)
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    if not proc.info['cmdline']:
                        continue
                    
                    cmdline = ' '.join(proc.info['cmdline'])
                    
                    if not self._matches_server_type(server_name, cmdline, server_config):
                        continue
                    
                    proc_obj = psutil.Process(proc.info['pid'])
                    
                    # Check if it's a recent process (started within last 10 seconds)
                    current_create_time = current_process.create_time()
                    proc_create_time = proc_obj.create_time()
                    time_diff = abs(proc_create_time - current_create_time)
                    
                    if time_diff <= 10:  # 10 seconds
                        return proc.info['pid']
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except Exception as e:
            print(f"⚠️  Error getting server PID: {e}")
        
        return None
    
    def get_server_info(self) -> Dict[str, Dict]:
        """Get information about all managed servers."""
        return self._server_info.copy()
    
    async def cleanup(self):
        """Clean up all managed servers."""
        async with self._lock:
            for server_name, server in self._servers.items():
                try:
                    # Close the connection
                    if hasattr(server, 'close'):
                        await server.close()
                except Exception as e:
                    print(f"⚠️  Error closing {server_name}: {e}")
            
            self._servers.clear()
            self._server_info.clear()

# Global instance
_mcp_manager = MCPServerManager()

async def get_or_create_mcp_server(server_name: str, server_config: Dict, working_dir: str = None) -> MCPServerStdio:
    """Global function to get or create MCP server."""
    return await _mcp_manager.get_or_create_server(server_name, server_config, working_dir=working_dir)

async def cleanup_mcp_servers():
    """Global function to cleanup MCP servers."""
    await _mcp_manager.cleanup()

def get_mcp_server_info() -> Dict[str, Dict]:
    """Global function to get MCP server information."""
    return _mcp_manager.get_server_info()
