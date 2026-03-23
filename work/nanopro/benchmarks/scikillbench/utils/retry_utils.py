import asyncio
from typing import Any, Callable, TypeVar

T = TypeVar('T')

async def retry_with_backoff(
    func: Callable[..., Any],
    max_retries: int = 3,
    initial_delay: float = 2.0,
    max_delay: float = 32.0,
    backoff_factor: float = 2.0,
    *args: Any,
    **kwargs: Any
) -> Any:
    """
    Retry a function with exponential backoff.
    """
    last_exception = None
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                print(f"❌ Attempt {attempt + 1} failed: {str(e)}")
                print(f"🔄 Retrying in {delay} seconds... (attempt {attempt + 2}/{max_retries})")
                await asyncio.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)
            else:
                print(f"❌ Final attempt failed: {str(e)}")
                print(f"🚫 All {max_retries} attempts exhausted")
                raise last_exception

async def call_tool_with_retry(
    tool: Any, 
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 2.0,
    max_delay: float = 32.0,
    backoff_factor: float = 2.0,
    **kwargs: Any
) -> Any:
    """
    Call a tool with retry mechanism, supporting different tool interfaces.
    """
    # Remove retry-related parameters from kwargs to avoid duplicate passing
    tool_kwargs = {k: v for k, v in kwargs.items() 
                   if k not in ['max_retries', 'initial_delay', 'max_delay', 'backoff_factor']}
    
    # If tool is a function or class method, wrap it directly
    if callable(tool):
        # For instance methods, we need to bind the first argument (self)
        if hasattr(tool, '__self__'):
            async def wrapped_func(*func_args, **func_kwargs):
                return await tool(*func_args, **func_kwargs)
            return await retry_with_backoff(
                wrapped_func, 
                max_retries,
                initial_delay,
                max_delay,
                backoff_factor,
                *args, 
                **tool_kwargs
            )
        else:
            # For regular functions, we can call them directly
            return await retry_with_backoff(
                tool,
                max_retries,
                initial_delay,
                max_delay,
                backoff_factor,
                *args, 
                **tool_kwargs
            )
    
    # Otherwise, check for tool interfaces
    if hasattr(tool, '__call__') and callable(getattr(tool, '__call__')):
        return await retry_with_backoff(
            tool,
            max_retries,
            initial_delay,
            max_delay,
            backoff_factor,
            *args, 
            **tool_kwargs
        )
    elif hasattr(tool, 'call') and callable(getattr(tool, 'call')):
        return await retry_with_backoff(
            tool.call,
            max_retries,
            initial_delay,
            max_delay,
            backoff_factor,
            *args, 
            **tool_kwargs
        )
    elif hasattr(tool, 'execute') and callable(getattr(tool, 'execute')):
        return await retry_with_backoff(
            tool.execute,
            max_retries,
            initial_delay,
            max_delay,
            backoff_factor,
            *args, 
            **tool_kwargs
        )
    else:
        raise Exception(f"Tool {tool} has no callable interface")

async def retry_mcp_server_connect(server, max_retries: int = 3) -> None:
    """
    Retry MCP server connection with exponential backoff.
    Only shows output when there are errors.
    """
    last_exception = None
    delay = 2.0
    
    for attempt in range(max_retries):
        try:
            # Call the connect method directly - silent on success
            return await server.connect()
        except Exception as e:
            last_exception = e
            error_type = type(e).__name__
            
            if attempt < max_retries - 1:
                print(f"❌ MCP server '{server.name}' connection failed: {error_type} - {str(e)}")
                print(f"🔄 Retrying connection to '{server.name}' in {delay} seconds... (attempt {attempt + 2}/{max_retries})")
                await asyncio.sleep(delay)
                delay = min(delay * 2.0, 32.0)  # Exponential backoff
            else:
                print(f"❌ MCP server '{server.name}' final connection attempt failed: {error_type} - {str(e)}")
                print(f"🚫 All {max_retries} connection attempts to '{server.name}' failed")
                raise last_exception