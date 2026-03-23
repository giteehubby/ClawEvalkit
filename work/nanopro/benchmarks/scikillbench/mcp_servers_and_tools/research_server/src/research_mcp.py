"""
Research Server
A specialized MCP server designed for comprehensive code research and analysis workflows.
Built to empower AI agents and coding assistants with powerful research capabilities.
Core Capabilities:
- Smart code extraction from web sources with caching
- Comprehensive code search and discovery
- Deep package and module introspection
- Runtime code analysis and exploration
- Local repository analysis and parsing
- Knowledge graph-powered code understanding
This server provides a complete research toolkit for understanding codebases,
discovering implementation patterns, and accelerating development workflows.
"""
from mcp.server.fastmcp import FastMCP, Context
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, urldefrag
from xml.etree import ElementTree
from dotenv import load_dotenv
from supabase import Client
from pathlib import Path
import requests
import asyncio
import json
import os
import sysconfig as _sc_doc
import site as _site_doc
import re
import sys
import time
import traceback
import logging
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, MemoryAdaptiveDispatcher

# Configure logging to stderr (MCP uses stdout for JSON-RPC)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("research_mcp")

# Compute a site-packages hint for docstrings
try:
    _purelib_doc = _sc_doc.get_paths().get("purelib") or ""
    _sitepkgs_doc = []
    try:
        _sitepkgs_doc = _site_doc.getsitepackages() or []
    except Exception:
        _sitepkgs_doc = []
    SITE_PACKAGES_HINT = _purelib_doc or (_sitepkgs_doc[0] if _sitepkgs_doc else "<site-packages>")
except Exception:
    SITE_PACKAGES_HINT = "<site-packages>"

# Add knowledge_graphs and introspection_and_probe folders to path for importing local modules
project_base = Path(__file__).resolve().parent.parent
knowledge_graphs_path = project_base / 'knowledge_graphs'
probe_path = project_base / 'introspection_and_probe'
sys.path.append(str(knowledge_graphs_path))
sys.path.append(str(probe_path))

from research_server_utils import (
    get_supabase_client,
    extract_code_blocks,
    generate_code_example_summary,
    check_extracted_code_exists,
    save_extracted_code_to_supabase,
    get_extracted_code_from_supabase,
    search_code_blocks,
    detect_content_type_and_source,
    extract_readthedocs_code_blocks,
    extract_markdown_code_blocks,
    extract_command_examples,
    extract_smart_context_before,
    extract_smart_context_after,
    extract_generic_html_code_blocks,
    extract_github_html_code_blocks,
    extract_mkdocs_code_blocks,
    extract_jupyter_notebook_cells
)
from parse_repo_into_neo4j import DirectNeo4jExtractor
from quick_introspect_core import run_quick_introspect
from runtime_probe import show_all_keys_or_attrs as rp_show_all, try_get_key as rp_try_get_key, try_get_attr as rp_try_get_attr

# Load environment variables from the project root .env file
# Priority: .env file > shell environment (.bashrc) > code defaults
project_root = Path(__file__).resolve().parent.parent
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path, override=True)

# Research Server Context
@dataclass
class ResearchContext:
    """
    Central context for the Research Server.
    Manages all core resources including web crawling, database connections,
    and knowledge graph components for comprehensive research workflows.
    """
    crawler: AsyncWebCrawler
    supabase_client: Client
    repo_extractor: Optional[Any] = None  # DirectNeo4jExtractor for knowledge graphs

@asynccontextmanager
async def research_lifespan(server: FastMCP) -> AsyncIterator[ResearchContext]:
    """
    Research Server Lifecycle Manager
    Initializes and manages all core components of the Research Server including:
    - Web crawler for content extraction
    - Database connections for code storage
    - Knowledge graph components for analysis
    Args:
        server: The Research Server FastMCP instance
    Yields:
        ResearchContext: Complete research context with all initialized components
    """
    # Browser configuration setup with retry mechanism
    browser_config = BrowserConfig(
        headless=True,
        verbose=False
    )
    
    # Initialize the crawler with retry mechanism
    crawler = None
    max_retries = 3
    for attempt in range(max_retries):
        try:
            crawler = AsyncWebCrawler(config=browser_config)
            await crawler.__aenter__()
            break  # Success, exit retry loop
        except Exception as e:
            if attempt == max_retries - 1:
                # Final attempt failed
                raise Exception(f"Failed to start web crawler after {max_retries} attempts. This may be due to browser resource conflicts. Error: {str(e)}")
            else:
                # Wait before retry
                await asyncio.sleep(1)
                if crawler:
                    try:
                        await crawler.__aexit__(None, None, None)
                    except:
                        pass  # Ignore cleanup errors
                    crawler = None
    # Initialize Supabase client
    supabase_client = get_supabase_client()
    # Initialize Neo4j components if configured and enabled
    repo_extractor = None
    # Check if knowledge graph functionality is enabled
    knowledge_graph_enabled = os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true"
    if knowledge_graph_enabled:
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_user = os.getenv("NEO4J_USER")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        if neo4j_uri and neo4j_user and neo4j_password:
            try:
                repo_extractor = DirectNeo4jExtractor(neo4j_uri, neo4j_user, neo4j_password)
                await repo_extractor.initialize()
                # print("✓ Neo4j knowledge graph extractor initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Neo4j extractor: {e}")
                repo_extractor = None
        else:
            logger.warning("Neo4j credentials not configured - knowledge graph tools will be unavailable")
    else:
        logger.info("Knowledge graph functionality disabled - set USE_KNOWLEDGE_GRAPH=true to enable")
    try:
        yield ResearchContext(
            crawler=crawler,
            supabase_client=supabase_client,
            repo_extractor=repo_extractor
        )
    finally:
        # Clean up components
        if crawler:
            try:
                await crawler.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing crawler: {e}")
        if repo_extractor:
            try:
                await repo_extractor.close()
                logger.info("Repository extractor closed")
            except Exception as e:
                logger.error(f"Error closing repository extractor: {e}")

# Research Server - FastMCP Application
mcp = FastMCP(
    "mcp_servers_and_tools/research_server",
    lifespan=research_lifespan,
    host=os.getenv("HOST", "127.0.0.1"),
    port=int(os.getenv("PORT", "8052"))
)


def is_sitemap(url: str) -> bool:
    """
    Check if a URL is a sitemap.
    Args:
        url: URL to check
    Returns:
        True if the URL is a sitemap, False otherwise
    """
    return url.endswith('sitemap.xml') or 'sitemap' in urlparse(url).path

def is_txt(url: str) -> bool:
    """
    Check if a URL is a text file.
    Args:
        url: URL to check
    Returns:
        True if the URL is a text file, False otherwise
    """
    return url.endswith('.txt')

def parse_sitemap(sitemap_url: str) -> List[str]:
    """
    Parse a sitemap and extract URLs.
    Args:
        sitemap_url: URL of the sitemap
    Returns:
        List of URLs found in the sitemap
    """
    resp = requests.get(sitemap_url)
    urls = []
    if resp.status_code == 200:
        try:
            tree = ElementTree.fromstring(resp.content)
            urls = [loc.text for loc in tree.findall('.//{*}loc')]
        except Exception as e:
            logger.error(f"Error parsing sitemap XML: {e}")
    return urls

def smart_chunk_markdown(text: str, chunk_size: int = 5000) -> List[str]:
    """Split text into chunks, respecting code blocks and paragraphs."""
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        # Calculate end position
        end = start + chunk_size
        # If we're at the end of the text, just take what's left
        if end >= text_length:
            chunks.append(text[start:].strip())
            break
        # Try to find a code block boundary first (```)
        chunk = text[start:end]
        code_block = chunk.rfind('```')
        if code_block != -1 and code_block > chunk_size * 0.3:
            end = start + code_block
        # If no code block, try to break at a paragraph
        elif '\n\n' in chunk:
            # Find the last paragraph break
            last_break = chunk.rfind('\n\n')
            if last_break > chunk_size * 0.3:  # Only break if we're past 30% of chunk_size
                end = start + last_break
        # If no paragraph break, try to break at a sentence
        elif '. ' in chunk:
            # Find the last sentence break
            last_period = chunk.rfind('. ')
            if last_period > chunk_size * 0.3:  # Only break if we're past 30% of chunk_size
                end = start + last_period + 1
        # Extract chunk and clean it up
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        # Move start position for next chunk
        start = end
    return chunks

def github_blob_to_raw(url: str) -> str:
    """
    Convert a GitHub blob URL to the corresponding raw URL if applicable.
    For example:
    https://github.com/user/repo/blob/branch/path/to/file.md
    ->
    https://raw.githubusercontent.com/user/repo/branch/path/to/file.md
    If the URL is not a GitHub blob URL, return it unchanged.
    """
    if not url:
        return url
    # Check if already converted
    if 'raw.githubusercontent.com' in url:
        return url
    m = re.match(r'https://github.com/([^/]+)/([^/]+)/blob/([^#?]+)', url)
    if m:
        user, repo, path = m.groups()
        return f'https://raw.githubusercontent.com/{user}/{repo}/{path}'
    return url

def validate_and_normalize_url(url: str) -> tuple[str, bool]:
    """
    Validate and normalize a URL for processing.
    Handles:
    - view-source: URLs (converts to regular URLs)
    - GitHub blob URLs (converts to raw URLs)
    - Regular URLs (validates and returns as-is)
    Returns:
        Tuple of (normalized_url, is_valid)
    """
    if not url:
        return url, False
    try:
        # Handle view-source: URLs
        if url.startswith('view-source:'):
            # Remove view-source: prefix
            url = url[12:]  # len('view-source:') = 12
        # Basic URL validation
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url, False
        # Normalize the URL (GitHub blob to raw, etc.)
        normalized = github_blob_to_raw(url)
        return normalized, True
    except Exception:
        return url, False


@mcp.tool()
async def extract_code_from_url(ctx: Context, url: str = None, urls: list = None) -> str:
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
        ctx: The MCP server provided context
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
            return await _extract_code_from_url_internal(ctx, url, urls)
        
        try:
            result = await asyncio.wait_for(extract_with_timeout(), timeout=EXTRACTION_TIMEOUT)
            elapsed_time = time.time() - start_time
            # print(f"✅ Extraction completed in {elapsed_time:.2f} seconds")
            return result
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            logger.warning(f"Extraction timed out after {elapsed_time:.2f} seconds")
            
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


async def _extract_code_from_url_internal(ctx: Context, url: str = None, urls: list = None) -> str:
    """
    Internal implementation of extract_code_from_url without timeout wrapper.
    This is the original function logic.
    """
    try:
        supabase_client = ctx.request_context.lifespan_context.supabase_client
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
            crawler = ctx.request_context.lifespan_context.crawler
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
                # print(f"Error parsing single page result: {e}")
                pass
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
        
async def _extract_code_single_page(crawler: AsyncWebCrawler, url: str) -> str:
    """
    Extract code from a single webpage without following any links.
    
    Optimized extraction strategy:
    1. HTML extraction only for ReadTheDocs/Sphinx documentation
    2. Markdown extraction for other content types
    3. Special handling for Jupyter notebooks (JSON extraction with raw URL fallback)
    4. No deduplication to preserve all code blocks
    """
    try:
        original_url = url
        url, is_valid = validate_and_normalize_url(url)
        if not is_valid:
            return json.dumps({
                "success": False,
                "url": original_url,
                "crawl_method": "single_page",
                "error": "Invalid URL provided for single page extraction",
                "extracted_code": []
            }, indent=2)
        # Configure crawler
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS, 
            stream=False,
            verbose=False
        )
        # Fetch the page
        result = await crawler.arun(url=url, config=run_config)
        # Check if crawl was successful and we have content
        if not result.success:
            return json.dumps({
                "success": False,
                "url": original_url,
                "crawl_method": "single_page",
                "error": "Failed to crawl page",
                "error_details": getattr(result, 'error_message', 'Unknown error'),
                "extracted_code": []
            }, indent=2)
        if not hasattr(result, 'html') and not hasattr(result, 'markdown'):
            return json.dumps({
                "success": False,
                "url": original_url,
                "crawl_method": "single_page",
                "error": "No content available (neither HTML nor Markdown)",
                "extracted_code": []
            }, indent=2)
        code_blocks = []
        extraction_method = "none"
        doc_system = "unknown"
        # Strategy: HTML only for ReadTheDocs/Sphinx, otherwise use markdown
        # For Jupyter notebooks, prioritize JSON extraction
        # 1) HTML path only for ReadTheDocs/Sphinx
        if hasattr(result, 'html') and result.html:
            try:
                # Detect documentation system
                content_type, detected_doc_system, has_code = detect_content_type_and_source(
                    result.html, 
                    url
                )
                doc_system = detected_doc_system
                # Only use HTML extraction for ReadTheDocs/Sphinx
                if detected_doc_system in ['readthedocs', 'sphinx']:
                    code_blocks = extract_readthedocs_code_blocks(result.html, min_length=3)
                    extraction_method = f"html_{detected_doc_system}"
                else:
                    code_blocks = []
            except Exception as e:
                import traceback
                traceback.print_exc()
                code_blocks = []
        # 2) Markdown path for everything else
        if not code_blocks and hasattr(result, 'markdown') and result.markdown:
            try:
                md = result.markdown
                extraction_method = "markdown"
                # Check if this is Jupyter notebook content
                is_ipynb_url = url.lower().endswith('.ipynb')
                looks_like_json_notebook = md.strip().startswith('{') and '"cells"' in md[:2000]
                if is_ipynb_url or looks_like_json_notebook:
                    # Try direct JSON extraction from markdown
                    if looks_like_json_notebook:
                        code_blocks = extract_jupyter_notebook_cells(md, min_length=3)
                        doc_system = 'jupyter'
                        extraction_method = 'markdown_jupyter_json'
                    else:
                        # It's an .ipynb URL but markdown is not JSON (GitHub page). Fetch raw and parse
                        raw_url = github_blob_to_raw(url)
                        # Try crawler first (may not return JSON text)
                        raw_result = await crawler.arun(url=raw_url, config=run_config)
                        raw_content = (getattr(raw_result, 'text', None) or getattr(raw_result, 'markdown', None) or '')
                        if not (raw_content and raw_content.strip().startswith('{') and '"cells"' in raw_content[:2000]):
                            # Fallback to direct HTTP request
                            try:
                                resp = requests.get(raw_url, timeout=15)
                                if resp.status_code == 200:
                                    raw_content = resp.text
                                else:
                                    raw_content = ''
                            except Exception as _e:
                                raw_content = ''
                        if raw_content and raw_content.strip().startswith('{') and '"cells"' in raw_content[:2000]:
                            code_blocks = extract_jupyter_notebook_cells(raw_content, min_length=3)
                            doc_system = 'jupyter'
                            extraction_method = 'raw_jupyter_json'
                        else:
                            code_blocks = []
                # If still nothing, extract markdown code blocks + commands
                if not code_blocks:
                    md_blocks = extract_markdown_code_blocks(md, min_length=3)
                    command_blocks = extract_command_examples(md, min_length=3)
                    # Filter overly long command blocks
                    command_blocks = [b for b in command_blocks if len(b.get('code','')) < 5000]
                    # Merge unique command blocks
                    if command_blocks:
                        existing_codes = {block.get('code', '').strip() for block in md_blocks}
                        initial_count = len(md_blocks)
                        for cmd_block in command_blocks:
                            if cmd_block.get('code', '').strip() not in existing_codes:
                                md_blocks.append(cmd_block)
                    code_blocks = md_blocks
                    doc_system = 'unknown'
                    extraction_method = 'markdown_generic'
            except Exception as e:
                import traceback
                traceback.print_exc()
                code_blocks = []
        # Keep all code blocks (no deduplication)
        unique_code_blocks = code_blocks
        # Format extracted code blocks
        all_extracted_code = []
        for i, block in enumerate(unique_code_blocks):
            # Enhance context if missing
            context_before = block.get('context_before', '')
            context_after = block.get('context_after', '')
            if (not context_before or not context_after) and hasattr(result, 'markdown') and result.markdown:
                code_snippet = block.get('code', '')[:50]
                position = result.markdown.find(code_snippet)
                if position > 0:
                    context_before = extract_smart_context_before(
                        result.markdown, position, max_chars=1000
                    )
                    end_position = position + len(block.get('code', ''))
                    context_after = extract_smart_context_after(
                        result.markdown, end_position, max_chars=1000
                    )
            # Build code block info
            code_info = {
                "index": i + 1,
                "url": original_url,
                "type": block.get('type', 'code'),
                "language": block.get('language', 'unknown'),
                "code": block.get('code', ''),
                "context_before": context_before[:1000],
                "context_after": context_after[:1000],
                "extraction_method": extraction_method,
                "doc_system": doc_system,
                "summary": _generate_code_summary({
                    **block,
                    'context_before': context_before,
                    'context_after': context_after
                })
            }
            # Add optional metadata
            if block.get('title'):
                code_info['title'] = block['title']
            if block.get('description'):
                code_info['description'] = block['description']
            all_extracted_code.append(code_info)
        # Return results
        return json.dumps({
            "success": True,
            "url": original_url,
            "processed_url": url,
            "crawl_method": "single_page",
            "extraction_method": extraction_method,
            "doc_system": doc_system,
            "content_length": len(result.html) if hasattr(result, 'html') and result.html else len(result.markdown) if hasattr(result, 'markdown') and result.markdown else 0,
            "code_blocks_found": len(all_extracted_code),
            "extracted_code": all_extracted_code,
            "message": f"Found {len(all_extracted_code)} code blocks" if all_extracted_code else "No code blocks found in page"
        }, indent=2)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({
            "success": False,
            "url": url,
            "crawl_method": "single_page",
            "error": str(e),
            "extracted_code": []
        }, indent=2)

async def _extract_code_smart_crawl(crawler: AsyncWebCrawler, url: str) -> str:
    """Extract code using smart crawl for complex sites."""
    try:
        # Store original URL
        original_url = url
        # Automatically convert GitHub blob URLs to raw URLs for better extraction
        url, is_valid = validate_and_normalize_url(url)
        if not is_valid:
            return json.dumps({
                "success": False,
                "url": original_url,
                "error": "Invalid URL provided for smart crawl",
                "extracted_code": []
            }, indent=2)
        crawl_results = []
        if is_txt(url):
            # For text files, use simple crawl
            crawl_results = await crawl_markdown_file(crawler, url)
        elif is_sitemap(url):
            # For sitemaps, extract URLs and crawl in parallel
            sitemap_urls = parse_sitemap(url)
            crawl_results = await crawl_batch(crawler, sitemap_urls[:5])  # Limit to first 5 URLs
        else:
            # For regular webpages, crawl recursively
            crawl_results = await crawl_recursive_internal_links(crawler, [url], max_depth=2, max_concurrent=5)
        # Extract code from all crawled results
        all_extracted_code = []
        total_content_length = 0
        for result in crawl_results:
            if result.get('success') and result.get('markdown'):
                # Pass URL context to extraction
                result_url = result.get('url', url)
                code_blocks = extract_code_blocks(result['markdown'], min_length=3, url=result_url)
                total_content_length += len(result['markdown'])
                for i, block in enumerate(code_blocks):
                    code_info = {
                        "index": len(all_extracted_code) + 1,
                        "url": original_url,  # Use the original URL
                        "type": block.get('type', 'unknown'),
                        "language": block.get('language', 'unknown'),
                        "code": block['code'],
                        "context_before": block.get('context_before', '')[:1000],
                        "context_after": block.get('context_after', '')[:1000],
                        "summary": _generate_code_summary(block)
                    }
                    all_extracted_code.append(code_info)
        return json.dumps({
            "success": True,
            "url": original_url,
            "processed_url": url,
            "crawl_method": "smart_crawl",
            "content_length": total_content_length,
            "code_blocks_found": len(all_extracted_code),
            "extracted_code": all_extracted_code
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "url": original_url,
            "error": str(e),
            "extracted_code": []
        }, indent=2)

async def crawl_batch(crawler: AsyncWebCrawler, urls: List[str], max_concurrent: int = 10) -> List[Dict[str, Any]]:
    """
    Batch crawl multiple URLs in parallel.
    Args:
        crawler: AsyncWebCrawler instance
        urls: List of URLs to crawl
        max_concurrent: Maximum number of concurrent browser sessions
    Returns:
        List of dictionaries with URL, markdown content, and success status
    """
    crawl_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, 
        stream=False,
        verbose=False
    )
    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=70.0,
        check_interval=1.0,
        max_session_permit=max_concurrent
    )
    try:
        results = await crawler.arun_many(urls=urls, config=crawl_config, dispatcher=dispatcher)
        return [{
            'url': r.url, 
            'markdown': r.markdown,
            'success': True
        } for r in results if r.success and r.markdown]
    except Exception as e:
        logger.error(f"Error in batch crawl: {e}")
        return []
    finally:
        # Ensure dispatcher is properly cleaned up
        try:
            await dispatcher.close()
        except:
            pass

async def crawl_recursive_internal_links(crawler: AsyncWebCrawler, start_urls: List[str], max_depth: int = 3, max_concurrent: int = 10) -> List[Dict[str, Any]]:
    """
    Recursively crawl internal links from start URLs up to a maximum depth.
    Args:
        crawler: AsyncWebCrawler instance
        start_urls: List of starting URLs
        max_depth: Maximum recursion depth
        max_concurrent: Maximum number of concurrent browser sessions
    Returns:
        List of dictionaries with URL and markdown content
    """
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, 
        stream=False,
        verbose=False
    )
    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=70.0,
        check_interval=1.0,
        max_session_permit=max_concurrent
    )
    visited = set()
    def normalize_url(url):
        return urldefrag(url)[0]
    current_urls = set([normalize_url(u) for u in start_urls])
    results_all = []
    for depth in range(max_depth):
        urls_to_crawl = [normalize_url(url) for url in current_urls if normalize_url(url) not in visited]
        if not urls_to_crawl:
            break
        results = await crawler.arun_many(urls=urls_to_crawl, config=run_config, dispatcher=dispatcher)
        next_level_urls = set()
        for result in results:
            norm_url = normalize_url(result.url)
            visited.add(norm_url)
            if result.success and result.markdown:
                results_all.append({
                    'url': result.url, 
                    'markdown': result.markdown,
                    'success': True
                })
                for link in result.links.get("internal", []):
                    next_url = normalize_url(link["href"])
                    if next_url not in visited:
                        next_level_urls.add(next_url)
        current_urls = next_level_urls
    return results_all

async def crawl_markdown_file(crawler: AsyncWebCrawler, url: str) -> List[Dict[str, Any]]:
    """
    Crawl a .txt or markdown file.
    Args:
        crawler: AsyncWebCrawler instance
        url: URL of the file
    Returns:
        List of dictionaries with URL, markdown content, and success status
    """
    try:
        crawl_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS, 
            stream=False,
            verbose=False
        )
        result = await crawler.arun(url=url, config=crawl_config)
        if result.success:
            # Try to get content, prefer markdown then text
            content = result.markdown or result.text or ""
            if content:
                return [{
                    'url': url, 
                    'markdown': content,
                    'success': True
                }]
            else:
                # print(f"No content found for {url}")
                return [{
                    'url': url,
                    'markdown': '',
                    'success': False,
                    'error': 'No content found'
                }]
        else:
            # print(f"Failed to crawl {url}: {result.error_message}")
            return [{
                'url': url,
                'markdown': '',
                'success': False,
                'error': result.error_message or 'Unknown error'
            }]
    except Exception as e:
        # print(f"Exception while crawling {url}: {str(e)}")
        return [{
            'url': url,
            'markdown': '',
            'success': False,
            'error': str(e)
        }]

def _generate_code_summary(block: Dict[str, Any]) -> str:
    """Generate a summary for a code block using AI Agent."""
    # Check if code summary generation is enabled
    generate_summary = os.getenv("GENERATE_CODE_SUMMARY", "false").lower() == "true"
    if not generate_summary:
        # Return empty string when summary generation is disabled
        return ""
    try:
        code = block.get('code', '')
        context_before = block.get('context_before', '')
        context_after = block.get('context_after', '')
        # Use the same logic as generate_code_example_summary
        return generate_code_example_summary(code, context_before, context_after)
    except Exception as e:
        logger.error(f"Error generating code summary: {e}")
        # Fallback to simple summary
        code = block.get('code', '')
        code_type = block.get('type', 'unknown')
        return f"{code_type.title()}: {code.strip()[:100]}..."


@mcp.tool()
async def retrieve_extracted_code(ctx: Context, query: str, match_count: int = 5) -> str:
    """
    Retrieve extracted code blocks relevant to the query.
    This tool searches the extracted_code table for code blocks relevant to the query and returns
    the matching examples with their summaries and context.
    You can call this tool multiple times with different queries to get more relevant results.
    Args:
        ctx: The MCP server provided context
        query: The search query
        match_count: Maximum number of results to return (default: 5)
    Returns:
        JSON string with the search results
    """
    try:
        # Get the Supabase client from the context
        supabase_client = ctx.request_context.lifespan_context.supabase_client
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


@mcp.tool()
async def quick_introspect(
    ctx: Context,
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
      * If unsure about the absolute path, use your check_package_version tool (if you have this tool) to obtain it.
      * If repo_hint fails to import, try providing an absolute or relative package_path (relative path starts from {SITE_PACKAGES_HINT}).
    - Function vs Method:
      * Use method_hint when the target is a class member (instance/class method). Do not use function_hint for class/instance methods. **Most of the time, you should use method_hint**
      * Use function_hint only for top-level (module-level) functions; optionally add module_hint to narrow
      * Heuristics: analyze the call-site pattern — calls like SomeClass.method(...)/obj.method(...) → method_hint; calls like package.module.function(...), module.function(...), function(...) → function_hint
    - method_hint can be provided without class_hint to trigger a repo-wide search (noisy but useful, but often it is more recommended to add fuzzy or exact class_hint to narrow down the search).
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


@mcp.tool()
async def runtime_probe_snippet(ctx: Context, snippet: str) -> str:
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
            "    if (_root / 'research-server' / 'introspection_and_probe').exists():\n"
            "        sys.path.insert(0, str(_root / 'research-server' / 'introspection_and_probe'))\n"
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
            "    if (_root / 'research-server' / 'introspection_and_probe').exists():\n"
            "        sys.path.insert(0, str(_root / 'research-server' / 'introspection_and_probe'))\n"
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


@mcp.tool()
async def parse_local_package(ctx: Context, package_name: str = None, package_path: str = None) -> str:
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
        ctx: The MCP server provided context
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
        # Get the repository extractor from context
        repo_extractor = ctx.request_context.lifespan_context.repo_extractor
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


@mcp.tool()
async def query_knowledge_graph(ctx: Context, command: str) -> str:
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
        ctx: The MCP server provided context
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
        # Get Neo4j driver from context
        repo_extractor = ctx.request_context.lifespan_context.repo_extractor
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

async def _handle_repos_command(session, command: str) -> str:
    """Handle 'repos' command - list all repositories"""
    query = "MATCH (r:Repository) RETURN r.name as name ORDER BY r.name"
    result = await session.run(query)
    repos = []
    async for record in result:
        repos.append(record['name'])
    return json.dumps({
        "success": True,
        "command": command,
        "data": {
            "repositories": repos
        },
        "metadata": {
            "total_results": len(repos),
            "limited": False
        }
    }, indent=2)

async def _handle_explore_command(session, command: str, repo_name: str) -> str:
    """Handle 'explore <repo>' command - get repository overview"""
    # Check if repository exists
    repo_check_query = "MATCH (r:Repository {name: $repo_name}) RETURN r.name as name"
    result = await session.run(repo_check_query, repo_name=repo_name)
    repo_record = await result.single()
    if not repo_record:
        return json.dumps({
            "success": False,
            "command": command,
            "error": f"Repository '{repo_name}' not found in knowledge graph"
        }, indent=2)
    # Get file count
    files_query = """
    MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(f:File)
    RETURN count(f) as file_count
    """
    result = await session.run(files_query, repo_name=repo_name)
    file_count = (await result.single())['file_count']
    # Get class count
    classes_query = """
    MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(f:File)-[:DEFINES]->(c:Class)
    RETURN count(DISTINCT c) as class_count
    """
    result = await session.run(classes_query, repo_name=repo_name)
    class_count = (await result.single())['class_count']
    # Get function count
    functions_query = """
    MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(f:File)-[:DEFINES]->(func:Function)
    RETURN count(DISTINCT func) as function_count
    """
    result = await session.run(functions_query, repo_name=repo_name)
    function_count = (await result.single())['function_count']
    # Get method count
    methods_query = """
    MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(f:File)-[:DEFINES]->(c:Class)-[:HAS_METHOD]->(m:Method)
    RETURN count(DISTINCT m) as method_count
    """
    result = await session.run(methods_query, repo_name=repo_name)
    method_count = (await result.single())['method_count']
    return json.dumps({
        "success": True,
        "command": command,
        "data": {
            "repository": repo_name,
            "statistics": {
                "files": file_count,
                "classes": class_count,
                "functions": function_count,
                "methods": method_count
            }
        },
        "metadata": {
            "total_results": 1,
            "limited": False
        }
    }, indent=2)

async def _handle_classes_command(session, command: str, repo_name: str = None) -> str:
    """Handle 'classes [repo]' command - list classes"""
    limit = 20
    if repo_name:
        query = """
        MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(f:File)-[:DEFINES]->(c:Class)
        RETURN c.name as name, c.full_name as full_name
        ORDER BY c.name
        LIMIT $limit
        """
        result = await session.run(query, repo_name=repo_name, limit=limit)
    else:
        query = """
        MATCH (c:Class)
        RETURN c.name as name, c.full_name as full_name
        ORDER BY c.name
        LIMIT $limit
        """
        result = await session.run(query, limit=limit)
    classes = []
    async for record in result:
        classes.append({
            'name': record['name'],
            'full_name': record['full_name']
        })
    return json.dumps({
        "success": True,
        "command": command,
        "data": {
            "classes": classes,
            "repository_filter": repo_name
        },
        "metadata": {
            "total_results": len(classes),
            "limited": len(classes) >= limit
        }
    }, indent=2)

async def _handle_class_command(session, command: str, class_name: str) -> str:
    """Handle 'class <name>' command - explore specific class"""
    # Find the class
    class_query = """
    MATCH (c:Class)
    WHERE c.name = $class_name OR c.full_name = $class_name
    RETURN c.name as name, c.full_name as full_name
    LIMIT 1
    """
    result = await session.run(class_query, class_name=class_name)
    class_record = await result.single()
    if not class_record:
        return json.dumps({
            "success": False,
            "command": command,
            "error": f"Class '{class_name}' not found in knowledge graph"
        }, indent=2)
    actual_name = class_record['name']
    full_name = class_record['full_name']
    # Get methods
    methods_query = """
    MATCH (c:Class)-[:HAS_METHOD]->(m:Method)
    WHERE c.name = $class_name OR c.full_name = $class_name
    RETURN m.name as name, m.params_list as params_list, m.params_detailed as params_detailed, m.return_type as return_type
    ORDER BY m.name
    """
    result = await session.run(methods_query, class_name=class_name)
    methods = []
    async for record in result:
        # Use detailed params if available, fall back to simple params
        params_to_use = record['params_detailed'] or record['params_list'] or []
        methods.append({
            'name': record['name'],
            'parameters': params_to_use,
            'return_type': record['return_type'] or 'Any'
        })
    # Get attributes
    attributes_query = """
    MATCH (c:Class)-[:HAS_ATTRIBUTE]->(a:Attribute)
    WHERE c.name = $class_name OR c.full_name = $class_name
    RETURN a.name as name, a.type as type
    ORDER BY a.name
    """
    result = await session.run(attributes_query, class_name=class_name)
    attributes = []
    async for record in result:
        attributes.append({
            'name': record['name'],
            'type': record['type'] or 'Any'
        })
    return json.dumps({
        "success": True,
        "command": command,
        "data": {
            "class": {
                "name": actual_name,
                "full_name": full_name,
                "methods": methods,
                "attributes": attributes
            }
        },
        "metadata": {
            "total_results": 1,
            "methods_count": len(methods),
            "attributes_count": len(attributes),
            "limited": False
        }
    }, indent=2)

async def _handle_method_command(session, command: str, method_name: str, class_name: str = None) -> str:
    """Handle 'method <name> [class]' command - search for methods"""
    if class_name:
        query = """
        MATCH (c:Class)-[:HAS_METHOD]->(m:Method)
        WHERE (c.name = $class_name OR c.full_name = $class_name)
          AND m.name = $method_name
        RETURN c.name as class_name, c.full_name as class_full_name,
               m.name as method_name, m.params_list as params_list, 
               m.params_detailed as params_detailed, m.return_type as return_type, m.args as args
        """
        result = await session.run(query, class_name=class_name, method_name=method_name)
    else:
        query = """
        MATCH (c:Class)-[:HAS_METHOD]->(m:Method)
        WHERE m.name = $method_name
        RETURN c.name as class_name, c.full_name as class_full_name,
               m.name as method_name, m.params_list as params_list, 
               m.params_detailed as params_detailed, m.return_type as return_type, m.args as args
        ORDER BY c.name
        LIMIT 20
        """
        result = await session.run(query, method_name=method_name)
    methods = []
    async for record in result:
        # Use detailed params if available, fall back to simple params
        params_to_use = record['params_detailed'] or record['params_list'] or []
        methods.append({
            'class_name': record['class_name'],
            'class_full_name': record['class_full_name'],
            'method_name': record['method_name'],
            'parameters': params_to_use,
            'return_type': record['return_type'] or 'Any',
            'legacy_args': record['args'] or []
        })
    if not methods:
        return json.dumps({
            "success": False,
            "command": command,
            "error": f"Method '{method_name}'" + (f" in class '{class_name}'" if class_name else "") + " not found"
        }, indent=2)
    return json.dumps({
        "success": True,
        "command": command,
        "data": {
            "methods": methods,
            "class_filter": class_name
        },
        "metadata": {
            "total_results": len(methods),
            "limited": len(methods) >= 20 and not class_name
        }
    }, indent=2)

async def _handle_query_command(session, command: str, cypher_query: str) -> str:
    """Handle 'query <cypher>' command - execute custom Cypher query"""
    try:
        # Execute the query with a limit to prevent overwhelming responses
        result = await session.run(cypher_query)
        records = []
        count = 0
        async for record in result:
            records.append(dict(record))
            count += 1
            if count >= 20:  # Limit results to prevent overwhelming responses
                break
        return json.dumps({
            "success": True,
            "command": command,
            "data": {
                "query": cypher_query,
                "results": records
            },
            "metadata": {
                "total_results": len(records),
                "limited": len(records) >= 20
            }
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "command": command,
            "error": f"Cypher query error: {str(e)}",
            "data": {
                "query": cypher_query
            }
        }, indent=2)


async def main():
    transport = os.getenv("TRANSPORT", "sse")
    if transport == 'sse':
        # Run the MCP server with sse transport
        await mcp.run_sse_async()
    else:
        # Run the MCP server with stdio transport
        await mcp.run_stdio_async()

if __name__ == "__main__":
    asyncio.run(main())