import os
import sys
import io
import logging
import atexit
import signal
import contextlib

_SHUTDOWN_DETECTED = False

def _set_shutdown_flag():
    """Set the global shutdown flag on exit."""
    global _SHUTDOWN_DETECTED
    _SHUTDOWN_DETECTED = True

def _aggressive_exit_handler(sig, frame):
    """Signal handler for SIGINT/SIGTERM. Sets the global shutdown flag."""
    global _SHUTDOWN_DETECTED
    print("\nSignal received, initiating shutdown...")
    _SHUTDOWN_DETECTED = True
    sys.exit(0)

class _SilentStderr(io.TextIOWrapper):
    """
    Suppresses stderr output once shutdown begins.
    Detects relevant error patterns to avoid noisy output during shutdown.
    """
    def __init__(self, target: io.TextIOBase):
        super().__init__(target.buffer, target.encoding, target.errors)
        self._target = target
        self._shutdown_patterns = {
            "asyncio.run() shutdown",
            "Attempted to exit cancel scope",
            "unhandled exception during",
            "an error occurred during closing",
            "BaseExceptionGroup",
            "RuntimeError: Attempted to exit cancel scope",
            "GeneratorExit",
            "CancelledError",
            "TaskGroup",
            "async_generator_athrow",
            "stdio_client",
            "anyio/_backends/_asyncio.py",
            "mcp/client/stdio/__init__.py",
            "Loop that handles pid",
            "is closed",
            "Exception Group Traceback",
            "During handling of the above exception",
            "Traceback (most recent call last)",
            "yield",
            "await",
            "async with",
            "self.close()",
            "call_soon(",
            "_check_closed()",
            "BaseSubprocessTransport.__del__",
            "Event loop unavailable",
            "Exception ignored",
            "RuntimeError: Event loop is closed",
            "Task group cancellation",
            "cancel scope in a different task",
            "/asyncio/",
            "Loop <_UnixSelectorEventLoop running=False closed=True debug=False>",
            "that handles pid",
        }

    def write(self, text):  # type: ignore[override]
        global _SHUTDOWN_DETECTED
        if _SHUTDOWN_DETECTED:
            return len(text)
        text_lower = text.lower()
        if any(pattern.lower() in text_lower for pattern in self._shutdown_patterns):
            _SHUTDOWN_DETECTED = True
            return len(text)
        return self._target.write(text)

    def flush(self):  # type: ignore[override]
        if not _SHUTDOWN_DETECTED:
            self._target.flush()

def configure_logging():
    """Configure logging and environment variables for the application."""
    os.environ["MCP_QUIET"] = "1"
    os.environ["NODE_ENV"] = "production"
    os.environ["PYTHONWARNINGS"] = "ignore"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OPENAI_LOG"] = "none"
    os.environ["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
    os.environ["PYTHONUNBUFFERED"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONHASHSEED"] = "0"
    os.environ["PYTHONPATH"] = os.getcwd()
    # Additional MCP quiet settings
    os.environ["MCP_LOG_LEVEL"] = "ERROR"
    os.environ["MCP_VERBOSE"] = "0"
    # Neo4j quiet settings
    os.environ["NEO4J_LOG_LEVEL"] = "ERROR"
    # Configure OpenAI Agents SDK tracing for full detail capture
    os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "0"  # Keep tracing enabled
    # Remove trace filtering to allow full granularity for MLflow autolog
    os.environ.pop("OPENAI_AGENTS_TRACE_FILTER", None)
    os.environ.pop("OPENAI_AGENTS_TRACE_LEVEL", None)
    os.environ["OPENAI_LOG_LEVEL"] = "WARNING"  # Reduce OpenAI SDK logging noise

    # Set root logger to ERROR level and configure basic logging
    logging.basicConfig(level=logging.ERROR, format='%(levelname)s:%(name)s:%(message)s')
    
    # Configure specific noisy loggers to ERROR level (expanded list)
    noisy_loggers = [
        # HTTP and network
        "httpx", "uvicorn", "urllib3", "requests",
        
        # OpenAI and AI libraries
        "openai", "openai._client", "_client",
        
        # MCP related
        "mcp", "mcp.client", "mcp.server", "mcp.utils", "mcp.rag",
        "mcp.client.stdio", "mcp.server.lowlevel", "mcp.server.lowlevel.server",
        "mcp_servers_and_tools/workspace_server",
        
        # Async and concurrency
        "asyncio", "anyio", "concurrent.futures",
        
        # ML and transformers
        "torch", "transformers", "tokenizers", "numpy", "pandas",
        "sentence_transformers", "sentence_transformers.cross_encoder", 
        "sentence_transformers.cross_encoder.CrossEncoder",
        
        # Neo4j and knowledge graph (more comprehensive)
        "neo4j", "neo4j.notifications", "neo4j.driver", "neo4j.work", "neo4j.pool",
        "neo4j.io", "neo4j.time", "neo4j.spatial", "neo4j.graph",
        "knowledge_graph_validator", "parse_repo_into_neo4j", "ai_hallucination_detector",
        "ai_script_analyzer", "hallucination_reporter",
        
        # Web scraping and automation
        "selenium", "crawl4ai", "Tavily", "server",
        
        # Database
        "supabase",
        
        # Other noisy loggers
        "CrossEncoder",
    ]
    
    # More aggressive silencing - set to CRITICAL level for extremely noisy loggers
    critical_silent_loggers = [
        "sentence_transformers.cross_encoder.CrossEncoder",
        "knowledge_graph_validator", 
        "parse_repo_into_neo4j",
        "neo4j.notifications",
        "mcp.server.lowlevel.server",
        "httpx",
        "ai_hallucination_detector",
    ]
    
    for logger_name in noisy_loggers:
        logger = logging.getLogger(logger_name)
        if logger_name in critical_silent_loggers:
            logger.setLevel(logging.CRITICAL)  # Even more silent
        else:
            logger.setLevel(logging.ERROR)
        logger.propagate = False
        # Remove all existing handlers to ensure our settings take effect
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
    
    # Override getLogger to automatically configure noisy loggers (enhanced)
    original_getLogger = logging.getLogger
    
    def quiet_getLogger(name=None):
        logger = original_getLogger(name)
        if name:
            name_lower = name.lower()
            # Enhanced pattern matching for automatic silencing
            silent_patterns = [
                "mcp", "sentence_transformers", "crossencoder", "tavily", "neo4j",
                "httpx", "uvicorn", "openai", "asyncio", "anyio", "selenium", "urllib3",
                "knowledge_graph", "parse_repo", "supabase", "transformers", "torch",
                "hallucination", "ai_script"
            ]
            
            if any(pattern in name_lower for pattern in silent_patterns):
                # Extra quiet for the most noisy ones
                if any(critical in name_lower for critical in ["sentence_transformers", "neo4j", "mcp.server", "knowledge_graph", "parse_repo", "hallucination"]):
                    logger.setLevel(logging.CRITICAL)
                else:
                    logger.setLevel(logging.ERROR)
                logger.propagate = False
                # Remove existing handlers
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)
        return logger
    
    logging.getLogger = quiet_getLogger
    
    # Additional step: Silence the root logger's handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setLevel(logging.ERROR)
    
    # Force Neo4j logging to be quiet
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="neo4j")
    warnings.filterwarnings("ignore", message=".*Neo4j.*")
    warnings.filterwarnings("ignore", message=".*neo4j.*")

def _get_noisy_logger_names():
    """
    Return logger names known to emit irrelevant noise during shutdown.
    """
    return (
        # MCP related
        "MCP", "mcp", "mcp.client", "mcp.server", "mcp.utils", "mcp.rag", 
        "mcp.server.lowlevel", "mcp.server.lowlevel.server",
        
        # Async and system
        "anyio", "memgpt", "asyncio", "concurrent.futures",
        
        # HTTP and network
        "httpx", "uvicorn", "urllib3", "requests",
        
        # ML and AI
        "CrossEncoder", "sentence_transformers", "sentence_transformers.cross_encoder",
        "sentence_transformers.cross_encoder.CrossEncoder", "transformers", "torch",
        "tokenizers", "numpy", "pandas",
        
        # Neo4j and knowledge graph (comprehensive)
        "neo4j", "neo4j.notifications", "neo4j.driver", "neo4j.work", "neo4j.pool",
        "neo4j.io", "neo4j.time", "neo4j.spatial", "neo4j.graph",
        "knowledge_graph_validator", "parse_repo_into_neo4j", "ai_hallucination_detector",
        "ai_script_analyzer", "hallucination_reporter",
        
        # Web and automation
        "Tavily", "selenium", "crawl4ai",
        
        # Database
        "supabase",
        
        # OpenAI
        "openai", "openai._client", "_client"
    )

@contextlib.contextmanager
def silence_external_output(enabled=True):
    """
    Temporarily redirect stdout/stderr and raise loggers to ERROR level.
    Used to suppress noisy output from external libraries.
    """
    if not enabled:
        yield
        return
    new_out, new_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(new_out), contextlib.redirect_stderr(new_err):
        saved = {}
        for name in _get_noisy_logger_names():
            lg = logging.getLogger(name)
            saved[name] = lg.level
            lg.setLevel(logging.ERROR)
        try:
            yield
        finally:
            for name, lvl in saved.items():
                logging.getLogger(name).setLevel(lvl)

def setup_quiet_mode():
    """
    Set up stderr filtering, logging, signal handlers, and environment variables
    to suppress noisy output and warnings during shutdown.
    Should be called as early as possible in the main script.
    """
    # Install stderr filter (only once)
    if not isinstance(sys.stderr, _SilentStderr):
        sys.stderr = _SilentStderr(sys.stderr)
    # Register shutdown handlers
    atexit.register(_set_shutdown_flag)
    signal.signal(signal.SIGINT, _aggressive_exit_handler)
    signal.signal(signal.SIGTERM, _aggressive_exit_handler)
    # Configure logging and environment
    configure_logging()
    
    # Proactively silence any existing loggers that match our patterns
    import logging
    
    # Get all existing loggers
    existing_loggers = [logging.getLogger(name) for name in logging.Logger.manager.loggerDict]
    
    for logger in existing_loggers:
        if logger.name:
            name_lower = logger.name.lower()
            silent_patterns = [
                "mcp", "sentence_transformers", "crossencoder", "tavily", "neo4j",
                "httpx", "uvicorn", "openai", "asyncio", "anyio", "selenium", "urllib3",
                "knowledge_graph", "parse_repo", "supabase", "transformers", "torch"
            ]
            
            if any(pattern in name_lower for pattern in silent_patterns):
                # Extra quiet for the most noisy ones
                if any(critical in name_lower for critical in ["sentence_transformers", "neo4j", "mcp.server", "knowledge_graph", "parse_repo"]):
                    logger.setLevel(logging.CRITICAL)
                else:
                    logger.setLevel(logging.ERROR)
                logger.propagate = False
                # Remove existing handlers
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)

def reapply_quiet_mode():
    """
    Reapply quiet mode to any newly created loggers.
    Call this periodically during long-running processes.
    """
    import logging
    
    # Get all existing loggers
    existing_loggers = [logging.getLogger(name) for name in logging.Logger.manager.loggerDict]
    
    for logger in existing_loggers:
        if logger.name:
            name_lower = logger.name.lower()
            silent_patterns = [
                "mcp", "sentence_transformers", "crossencoder", "tavily", "neo4j",
                "httpx", "uvicorn", "openai", "asyncio", "anyio", "selenium", "urllib3",
                "knowledge_graph", "parse_repo", "supabase", "transformers", "torch"
            ]
            
            if any(pattern in name_lower for pattern in silent_patterns):
                # Extra quiet for the most noisy ones
                if any(critical in name_lower for critical in ["sentence_transformers", "neo4j", "mcp.server", "knowledge_graph", "parse_repo"]):
                    logger.setLevel(logging.CRITICAL)
                else:
                    logger.setLevel(logging.ERROR)
                logger.propagate = False
                # Remove existing handlers
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)

def is_shutdown():
    """Return True if shutdown has been detected."""
    return _SHUTDOWN_DETECTED
