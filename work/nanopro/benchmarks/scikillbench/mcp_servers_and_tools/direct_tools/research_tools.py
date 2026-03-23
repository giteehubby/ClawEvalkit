"""
Direct Function Tools for Research Operations

This module provides direct implementations of research tools, bypassing MCP server overhead
"""

import asyncio
import atexit
import json
import os
import sys
import time
import traceback
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Suppress harmless "Event loop is closed" warnings from asyncio subprocess cleanup
# These occur when browser processes are garbage collected after the event loop closes
warnings.filterwarnings("ignore", message="Event loop is closed", category=RuntimeWarning)

# Patch asyncio to suppress "Event loop is closed" errors during subprocess cleanup
# This is a known Python issue where subprocess transports are GC'd after event loop closes
_original_del = None
try:
    import asyncio.base_subprocess
    _original_del = asyncio.base_subprocess.BaseSubprocessTransport.__del__

    def _patched_del(self):
        try:
            _original_del(self)
        except RuntimeError as e:
            if "Event loop is closed" not in str(e):
                raise
    asyncio.base_subprocess.BaseSubprocessTransport.__del__ = _patched_del
except Exception:
    pass  # If patching fails, continue without it

from agents import function_tool
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from dotenv import load_dotenv
from supabase import Client
import re
# Compute a human-readable site-packages hint for docstrings
try:
    import sysconfig, site as _site
    _purelib = sysconfig.get_paths().get("purelib") or ""
    _sitepkgs = []
    try:
        _sitepkgs = _site.getsitepackages() or []
    except Exception:
        _sitepkgs = []
    SITE_PACKAGES_HINT = _purelib or (_sitepkgs[0] if _sitepkgs else "<site-packages>")
except Exception:
    SITE_PACKAGES_HINT = "<site-packages>"

# Add paths for importing local modules
project_root = Path(__file__).resolve().parent.parent.parent
mcp_servers = project_root / 'mcp_servers_and_tools'
knowledge_graphs_path = mcp_servers / 'research_server' / 'knowledge_graphs'
probe_path = mcp_servers / 'research_server' / 'introspection_and_probe'
research_server_path = mcp_servers / 'research_server' / 'src'
sys.path.append(str(knowledge_graphs_path))
sys.path.append(str(probe_path))
sys.path.append(str(research_server_path))

# Load environment variables
# Priority: .env file > shell environment (.bashrc) > code defaults
project_root = Path(__file__).resolve().parent.parent.parent
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path, override=True)

# Import utilities from research server
import importlib.util
_research_utils_spec = importlib.util.spec_from_file_location("research_server_utils", research_server_path / "research_server_utils.py")
_research_utils = importlib.util.module_from_spec(_research_utils_spec)
_research_utils_spec.loader.exec_module(_research_utils)

get_supabase_client = _research_utils.get_supabase_client
extract_code_blocks = _research_utils.extract_code_blocks
generate_code_example_summary = _research_utils.generate_code_example_summary
check_extracted_code_exists = _research_utils.check_extracted_code_exists
save_extracted_code_to_supabase = _research_utils.save_extracted_code_to_supabase
get_extracted_code_from_supabase = _research_utils.get_extracted_code_from_supabase
search_code_blocks = _research_utils.search_code_blocks
detect_content_type_and_source = _research_utils.detect_content_type_and_source
extract_readthedocs_code_blocks = _research_utils.extract_readthedocs_code_blocks
extract_markdown_code_blocks = _research_utils.extract_markdown_code_blocks
extract_command_examples = _research_utils.extract_command_examples
extract_smart_context_before = _research_utils.extract_smart_context_before
extract_smart_context_after = _research_utils.extract_smart_context_after
extract_generic_html_code_blocks = _research_utils.extract_generic_html_code_blocks
extract_github_html_code_blocks = _research_utils.extract_github_html_code_blocks
extract_mkdocs_code_blocks = _research_utils.extract_mkdocs_code_blocks
extract_jupyter_notebook_cells = _research_utils.extract_jupyter_notebook_cells

# Import knowledge graph and introspection tools
from parse_repo_into_neo4j import DirectNeo4jExtractor
from quick_introspect_core import run_quick_introspect
from runtime_probe import (
    show_all_keys_or_attrs as rp_show_all,
    try_get_key as rp_try_get_key,
    try_get_attr as rp_try_get_attr
)

# Initialize shared resources
_crawler = None
_supabase_client = None
_repo_extractor = None

async def get_crawler():
    """Get or create the shared crawler instance with error handling and retry"""
    global _crawler
    if _crawler is None:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                browser_config = BrowserConfig(
                    headless=True,
                    verbose=False
                )
                _crawler = AsyncWebCrawler(config=browser_config)
                await _crawler.start()
                break  # Success, exit retry loop
            except Exception as e:
                _crawler = None  # Reset on failure
                if attempt == max_retries - 1:
                    # Final attempt failed
                    raise Exception(f"Failed to start web crawler after {max_retries} attempts. This may be due to browser resource conflicts. Error: {str(e)}")
                else:
                    # Wait before retry
                    import asyncio
                    await asyncio.sleep(1)
    return _crawler

async def reset_crawler():
    """Force reset the crawler instance (useful for troubleshooting)"""
    global _crawler
    if _crawler is not None:
        try:
            await _crawler.close()
        except:
            pass  # Ignore errors during cleanup
        _crawler = None

async def cleanup_crawler():
    """Public function to cleanup the crawler before process exit.
    This should be called to properly close the browser and prevent hanging."""
    await reset_crawler()

def _cleanup_crawler_sync():
    """Synchronous cleanup for atexit - closes browser before event loop shuts down"""
    global _crawler
    if _crawler is not None:
        try:
            # Try to get or create an event loop for cleanup
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(_crawler.close())
        except Exception:
            pass  # Ignore all errors during cleanup
        finally:
            _crawler = None

# Register cleanup handler to close browser before Python exits
atexit.register(_cleanup_crawler_sync)

def get_supabase():
    """Get or create the shared Supabase client"""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = get_supabase_client()
    return _supabase_client

async def get_repo_extractor():
    """Get or create the shared repository extractor instance"""
    global _repo_extractor
    if _repo_extractor is None:
        # Check if knowledge graph functionality is enabled
        knowledge_graph_enabled = os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true"
        if knowledge_graph_enabled:
            neo4j_uri = os.getenv("NEO4J_URI")
            neo4j_user = os.getenv("NEO4J_USER")
            neo4j_password = os.getenv("NEO4J_PASSWORD")
            if neo4j_uri and neo4j_user and neo4j_password:
                try:
                    _repo_extractor = DirectNeo4jExtractor(neo4j_uri, neo4j_user, neo4j_password)
                    await _repo_extractor.initialize()
                    # print("✓ Neo4j knowledge graph extractor initialized")
                except Exception as e:
                    print(f"✗ Failed to initialize Neo4j extractor: {e}")
                    _repo_extractor = None
            else:
                print("Neo4j credentials not configured - knowledge graph tools will be unavailable")
        else:
            print("Knowledge graph functionality disabled - set USE_KNOWLEDGE_GRAPH=true to enable")
    return _repo_extractor

# Import helper functions directly from research_mcp.py
from research_mcp import (
    crawl_batch,
    crawl_recursive_internal_links,
    crawl_markdown_file,
    _generate_code_summary,
    is_sitemap,
    is_txt,
    parse_sitemap,
    smart_chunk_markdown,
    github_blob_to_raw,
    validate_and_normalize_url,
    _extract_code_single_page,
    _extract_code_smart_crawl,
    _handle_repos_command,
    _handle_explore_command,
    _handle_classes_command,
    _handle_class_command,
    _handle_method_command,
    _handle_query_command
)

# ============================================================================
# MAIN TOOL FUNCTIONS
# ============================================================================

@function_tool
async def extract_code_from_url(
    url: str = None,
    urls: List[str] = None
) -> str:
    """
    Extract code examples and commands from one or more URLs for immediate use by agents.
    This tool uses a caching strategy: first checks if code has already been extracted from the URL(s),
    and if not, performs extraction and stores the results in Supabase for future use.
    
    Extraction strategy:
    1. Check cache first
    2. Try single page extraction with optimized strategy:
       - HTML extraction only for ReadTheDocs/Sphinx
       - Markdown extraction for other content types
       - Special handling for Jupyter notebooks (JSON extraction)
    3. If no code blocks found, fallback to smart crawl
    
    If a list of URLs is provided, all will be processed and results merged.
    Each code block in the result will include a 'source_url' key indicating its origin.
    
    Args:
        url: Single URL to extract code from 
        urls: List of URLs to extract code from
        
    Returns:
        JSON string with extracted code examples, commands, and content summary.
        Key fields to focus on:
        - 'code': The extracted code content
        - 'context_before': Text content before the code block
        - 'context_after': Text content after the code block
        - 'source_url': URL where the code was extracted from
        - 'summary': Code summary (often an empty string unless language model summary is enabled)
    """
    # Set timeout for the entire extraction process (100 seconds)
    EXTRACTION_TIMEOUT = 100
    
    try:
        start_time = time.time()
        
        # Wrap the entire function in a timeout
        async def extract_with_timeout():
            return await _extract_code_from_url_internal(url, urls)
        
        try:
            result = await asyncio.wait_for(extract_with_timeout(), timeout=EXTRACTION_TIMEOUT)
            elapsed_time = time.time() - start_time
            # print(f"✅ Extraction completed in {elapsed_time:.2f} seconds")
            return result
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            print(f"⏰ Extraction timed out after {elapsed_time:.2f} seconds")
            
            # Return a friendly error message instead of crashing
            timeout_message = {
                "success": False,
                "error": f"Extraction timed out after {EXTRACTION_TIMEOUT} seconds",
                "error_type": "timeout",
                "suggestion": "This webpage may not exist, or extraction is taking too long. Do NOT try to extract code from this URL again. Please try:",
                "alternatives": [
                    "Use a different related webpage for code extraction",
                    "Use tavily search to find information about this webpage if the URL exists"
                ],
                "url": url if url else (urls[0] if urls else "unknown"),
                "extracted_code": [],
                "code_blocks_found": 0
            }
            
            if urls:
                # For multiple URLs, return timeout info for all
                timeout_message["urls"] = urls
                timeout_message["per_url_results"] = [
                    {
                        "success": False,
                        "url": u,
                        "error": f"Extraction timed out after {EXTRACTION_TIMEOUT} seconds",
                        "error_type": "timeout",
                        "suggestion": "Try alternative methods or different URLs"
                    } for u in urls
                ]
                timeout_message["summary"] = {
                    "total_unique_urls": len(urls),
                    "successful_extractions": 0,
                    "timeout_urls": len(urls),
                    "total_code_blocks_found": 0
                }
            
            return json.dumps(timeout_message, indent=2)
            
    except Exception as e:
        # print(f"Error in extract_code_from_url: {traceback.format_exc()}")
        return json.dumps({
            "success": False,
            "error": str(e),
            "error_type": "exception"
        }, indent=2)

async def _extract_code_from_url_internal(url: str = None, urls: list = None) -> str:
    """
    Internal implementation of extract_code_from_url without timeout wrapper.
    This is the original function logic.
    """
    try:
        supabase_client = get_supabase()
        crawler = await get_crawler()
        
        async def process_one_url(url):
            """Process a single URL with caching and fallback strategy"""
            url, is_valid = validate_and_normalize_url(url)
            if not is_valid:
                return {
                    "success": False,
                    "url": url,
                    "error": "Invalid URL provided"
                }
            # 1. Check cache first
            if await check_extracted_code_exists(supabase_client, url):
                # print(f"📋 Found cached extracted code for {url}")
                cached_code_blocks = await get_extracted_code_from_supabase(supabase_client, url)
                if cached_code_blocks:
                    for block in cached_code_blocks:
                        block["source_url"] = url
                    return {
                        "success": True,
                        "url": url,
                        "code_blocks_found": len(cached_code_blocks),
                        "extracted_code": cached_code_blocks,
                        "extraction_method": "cached",
                        "cached": True
                    }
            # 2. Try single page extraction
            # print(f"🔄 Extracting code from {url}...")
            single_page_result = await _extract_code_single_page(crawler, url)
            try:
                result_data = json.loads(single_page_result)
                # If single page crawl succeeded
                if result_data.get("success", False):
                    extracted_code = result_data.get("extracted_code", [])
                    # Add source_url to each code block
                    for block in extracted_code:
                        block["source_url"] = url
                    # Check if we found any code blocks
                    if result_data.get("code_blocks_found", 0) > 0:
                        # Found code blocks - save and return
                        await save_extracted_code_to_supabase(
                            supabase_client, 
                            url, 
                            extracted_code, 
                            result_data.get("code_blocks_found", 0),
                            "single_page"
                        )
                        result_data["cached"] = False
                        return result_data
                    else:
                        # No code blocks found - try smart crawl as fallback
                        # print(f"📍 No code blocks found with single page, trying smart crawl for {url}...")
                        pass
                else:
                    # Single page crawl failed - try smart crawl
                    # print(f"❌ Single page crawl failed for {url}, trying smart crawl...")
                    pass
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error parsing single page result: {e}")
            # 3. Fallback to smart crawl (either no code found or crawl failed)
            smart_result = await _extract_code_smart_crawl(crawler, url)
            try:
                smart_data = json.loads(smart_result)
                extracted_code = smart_data.get("extracted_code", [])
                # Add source_url to each code block
                for block in extracted_code:
                    block["source_url"] = url
                # Save to cache
                await save_extracted_code_to_supabase(
                    supabase_client, 
                    url, 
                    extracted_code, 
                    smart_data.get("code_blocks_found", 0),
                    "smart_crawl"
                )
                smart_data["cached"] = False
                return smart_data
            except Exception as e:
                return {
                    "success": False, 
                    "url": url, 
                    "error": f"Both single page and smart crawl failed: {str(e)}"
                }
        # Handle multiple URLs (only if urls is provided and not empty)
        if urls is not None and len(urls) > 0:
            # Special case: if only one URL provided, treat it like single URL for consistent output
            if len(urls) == 1:
                result = await process_one_url(urls[0])
                return json.dumps(result, indent=2)
            
            # Remove duplicates while preserving order
            unique_urls = []
            seen_urls = set()
            duplicate_urls = []
            for u in urls:
                if u in seen_urls:
                    duplicate_urls.append(u)
                else:
                    unique_urls.append(u)
                    seen_urls.add(u)
            
            # After deduplication, check if we ended up with only one URL
            if len(unique_urls) == 1:
                result = await process_one_url(unique_urls[0])
                return json.dumps(result, indent=2)
            
            # Process multiple unique URLs
            all_results = []
            all_code_blocks = []
            cached_count = 0
            extracted_count = 0
            for u in unique_urls:
                result = await process_one_url(u)
                all_results.append(result)
                if result.get("success") and result.get("extracted_code"):
                    all_code_blocks.extend(result["extracted_code"])
                    if result.get("cached", False):
                        cached_count += 1
                    else:
                        extracted_count += 1
            # Create summary
            summary_info = {
                "cached_urls": cached_count,
                "newly_extracted_urls": extracted_count,
                "total_unique_urls": len(unique_urls),
                "total_original_urls": len(urls),
                "duplicate_urls_skipped": len(duplicate_urls)
            }
            if duplicate_urls:
                summary_info["duplicate_urls"] = duplicate_urls
            return json.dumps({
                "success": True,
                "urls": urls,
                "unique_urls": unique_urls,
                "total_code_blocks_found": len(all_code_blocks),
                "all_extracted_code": all_code_blocks,
                "per_url_results": all_results,
                "summary": summary_info
            }, indent=2)
        # Handle single URL
        elif url is not None:
            result = await process_one_url(url)
            return json.dumps(result, indent=2)
        # No URL provided
        else:
            return json.dumps({
                "success": False,
                "error": "No url or urls provided"
            }, indent=2)
    except Exception as e:
        # print(f"Error in _extract_code_from_url_internal: {traceback.format_exc()}")
        return json.dumps({
            "success": False,
            "error": str(e)
        }, indent=2)


@function_tool
async def retrieve_extracted_code(
    query: str,
    match_count: int = 5
) -> str:
    """
    Retrieve extracted code blocks relevant to the query.
    This tool searches the extracted_code table for code blocks relevant to the query and returns
    the matching examples with their summaries and context.
    You can call this tool multiple times with different queries to get more relevant results.
    Args:
        query: The search query
        match_count: Maximum number of results to return (default: 5)
    Returns:
        JSON string with the search results
    """
    try:
        supabase_client = get_supabase()
        # Search for code blocks
        results = await search_code_blocks(
            client=supabase_client,
            query=query,
            match_count=match_count
        )
        # Format the results
        formatted_results = []
        for result in results:
            formatted_result = {
                "source_url": result.get("source_url"),
                "code": result.get("code"),
                "summary": result.get("summary"),
                "context_before": result.get("context_before"),
                "context_after": result.get("context_after"),
                "type": result.get("type"),
                "language": result.get("language"),
                "index": result.get("index"),
                "similarity_score": result.get("similarity_score")
            }
            formatted_results.append(formatted_result)
        return json.dumps({
            "success": True,
            "query": query,
            "search_mode": "vector",
            "results": formatted_results,
            "count": len(formatted_results)
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "query": query,
            "error": str(e)
        }, indent=2)

@function_tool
async def quick_introspect(
    code_content: str = None,
    class_hint: str = None,
    method_hint: str = None,
    package_path: str = None,
    function_hint: str = None,
    module_hint: str = None,
    repo_hint: str = None,
    max_suggestions: int = 10,
    no_imports: bool = False,
) -> str:
    f"""
    Fast, static-first introspection for fixing import/class/method/function related errors.
    Uses Jedi for static discovery first (no side effects), then runtime import/inspect fallback.
    Returns a human/agent-readable report string with suggested import lines (if no-imports is not set), class methods (if method_hint/class_hint and repo_hint or package_path are provided), and functions (if function_hint/module_hint and repo_hint or package_path are provided).
    Parameter relationships:
    - repo_hint vs package_path: mutually exclusive; pass at most one.
    - module_hint must be used together with function_hint.
    - If class_hint or method_hint is provided, one of repo_hint or package_path is required.
    - If function_hint is provided, one of repo_hint or package_path is required.
    Notes:
    - You can provide fuzzy hints for class_hint, method_hint, function_hint, module_hint (but repo_hint need to be exact) if you cannot provide exact hints.
    - It is recommended to use code_content to provide the code content for import diagnostics.
    - repo_hint is the top-level import module name (may differ from pip distribution name). If repo_hint cannot be imported, provide package_path instead.
    - PATH HANDLING for package_path:
      * Absolute path: used as-is.
      * Relative path: resolved against the active environment's site-packages root {SITE_PACKAGES_HINT}.
        For example, passing "pydantic" will be tried as {SITE_PACKAGES_HINT}/pydantic.
      * If unsure about the absolute path, use your check_package_version tool to obtain it if you have this tool.
      * If repo_hint fails to import, try providing an absolute or relative package_path (relative path starts from {SITE_PACKAGES_HINT}).
    - Function vs Method:
      * Use method_hint when the target is a class member (instance/class method). Do not use function_hint for class/instance methods. **Most of the time, you should use method_hint**
      * Use function_hint only for top-level (module-level) functions; optionally add module_hint to narrow
      * Heuristics: analyze the call-site pattern — calls like SomeClass.method(...)/obj.method(...) → method_hint; calls like package.module.function(...), module.function(...), function(...) → function_hint
    - method_hint can be provided without class_hint to trigger a repo-wide search (noisy but useful, but oftenit is more recommended to add fuzzy or exact class_hint to narrow down the search).
    - To silence import diagnostics if you think it is too noisy for your use case, set no_imports=true and reuse this tool to introspect the code again.
    - max_suggestions is the maximum number of suggestions to return. If not provided, it will return all suggestions. You can set it to a smaller number to reduce the noise if needed.
    - Set env QI_DEBUG_ENGINE=1 to see whether Jedi or runtime fallback is used. But normally you don't need to set this.
    """
    try:
        # Resolve relative package_path against active environment's site-packages
        if package_path:
            try:
                import sysconfig, site
                candidate_paths = []
                purelib = sysconfig.get_paths().get("purelib")
                if purelib:
                    candidate_paths.append(purelib)
                # site.getsitepackages may return multiple entries (venv + global)
                try:
                    for p in site.getsitepackages():
                        if p not in candidate_paths:
                            candidate_paths.append(p)
                except Exception:
                    pass
                if not os.path.isabs(package_path):
                    for root in candidate_paths:
                        joined = os.path.join(root, package_path)
                        if os.path.exists(joined):
                            package_path = joined
                            break
            except Exception:
                pass
        report = run_quick_introspect(
            code_content=code_content,
            class_hint=class_hint,
            method_hint=method_hint,
            package_path=package_path,
            function_hint=function_hint,
            module_hint=module_hint,
            repo_hint=repo_hint,
            max_suggestions=max_suggestions,
            no_imports=no_imports,
        )
        import json as _json
        return _json.dumps({
            "success": True,
            "report": report,
        }, indent=2)
    except Exception as e:
        import json as _json
        # Return the core error message in 'report' to keep a single consumption path
        message = str(e)
        return _json.dumps({
            "success": False,
            "report": message,
        }, indent=2)

@function_tool
async def runtime_probe_snippet(
    snippet: str
) -> str:
    """
    Return a ready-to-paste Python probe snippet for targeted debugging of runtime errors.
    snippet: one of "try_get_key", "try_get_attr".
    - try_get_key: Use at a KeyError site. Replace mapping['k'] with try_get_key(mapping, 'k').
      If the key exists, it prints an OK message (either the earlier error was at a different site and you
      should probe the right line and re-run, or you are now probing a different key than the one that caused the earlier KeyError and have successfully
      debugged it). If missing, it prints available keys and error context to guide a fix.
    - try_get_attr: Use at an AttributeError site. Replace obj.attr with try_get_attr(obj, 'attr').
      If the attribute exists, it prints an OK message (either the earlier error was at a different site and
      you should probe the right line and re-run, or you are now probing a different attribute than the one that caused the earlier AttributeError and have
      successfully debugged it). If missing, it prints public attributes, similarity suggestions and error context to guide a fix.
    The returned report contains a short usage header followed by the snippet code. You MUST Paste the snippet into
    your current script right after your imports and follow the usage note to replace the failing access.
    """
    import json as _json
    SNIPPETS: dict[str, str] = {
        "try_get_key": (
            "import sys, os\n"
            "from pathlib import Path\n"
            "# Resolve project root heuristically and add probe folder to sys.path\n"
            "_here = Path(__file__).resolve() if '__file__' in globals() else Path.cwd()\n"
            "_root = _here\n"
            "for _ in range(5):\n"
            "    if (_root / 'mcp_servers_and_tools' / 'research_server' / 'introspection_and_probe').exists():\n"
            "        sys.path.insert(0, str(_root / 'mcp_servers_and_tools' / 'research_server' / 'introspection_and_probe'))\n"
            "        break\n"
            "    _root = _root.parent\n"
            "from runtime_probe import try_get_key\n\n"
            "# Usage at the KeyError site: replace mapping['k'] with try_get_key(mapping, 'k')\n"
        ),
        "try_get_attr": (
            "import sys, os\n"
            "from pathlib import Path\n"
            "_here = Path(__file__).resolve() if '__file__' in globals() else Path.cwd()\n"
            "_root = _here\n"
            "for _ in range(5):\n"
            "    if (_root / 'mcp_servers_and_tools' / 'research_server' / 'introspection_and_probe').exists():\n"
            "        sys.path.insert(0, str(_root / 'mcp_servers_and_tools' / 'research_server' / 'introspection_and_probe'))\n"
            "        break\n"
            "    _root = _root.parent\n"
            "from runtime_probe import try_get_attr\n\n"
            "# Usage at the AttributeError site: replace obj.attr with try_get_attr(obj, 'attr')\n"
        ),
    }
    key = (snippet or "").strip()
    if key not in SNIPPETS:
        return _json.dumps({
            "success": False,
            "report": "Invalid snippet. Use one of: try_get_key, try_get_attr",
        }, indent=2)
    headers = {
        "try_get_key": (
            "Usage at the KeyError site: replace mapping['k'] with try_get_key(mapping, 'k').\n"
            "**You MUST Paste this snippet right after your imports.**\n"
        ),
        "try_get_attr": (
            "Usage at the AttributeError site: replace obj.attr with try_get_attr(obj, 'attr').\n"
            "**You MUST Paste this snippet right after your imports.**\n"
        ),
    }
    header = headers[key]
    return _json.dumps({
        "success": True,
        "report": header + "\n" + SNIPPETS[key],
    }, indent=2)

@function_tool
async def parse_local_package(
    package_name: str = None,
    package_path: str = None
) -> str:
    f"""
    Parse a locally installed Python package into the Neo4j knowledge graph.
    This tool analyzes a locally installed Python package, extracts its code structure,
    and stores it in Neo4j for use in knowledge graph exploration. The tool supports
    flexible package location strategies:
    **Package Location Strategies:**
    1. **Auto-detection**: Provide only `package_name` - tool will use `uv pip show` to locate the package
    2. **Direct path**: Provide only `package_path` - tool will parse the specified directory directly
    3. **Hybrid approach**: Provide both - tool will try `package_path` first, fallback to `package_name` auto-detection
    **Error Handling:**
    - If package_name cannot be found or is not installed, provides detailed error with suggestions
    - If package_path doesn't exist but package_name is provided, tries auto-detection as fallback
    - Returns clear error messages with actionable suggestions
    **Features:**
    - Locates the package in the Python environment or uses provided path
    - Analyzes Python files to extract code structure  
    - Stores classes, methods, functions, and imports in Neo4j
    - Provides detailed statistics about the parsing results
    - Ensures version compatibility with the local environment
    - Checks if the specific version already exists before parsing
    PATH HANDLING for package_path:
    - Absolute path: used as-is.
    - Relative path: resolved against the active environment's site-packages root {SITE_PACKAGES_HINT}.
      For example, passing "pydantic" will be tried as {SITE_PACKAGES_HINT}/pydantic.
    - If unsure about the absolute path, use your check_package_version tool (if you have this tool) to obtain it.

    Args:
        package_name: Name of the package to parse (optional if package_path is provided)
        package_path: Path to the package directory (optional if package_name is provided)
    Returns:
        JSON string with parsing results, statistics, and package information
    """
    try:
        # Check if knowledge graph functionality is enabled
        knowledge_graph_enabled = os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true"
        if not knowledge_graph_enabled:
            return json.dumps({
                "success": False,
                "error": "Knowledge graph functionality is disabled. Set USE_KNOWLEDGE_GRAPH=true in environment."
            }, indent=2)
        # Get the repository extractor
        repo_extractor = await get_repo_extractor()
        if not repo_extractor:
            return json.dumps({
                "success": False,
                "error": "Repository extractor not available. Check Neo4j configuration in environment variables."
            }, indent=2)
        # Validate input parameters
        if not package_name and not package_path:
            return json.dumps({
                "success": False,
                "error": "Either package_name or package_path must be provided"
            }, indent=2)
        valid_package_path = None
        detected_version = None
        final_package_name = package_name
        def try_auto_detect_package(pkg_name):
            """Helper function to auto-detect package path from package name"""
            try:
                import subprocess
                result = subprocess.run(
                    ["uv", "pip", "show", pkg_name], 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
                # Parse pip show output to get location and version
                site_packages_path = None
                version = None
                for line in result.stdout.split('\n'):
                    if line.startswith('Location:'):
                        site_packages_path = line.split(':', 1)[1].strip()
                    elif line.startswith('Version:'):
                        version = line.split(':', 1)[1].strip()
                # Construct the actual package path by appending package name to site-packages location
                if site_packages_path:
                    auto_detected_path = os.path.join(site_packages_path, pkg_name)
                    if os.path.exists(auto_detected_path):
                        return auto_detected_path, version
            except subprocess.CalledProcessError:
                pass
            return None, None
        # Helper to resolve relative package_path against site-packages
        def _resolve_relative_package_path(path: str) -> Optional[str]:
            try:
                import sysconfig, site
                bases: list[str] = []
                purelib = sysconfig.get_paths().get("purelib")
                if purelib:
                    bases.append(purelib)
                try:
                    for p in site.getsitepackages():
                        if p not in bases:
                            bases.append(p)
                except Exception:
                    pass
                if not os.path.isabs(path):
                    for root in bases:
                        candidate = os.path.join(root, path)
                        if os.path.exists(candidate):
                            return candidate
            except Exception:
                pass
            return None

        # Case 1: Only package_path provided
        if package_path and not package_name:
            resolved_package_path = package_path
            if not os.path.isabs(resolved_package_path):
                maybe = _resolve_relative_package_path(resolved_package_path)
                if maybe:
                    resolved_package_path = maybe
            if os.path.exists(resolved_package_path):
                valid_package_path = resolved_package_path
                # Try to infer package name from path for better error messages
                final_package_name = os.path.basename(valid_package_path.rstrip('/'))
            else:
                return json.dumps({
                    "success": False,
                    "package_path": package_path,
                    "error": f"Package path does not exist: {package_path}. Please confirm the package_path is correct or use package_name instead and retry this tool.",
                    "suggestions": [
                        "1. Verify the package_path is correct and accessible",
                        "2. Use package_name instead to auto-detect the location",
                        "3. Check if the directory exists and contains Python files"
                    ]
                }, indent=2)
        # Case 2: Only package_name provided  
        elif package_name and not package_path:
            valid_package_path, detected_version = try_auto_detect_package(package_name)
            if not valid_package_path:
                return json.dumps({
                    "success": False,
                    "package_name": package_name,
                    "error": (
                        f"Package '{package_name}' may be incorrect or not installed. "
                        f"Please verify the package name is correct, ensure it's installed, "
                        f"or provide package_path instead (absolute path, or relative path starting from {SITE_PACKAGES_HINT}) and retry this tool. "
                        f"If you have the check_package_version tool, you can use it to obtain the absolute package_path."
                    ),
                    "suggestions": [
                        f"1. Verify package name is correct: {package_name}",
                        f"2. Install the package: uv pip install {package_name}",
                        f"3. Provide package_path manually (absolute path or relative path from {SITE_PACKAGES_HINT})",
                        f"4. If you want to use absolute path, use check_package_version tool (if you have this tool) to get the absolute package_path"
                    ]
                }, indent=2)
        # Case 3: Both package_name and package_path provided
        else:  # both package_name and package_path are provided
            # Try package_path first
            resolved_package_path = package_path
            if not os.path.isabs(resolved_package_path):
                maybe = _resolve_relative_package_path(resolved_package_path)
                if maybe:
                    resolved_package_path = maybe
            if os.path.exists(resolved_package_path):
                valid_package_path = resolved_package_path
                # Infer the actual package name from the path (more reliable than user input)
                inferred_package_name = os.path.basename(valid_package_path.rstrip('/'))
                final_package_name = inferred_package_name
                # Try to get version info using the inferred package name
                _, detected_version = try_auto_detect_package(inferred_package_name)
                # If that fails, try with the provided package_name as fallback
                if not detected_version:
                    _, detected_version = try_auto_detect_package(package_name)
            else:
                # Fallback to package_name auto-detection
                valid_package_path, detected_version = try_auto_detect_package(package_name)
                if not valid_package_path:
                    return json.dumps({
                        "success": False,
                        "package_name": package_name,
                        "package_path": package_path,
                        "error": (
                            f"Both provided package_path '{package_path}' and package_name '{package_name}' "
                            f"are incorrect. Please check both parameters and provide correct information to retry."
                        ),
                        "suggestions": [
                            "1. Verify the package_path exists and is accessible",
                            "2. Verify the package_name is correct and installed",
                            "3. You can provide either package_name or package_path (or both)"
                        ]
                    }, indent=2)
        # Try to get version info if we still don't have it and we have a valid path
        if not detected_version and valid_package_path and final_package_name:
            _, detected_version = try_auto_detect_package(final_package_name)
        # Parse the local package using the valid path and detected version
        # print(f"Starting local package analysis for: {final_package_name}")
        # print(f"Using package path: {valid_package_path}")
        # if detected_version:
        #     print(f"Version: {detected_version}")
        # else:
        #     print("Version: Not detected")
        result = await repo_extractor.analyze_local_package(final_package_name, valid_package_path, detected_version)
        if result.get("skipped", False):
            return json.dumps({
                "success": True,
                "package_name": final_package_name,
                "package_path": valid_package_path,
                "version": detected_version,
                "message": result["message"],
                "skipped": True
            }, indent=2)
        # print(f"Local package analysis completed for: {final_package_name}")
        # Use the result from analyze_local_package
        if result.get("success", False):
            stats = {
                "package": final_package_name,
                "files_processed": result.get("files_processed", 0),
                "classes_created": result.get("classes_created", 0),
                "methods_created": result.get("methods_created", 0), 
                "functions_created": result.get("functions_created", 0)
            }
            return json.dumps({
                "success": True,
                "package_name": final_package_name,
                "package_path": valid_package_path,
                "version": detected_version,
                "message": f"Successfully parsed local package '{final_package_name}' into knowledge graph",
                "statistics": stats,
                "ready_for_validation": True,
                "next_steps": [
                    "Package is now available for knowledge graph exploration",
                    f"Use query_knowledge_graph to explore the knowledge graph for {final_package_name}",
                    "The knowledge graph contains classes, methods, and functions from this package"
                ]
            }, indent=2)
        else:
            return json.dumps({
                "success": False,
                "package_name": final_package_name,
                "error": "Failed to parse local package"
            }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "package_name": final_package_name if 'final_package_name' in locals() else package_name,
            "error": f"Local package parsing failed: {str(e)}"
        }, indent=2)

@function_tool
async def query_knowledge_graph(
    command: str
) -> str:
    """
    Query and explore the Neo4j knowledge graph containing repository data.
    This tool provides comprehensive access to the knowledge graph for exploring repositories,
    classes, methods, functions, and their relationships. Perfect for understanding what data
    is available for knowledge graph exploration and debugging validation results.
    **IMPORTANT: Always start with the `repos` command first!**
    Before using any other commands, run `repos` to see what repositories are available
    in your knowledge graph. This will help you understand what data you can explore.
    ## Available Commands:
    **Repository Commands:**
    - `repos` - **START HERE!** List all repositories in the knowledge graph
    - `explore <repo_name>` - Get detailed overview of a specific repository
    **Class Commands:**  
    - `classes` - List all classes across all repositories (limited to 20)
    - `classes <repo_name>` - List classes in a specific repository
    - `class <class_name>` - Get detailed information about a specific class including methods and attributes
    **Method Commands:**
    - `method <method_name>` - Search for methods by name across all classes
    - `method <method_name> <class_name>` - Search for a method within a specific class
    **Custom Query:**
    - `query <cypher_query>` - Execute a custom Cypher query (results limited to 20 records)
    ## Knowledge Graph Schema:
    **Node Types:**
    - Repository: `(r:Repository {name: string})`
    - File: `(f:File {path: string, module_name: string})`
    - Class: `(c:Class {name: string, full_name: string})`
    - Method: `(m:Method {name: string, params_list: [string], params_detailed: [string], return_type: string, args: [string]})`
    - Function: `(func:Function {name: string, params_list: [string], params_detailed: [string], return_type: string, args: [string]})`
    - Attribute: `(a:Attribute {name: string, type: string})`
    **Relationships:**
    - `(r:Repository)-[:CONTAINS]->(f:File)`
    - `(f:File)-[:DEFINES]->(c:Class)`
    - `(c:Class)-[:HAS_METHOD]->(m:Method)`
    - `(c:Class)-[:HAS_ATTRIBUTE]->(a:Attribute)`
    - `(f:File)-[:DEFINES]->(func:Function)`
    ## Example Workflow:
    ```
    1. repos                                    # See what repositories are available
    2. explore pydantic-ai                      # Explore a specific repository
    3. classes pydantic-ai                      # List classes in that repository
    4. class Agent                              # Explore the Agent class
    5. method run_stream                        # Search for run_stream method
    6. method __init__ Agent                    # Find Agent constructor
    7. query "MATCH (c:Class)-[:HAS_METHOD]->(m:Method) WHERE m.name = 'run' RETURN c.name, m.name LIMIT 5"
    ```
    Args:
        command: Command string to execute (see available commands above)
    Returns:
        JSON string with query results, statistics, and metadata
    """
    try:
        # Check if knowledge graph functionality is enabled
        knowledge_graph_enabled = os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true"
        if not knowledge_graph_enabled:
            return json.dumps({
                "success": False,
                "error": "Knowledge graph functionality is disabled. Set USE_KNOWLEDGE_GRAPH=true in environment."
            }, indent=2)
            
        # Get the repository extractor
        repo_extractor = await get_repo_extractor()
        if not repo_extractor or not repo_extractor.driver:
            return json.dumps({
                "success": False,
                "error": "Neo4j connection not available. Check Neo4j configuration in environment variables."
            }, indent=2)
        
        # Parse command
        command = command.strip()
        if not command:
            return json.dumps({
                "success": False,
                "command": "",
                "error": "Command cannot be empty. Available commands: repos, explore <repo>, classes [repo], class <name>, method <name> [class], query <cypher>"
            }, indent=2)
            
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        async with repo_extractor.driver.session() as session:
            # Route to appropriate handler
            if cmd == "repos":
                return await _handle_repos_command(session, command)
            elif cmd == "explore":
                if not args:
                    return json.dumps({
                        "success": False,
                        "command": command,
                        "error": "Repository name required. Usage: explore <repo_name>"
                    }, indent=2)
                return await _handle_explore_command(session, command, args[0])
            elif cmd == "classes":
                repo_name = args[0] if args else None
                return await _handle_classes_command(session, command, repo_name)
            elif cmd == "class":
                if not args:
                    return json.dumps({
                        "success": False,
                        "command": command,
                        "error": "Class name required. Usage: class <class_name>"
                    }, indent=2)
                return await _handle_class_command(session, command, args[0])
            elif cmd == "method":
                if not args:
                    return json.dumps({
                        "success": False,
                        "command": command,
                        "error": "Method name required. Usage: method <method_name> [class_name]"
                    }, indent=2)
                method_name = args[0]
                class_name = args[1] if len(args) > 1 else None
                return await _handle_method_command(session, command, method_name, class_name)
            elif cmd == "query":
                if not args:
                    return json.dumps({
                        "success": False,
                        "command": command,
                        "error": "Cypher query required. Usage: query <cypher_query>"
                    }, indent=2)
                cypher_query = " ".join(args)
                return await _handle_query_command(session, command, cypher_query)
            else:
                return json.dumps({
                    "success": False,
                    "command": command,
                    "error": f"Unknown command '{cmd}'. Available commands: repos, explore <repo>, classes [repo], class <name>, method <name> [class], query <cypher>"
                }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "command": command,
            "error": f"Query execution failed: {str(e)}"
        }, indent=2)
