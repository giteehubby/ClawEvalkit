"""
Utility functions for the research server.
"""
import os
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
import json
from supabase import create_client, Client
from urllib.parse import urlparse
import openai
import re
import time
import html
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
import asyncio
# Load OpenAI API key for embeddings
openai.api_key = os.getenv("OPENAI_API_KEY")


def get_supabase_client() -> Client:
    """
    Get a Supabase client with the URL and key from environment variables.
    Returns:
        Supabase client instance
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment variables")
    return create_client(url, key)


async def create_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Create embeddings for multiple texts in a single API call.
    Args:
        texts: List of texts to create embeddings for
    Returns:
        List of embeddings (each embedding is a list of floats)
    """
    if not texts:
        return []
    max_retries = 3
    retry_delay = 1.0  # Start with 1 second delay
    for retry in range(max_retries):
        try:
            # Offload blocking OpenAI call to a thread
            response = await asyncio.to_thread(
                openai.embeddings.create,
                model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            if retry < max_retries - 1:
                print(f"Error creating batch embeddings (attempt {retry + 1}/{max_retries}): {e}")
                print(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 16.0)
            else:
                print(f"Failed to create batch embeddings after {max_retries} attempts: {e}")
                # Try creating embeddings one by one as fallback
                print("Attempting to create embeddings individually...")
                embeddings = []
                successful_count = 0
                for i, text in enumerate(texts):
                    try:
                        individual_response = await asyncio.to_thread(
                            openai.embeddings.create,
                            model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
                            input=[text],
                        )
                        embeddings.append(individual_response.data[0].embedding)
                        successful_count += 1
                    except Exception as individual_error:
                        print(f"Failed to create embedding for text {i}: {individual_error}")
                        # Add zero embedding as fallback
                        embeddings.append([0.0] * 1536)
                print(f"Successfully created {successful_count}/{len(texts)} embeddings individually")
                return embeddings


async def create_embedding(text: str) -> List[float]:
    """
    Create an embedding for a single text using OpenAI's API.
    Args:
        text: Text to create an embedding for
    Returns:
        List of floats representing the embedding
    """
    try:
        embeddings = await create_embeddings_batch([text])
        return embeddings[0] if embeddings else [0.0] * 1536
    except Exception as e:
        print(f"Error creating embedding: {e}")
        # Return empty embedding if there's an error
        return [0.0] * 1536


def detect_content_type_and_source(html_content: str, url: str) -> Tuple[str, str, bool]:
    """
    Detect the type of content and documentation system from HTML and URL.
    Returns:
        Tuple of (content_type, doc_system, has_code)
        - content_type: 'html', 'jupyter', 'markdown', 'raw_code'
        - doc_system: 'readthedocs', 'sphinx', 'mkdocs', 'github', 'jupyter', 'unknown'
        - has_code: whether the content contains code blocks
    """
    # Check if it's a raw code file based on URL
    if url:
        url_lower = url.lower()
        # Check for raw GitHub URLs or direct code file extensions
        if 'raw.githubusercontent.com' in url_lower or ('github.com' in url_lower and '/raw/' in url_lower):
            code_extensions = ['.py', '.js', '.java', '.cpp', '.c', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala', '.r', '.m']
            for ext in code_extensions:
                if url_lower.endswith(ext):
                    return ('raw_code', 'github', True)
        # Special handling for GitHub Jupyter notebooks (.ipynb files)
        if url_lower.endswith('.ipynb'):
            return ('jupyter', 'github', True)
    # Quick check for Jupyter notebooks (JSON format)
    if html_content.strip().startswith('{') and '"cells"' in html_content[:1000]:
        try:
            import json
            json.loads(html_content)
            return ('jupyter', 'jupyter', True)
        except:
            pass
    # Check for Jupyter notebook HTML rendering
    if ('jp-Notebook' in html_content or 'notebook-container' in html_content or 
        'jupyter' in html_content.lower() or 'ipynb' in html_content.lower()):
        return ('jupyter', 'jupyter', True)
    # Check if it's markdown content (but not HTML with markdown)
    if not '<html' in html_content[:1000] and not '<!DOCTYPE' in html_content[:1000]:
        if html_content.strip().startswith('#') or '```' in html_content[:1000]:
            # Strong indicators of markdown
            has_code = '```' in html_content or '    ' in html_content  # Code blocks or indented code
            return ('markdown', 'unknown', has_code)
    # Parse HTML for detailed detection
    soup = BeautifulSoup(html_content, 'html.parser')
    # Check URL patterns first (most reliable)
    url_lower = url.lower() if url else ''
    # ReadTheDocs detection - PRIORITY CHECK
    if 'readthedocs' in url_lower:
        # Check for code blocks specific to ReadTheDocs
        highlight_divs = soup.find_all('div', class_=re.compile(r'highlight'))
        has_code = len(highlight_divs) > 0
        return ('html', 'readthedocs', has_code)
    # GitHub detection from URL (but not for .ipynb files which are handled above)
    if 'github.com' in url_lower and not url_lower.endswith('.ipynb'):
        has_code = bool(soup.find('pre') or soup.find('code'))
        return ('html', 'github', has_code)
    # Check for documentation system markers in HTML
    # ReadTheDocs/Sphinx detection by HTML structure
    if soup.find('div', class_='wy-nav-content'):  # ReadTheDocs theme
        highlight_divs = soup.find_all('div', class_=re.compile(r'highlight'))
        has_code = len(highlight_divs) > 0
        return ('html', 'readthedocs', has_code)
    if soup.find('div', class_='sphinxsidebar'):  # Classic Sphinx
        has_code = bool(soup.find('div', class_=re.compile(r'highlight')))
        return ('html', 'sphinx', has_code)
    if soup.find('div', class_='rst-content'):  # RestructuredText content
        has_code = bool(soup.find('div', class_=re.compile(r'highlight')))
        return ('html', 'sphinx', has_code)
    # Check for highlight divs (common in ReadTheDocs/Sphinx)
    highlight_divs = soup.find_all('div', class_=re.compile(r'highlight'))
    if len(highlight_divs) > 0:
        # Further check for ReadTheDocs/Sphinx patterns
        if soup.find('div', class_='document') or soup.find('div', role='main'):
            return ('html', 'readthedocs', True)  # Highlight divs mean there's code
        # If many highlight divs, likely ReadTheDocs/Sphinx
        if len(highlight_divs) >= 2:
            return ('html', 'readthedocs', True)
    # MkDocs detection
    if soup.find('div', class_='md-container'):
        has_code = bool(soup.find('pre') or soup.find('code'))
        return ('html', 'mkdocs', has_code)
    if soup.find('nav', class_='md-nav'):
        has_code = bool(soup.find('pre') or soup.find('code'))
        return ('html', 'mkdocs', has_code)
    # GitHub detection by HTML structure
    if soup.find('div', class_='markdown-body'):
        has_code = bool(soup.find('pre') or soup.find('code'))
        return ('html', 'github', has_code)
    if soup.find('article', class_='markdown-body'):
        has_code = bool(soup.find('pre') or soup.find('code'))
        return ('html', 'github', has_code)
    # Check meta tags
    generator = soup.find('meta', attrs={'name': 'generator'})
    if generator:
        content = generator.get('content', '').lower()
        if 'sphinx' in content:
            has_code = bool(soup.find('div', class_=re.compile(r'highlight')))
            return ('html', 'sphinx', has_code)
        if 'mkdocs' in content:
            has_code = bool(soup.find('pre') or soup.find('code'))
            return ('html', 'mkdocs', has_code)
    # Final check for any code indicators
    has_code = False
    code_indicators = [
        soup.find('pre'),
        soup.find('code'),
        soup.find('div', class_=re.compile(r'highlight')),
        soup.find('div', class_='codehilite'),
        soup.find('div', class_='sourceCode'),
        soup.find('div', class_='literal-block'),
        '```' in html_content,
        '<pre>' in html_content,
        '<code>' in html_content
    ]
    has_code = any(code_indicators)
    # Default to HTML with unknown system
    return ('html', 'unknown', has_code)


def detect_language_from_url(url: str) -> str:
    """
    Detect programming language from file extension in URL.
    Args:
        url: URL to analyze
    Returns:
        Language string (e.g., 'python', 'javascript', 'java')
    """
    extension_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.cs': 'csharp',
        '.go': 'go',
        '.rs': 'rust',
        '.php': 'php',
        '.rb': 'ruby',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.scala': 'scala',
        '.r': 'r',
        '.m': 'matlab',
        '.sql': 'sql',
        '.sh': 'bash',
        '.bash': 'bash',
        '.zsh': 'zsh',
        '.yml': 'yaml',
        '.yaml': 'yaml',
        '.json': 'json',
        '.xml': 'xml',
        '.html': 'html',
        '.css': 'css',
        '.md': 'markdown',
        '.txt': 'text'
    }
    for ext, lang in extension_map.items():
        if url.lower().endswith(ext):
            return lang
    return 'text'


def extract_html_code_blocks(html_content: str, doc_system: str) -> List[Dict[str, Any]]:
    """
    Extract code blocks from HTML based on documentation system.
    Args:
        html_content: HTML content to parse
        doc_system: Documentation system type ('sphinx', 'mkdocs', 'github_html', etc.)
    Returns:
        List of code blocks with metadata
    """
    if doc_system == 'sphinx' or doc_system == 'readthedocs':
        return extract_readthedocs_code_blocks(html_content)
    elif doc_system == 'mkdocs':
        return extract_mkdocs_code_blocks(html_content)
    elif doc_system == 'github_html':
        return extract_github_html_code_blocks(html_content)
    else:
        # Fallback to generic HTML code extraction
        return extract_generic_html_code_blocks(html_content)


def extract_mkdocs_code_blocks(html_content: str) -> List[Dict[str, Any]]:
    """
    Extract code blocks from MkDocs generated HTML.
    MkDocs patterns:
    - <pre><code class="language-python">...</code></pre>
    - <div class="highlight"><pre><span></span><code>...</code></pre></div>
    """
    code_blocks = []
    # Pattern 1: Standard MkDocs with language class
    pattern1 = r'<pre><code class="language-(\w+)">(.*?)</code></pre>'
    matches = re.finditer(pattern1, html_content, re.DOTALL)
    for i, match in enumerate(matches):
        language = match.group(1)
        code = html.unescape(match.group(2))
        code = re.sub(r'<[^>]+>', '', code)  # Remove any remaining HTML tags
        if code.strip():
            code_blocks.append({
                'code': code.strip(),
                'language': language,
                'type': 'mkdocs_code_block',
                'context_before': '',
                'context_after': '',
                'full_context': code.strip()
            })
    # Pattern 2: MkDocs with highlight div
    pattern2 = r'<div class="highlight"><pre><span></span><code>(.*?)</code></pre></div>'
    matches = re.finditer(pattern2, html_content, re.DOTALL)
    for i, match in enumerate(matches):
        code = html.unescape(match.group(1))
        code = re.sub(r'<span[^>]*>', '', code)
        code = re.sub(r'</span>', '', code)
        if code.strip():
            code_blocks.append({
                'code': code.strip(),
                'language': 'text',
                'type': 'mkdocs_code_block',
                'context_before': '',
                'context_after': '',
                'full_context': code.strip()
            })
    return code_blocks


def extract_github_html_code_blocks(html_content: str) -> List[Dict[str, Any]]:
    """
    Extract code blocks from GitHub's rendered HTML pages.
    GitHub patterns:
    - <td class="blob-code blob-code-inner">...</td>
    - <div class="highlight highlight-source-python">...</div>
    """
    code_blocks = []
    # Pattern for GitHub blob view
    pattern = r'<td class="blob-code blob-code-inner[^"]*">(.*?)</td>'
    matches = re.finditer(pattern, html_content, re.DOTALL)
    lines = []
    for match in matches:
        line = html.unescape(match.group(1))
        line = re.sub(r'<[^>]+>', '', line)
        lines.append(line)
    if lines:
        code = '\n'.join(lines)
        code_blocks.append({
            'code': code,
            'language': 'text',
            'type': 'github_blob',
            'context_before': '',
            'context_after': '',
            'full_context': code
        })
    return code_blocks


def extract_generic_html_code_blocks(html_content: str) -> List[Dict[str, Any]]:
    """
    Generic HTML code block extraction as fallback.
    Looks for:
    - <pre>...</pre>
    - <code>...</code>
    """
    code_blocks = []
    # Extract from <pre> tags
    pre_pattern = r'<pre[^>]*>(.*?)</pre>'
    matches = re.finditer(pre_pattern, html_content, re.DOTALL | re.IGNORECASE)
    for match in matches:
        code = html.unescape(match.group(1))
        code = re.sub(r'<[^>]+>', '', code)
        if code.strip() and len(code.strip()) > 10:
            code_blocks.append({
                'code': code.strip(),
                'language': 'text',
                'type': 'generic_pre',
                'context_before': '',
                'context_after': '',
                'full_context': code.strip()
            })
    return code_blocks


def extract_readthedocs_code_blocks(html_content: str, min_length: int = 3) -> List[Dict[str, Any]]:
    """
    Extract code blocks from ReadTheDocs/Sphinx documentation HTML without duplicates.
    ReadTheDocs typically uses nested structure:
    - <div class="highlight-{language} notranslate">
        <div class="highlight">
            <pre>...</pre>
        </div>
    </div>
    We extract each unique code block once, avoiding duplicates.
    Args:
        html_content: HTML content to parse
        min_length: Minimum length of code to consider (default: 10)
    Returns:
        List of unique code blocks with metadata
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    code_blocks = []
    # Find all <pre> tags and track which ones we've processed
    all_pres = soup.find_all('pre')
    # Process each pre tag once, using content hash to avoid duplicates
    seen_codes = set()  # Track code content to avoid duplicates
    for i, pre in enumerate(all_pres):
        code = pre.get_text().strip()
        # Debug: show first few chars of each pre
        preview = code[:50] + "..." if len(code) > 50 else code
        # Skip if too short or already seen
        if not code:
            continue
        if len(code) < min_length:
            continue
        if code in seen_codes:
            continue
        seen_codes.add(code)
        # Determine language by looking at parent divs
        language = 'text'
        parent = pre.parent
        while parent:
            if parent.name == 'div' and parent.get('class'):
                classes = parent.get('class', [])
                for cls in classes:
                    if isinstance(cls, str) and cls.startswith('highlight-') and cls != 'highlight':
                        language = cls.replace('highlight-', '')
                        break
                if language != 'text':
                    break
            parent = parent.parent
        if language == 'text':
            pass
        # Find the topmost highlight container for context
        highlight_container = pre
        temp = pre.parent
        container_depth = 0
        while temp:
            if temp.name == 'div' and temp.get('class'):
                if any('highlight' in str(c) for c in temp.get('class', [])):
                    highlight_container = temp
                    container_depth += 1
                    temp = temp.parent
                else:
                    break
            else:
                break
        # Get context from surrounding elements
        context_before = ""
        context_after = ""
        # Get previous sibling text (often contains description)
        prev = highlight_container.find_previous_sibling()
        if prev:
            # Get text, but limit length
            prev_text = prev.get_text().strip()
            if prev_text:
                context_before = prev_text[:500]
        # Get next sibling text
        next_elem = highlight_container.find_next_sibling()
        if next_elem:
            next_text = next_elem.get_text().strip()
            if next_text:
                context_after = next_text[:500]
        code_blocks.append({
            'code': code,
            'language': language,
            'type': 'code',
            'context_before': context_before,
            'context_after': context_after
        })
    # Also check for literal-block elements (another Sphinx pattern)
    literal_blocks = soup.find_all(class_='literal-block')
    for i, block in enumerate(literal_blocks):
        code = block.get_text().strip()
        preview = code[:50] + "..." if len(code) > 50 else code
        # Only add if not already seen and substantial
        if not code:
            continue
        if len(code) < min_length:
            continue
        if code in seen_codes:
            continue
        seen_codes.add(code)
        # Get context
        context_before = ""
        context_after = ""
        prev_elem = block.find_previous_sibling()
        if prev_elem:
            context_before = prev_elem.get_text().strip()[:500]
        next_elem = block.find_next_sibling()
        if next_elem:
            context_after = next_elem.get_text().strip()[:500]
        code_blocks.append({
            'code': code,
            'language': 'text',
            'type': 'literal-block',
            'context_before': context_before,
            'context_after': context_after
        })
    return code_blocks


def extract_code_blocks(content: str, min_length: int = 3, url: str = None) -> List[Dict[str, Any]]:
    """
    Universal code block extractor that handles multiple content formats.
    Automatically detects content type and applies the most appropriate extraction method:
    - Jupyter notebooks (JSON format, even from GitHub URLs)
    - HTML documentation (ReadTheDocs/Sphinx, MkDocs, GitHub, etc.)
    - Markdown files (fenced blocks, command examples, code boxes)
    - Raw code files (from GitHub raw URLs)
    - Plain text with code patterns
    Uses specialized extractors when available (e.g., ReadTheDocs) with automatic
    fallback to general extractors. Removes duplicates and adds sequential indexing.
    Args:
        content: The content to extract code blocks from
        min_length: Minimum length of code blocks to extract (default: 3 character)
        url: Optional URL to help identify content type
    Returns:
        List of dictionaries containing code blocks with:
        - 'code': The extracted code content
        - 'language': Detected programming language
        - 'type': Source type (e.g., 'raw_file', 'notebook_cell')
        - 'index': Sequential number of the block
    """
    code_blocks = []
    # Detect content type and source
    content_type, doc_system, has_code = detect_content_type_and_source(content, url)
    # print(f"🔍 Detected content type: {content_type}, doc system: {doc_system}, has code: {has_code}")
    # Handle based on content type
    if content_type == 'raw_code':
        # This is a raw code file (e.g., from GitHub raw URL)
        language = detect_language_from_url(url) if url else 'text'
        code_blocks.append({
            'code': content,
            'language': language,
            'type': 'raw_file',
            'context_before': f'Source: {url}' if url else '',
            'context_after': '',
            'full_context': content
        })
    elif content_type == 'jupyter':
        # Handle Jupyter notebook
        if doc_system == 'github':
            # Check if this is raw JSON content (from raw GitHub URL)
            if content.strip().startswith('{') and '"cells"' in content[:1000]:
                # print("🔍 Using Jupyter notebook JSON extractor for raw GitHub URL...")
                notebook_blocks = extract_jupyter_notebook_cells(content, min_length)
                code_blocks.extend(notebook_blocks)
            else:
                # GitHub-rendered Jupyter notebook HTML - fallback to markdown extraction
                # print("🔍 Using markdown extraction for GitHub Jupyter HTML...")
                markdown_blocks = extract_markdown_code_blocks(content, min_length)
                code_blocks.extend(markdown_blocks)
        else:
            # Standard Jupyter notebook JSON format
            notebook_blocks = extract_jupyter_notebook_cells(content, min_length)
            code_blocks.extend(notebook_blocks)
    elif content_type == 'html' and has_code:
        # Priority extraction based on doc_system
        if doc_system == 'sphinx':  # This includes ReadTheDocs
            # print("🔍 Using Sphinx/ReadTheDocs specific extractor...")
            specific_blocks = extract_readthedocs_code_blocks(content, min_length)
            if specific_blocks:
                code_blocks.extend(specific_blocks)
                # print(f"✅ Sphinx/ReadTheDocs extractor found {len(specific_blocks)} blocks")
            else:
                # Fallback to general HTML extraction
                # print("⚠️ Sphinx extractor found no blocks, falling back to general HTML...")
                html_blocks = extract_html_code_blocks(content, doc_system)
                code_blocks.extend(html_blocks)
        else:
            # General HTML extraction for other doc systems
            # print("🔍 Using general HTML extractor...")
            html_blocks = extract_html_code_blocks(content, doc_system)
            code_blocks.extend(html_blocks)
        # Final fallback: if still no blocks, try markdown extraction on HTML
        if not code_blocks:
            # print("🔍 No HTML code blocks found, trying markdown extraction as last resort...")
            markdown_blocks = extract_markdown_code_blocks(content, min_length)
            code_blocks.extend(markdown_blocks)
    elif content_type == 'markdown':
        # Extract markdown code blocks
        markdown_blocks = extract_markdown_code_blocks(content, min_length)
        code_blocks.extend(markdown_blocks)
        # Also extract command examples and code boxes
        command_blocks = extract_command_examples(content, min_length)
        filtered_command_blocks = [block for block in command_blocks if len(block['code']) < 5000]
        code_blocks.extend(filtered_command_blocks)
        codebox_blocks = extract_codebox_content(content, min_length)
        code_blocks.extend(codebox_blocks)
    else:
        # For plain text or unknown content, try all extraction methods
        # print("🔍 Unknown content type, trying all extraction methods...")
        # Try markdown extraction first
        markdown_blocks = extract_markdown_code_blocks(content, min_length)
        code_blocks.extend(markdown_blocks)
        # Try command extraction
        command_blocks = extract_command_examples(content, min_length)
        filtered_command_blocks = [block for block in command_blocks if len(block['code']) < 5000]
        code_blocks.extend(filtered_command_blocks)
        # Try codebox extraction
        codebox_blocks = extract_codebox_content(content, min_length)
        code_blocks.extend(codebox_blocks)
    # Add index to each block (no deduplication to preserve all code blocks)
    for i, block in enumerate(code_blocks):
        block['index'] = i + 1
    # print(f"🎯 Total code blocks extracted: {len(code_blocks)}")
    return code_blocks


def extract_jupyter_notebook_cells(markdown_content: str, min_length: int = 3) -> List[Dict[str, Any]]:
    """Extract code cells from Jupyter notebook JSON format"""
    import json
    code_blocks = []
    try:
        # Parse the JSON content
        notebook = json.loads(markdown_content)
        if 'cells' not in notebook:
            # print("No cells found in notebook")
            return code_blocks
        # Process each cell
        for i, cell in enumerate(notebook['cells']):
            cell_type = cell.get('cell_type', '')
            if cell_type == 'code':
                # Extract source code
                source = cell.get('source', [])
                if isinstance(source, list):
                    code_content = ''.join(source)
                else:
                    code_content = str(source)
                # Skip empty or very short code cells
                if len(code_content.strip()) < min_length:
                    continue
                # Get cell metadata
                metadata = cell.get('metadata', {})
                outputs = cell.get('outputs', [])
                # Extract context from surrounding cells
                context_before = ""
                context_after = ""
                # Get previous cell content (if any)
                if i > 0:
                    prev_cell = notebook['cells'][i-1]
                    prev_source = prev_cell.get('source', [])
                    if isinstance(prev_source, list):
                        context_before = ''.join(prev_source)[:500]
                    else:
                        context_before = str(prev_source)[:500]
                # Get next cell content (if any)
                if i < len(notebook['cells']) - 1:
                    next_cell = notebook['cells'][i+1]
                    next_source = next_cell.get('source', [])
                    if isinstance(next_source, list):
                        context_after = ''.join(next_source)[:500]
                    else:
                        context_after = str(next_source)[:500]
                code_blocks.append({
                    'code': code_content,
                    'language': 'python',
                    'type': 'jupyter_code_cell',
                    'cell_index': i,
                    'metadata': metadata,
                    'outputs': outputs,
                    'context_before': context_before,
                    'context_after': context_after,
                    'full_context': f"Cell {i}:\n{context_before}\n\n{code_content}\n\n{context_after}"
                })
            elif cell_type == 'markdown':
                # Extract markdown content for context
                source = cell.get('source', [])
                if isinstance(source, list):
                    markdown_content = ''.join(source)
                else:
                    markdown_content = str(source)
                # Look for code blocks within markdown cells
                if '```' in markdown_content:
                    markdown_blocks = extract_markdown_code_blocks(markdown_content, min_length)
                    for block in markdown_blocks:
                        block['cell_index'] = i
                        block['type'] = 'jupyter_markdown_code'
                        code_blocks.append(block)
    except json.JSONDecodeError as e:
        # print(f"Failed to parse Jupyter notebook JSON: {e}")
        pass
    except Exception as e:
        # print(f"Error processing Jupyter notebook: {e}")
        pass
    return code_blocks


def extract_smart_context_before(markdown_content: str, code_start_pos: int, max_chars: int = 1000) -> str:
    """
    Intelligently extract the most relevant context before a code block.
    This function looks for the most meaningful content preceding a code block:
    1. First tries to find the previous paragraph or heading
    2. If no paragraph found, looks for the previous section
    3. Falls back to a reasonable character limit if nothing else works
    Args:
        markdown_content: The full markdown content
        code_start_pos: Position where the code block starts
        max_chars: Maximum characters to extract (fallback limit)
    Returns:
        The most relevant context before the code block
    """
    if code_start_pos <= 0:
        return ""
    # Look backwards from the code block position
    search_start = max(0, code_start_pos - max_chars)
    search_content = markdown_content[search_start:code_start_pos]
    # Split into lines for analysis
    lines = search_content.split('\n')
    # Strategy 1: Find the most recent paragraph or heading
    relevant_lines = []
    for line in reversed(lines):
        line = line.strip()
        # Skip empty lines at the end
        if not line and not relevant_lines:
            continue
        # Stop if we hit a major section break
        if (line.startswith('#') or 
            line.startswith('---') or 
            line.startswith('===') or
            len(line) > 200):  # Very long lines are likely not relevant context
            break
        # Add this line to relevant context
        relevant_lines.insert(0, line)
        # Stop if we have enough context (2-3 lines is usually sufficient)
        if len(relevant_lines) >= 3:
            break
    # Join the relevant lines
    context = '\n'.join(relevant_lines).strip()
    # If we found meaningful context, return it
    if context and len(context) > 10:
        return context
    # Strategy 2: Fallback to character-based extraction with better boundaries
    # Look for natural paragraph breaks (double newlines)
    fallback_start = max(0, code_start_pos - max_chars)
    fallback_content = markdown_content[fallback_start:code_start_pos]
    # Find the last paragraph break
    last_break = fallback_content.rfind('\n\n')
    if last_break != -1:
        return fallback_content[last_break + 2:].strip()
    # Strategy 3: Final fallback - just take the last reasonable amount
    return fallback_content.strip()


def extract_smart_context_after(markdown_content: str, code_end_pos: int, max_chars: int = 1000) -> str:
    """
    Intelligently extract the most relevant context after a code block.
    This function looks for the most meaningful content following a code block:
    1. First tries to find the next paragraph or explanation
    2. If no paragraph found, looks for the next section
    3. Falls back to a reasonable character limit if nothing else works
    Args:
        markdown_content: The full markdown content
        code_end_pos: Position where the code block ends
        max_chars: Maximum characters to extract (fallback limit)
    Returns:
        The most relevant context after the code block
    """
    if code_end_pos >= len(markdown_content):
        return ""
    # Look forwards from the code block position
    search_end = min(len(markdown_content), code_end_pos + max_chars)
    search_content = markdown_content[code_end_pos:search_end]
    # Split into lines for analysis
    lines = search_content.split('\n')
    # Strategy 1: Find the next paragraph or heading
    relevant_lines = []
    for line in lines:
        line = line.strip()
        # Skip empty lines at the beginning
        if not line and not relevant_lines:
            continue
        # Stop if we hit a major section break
        if (line.startswith('#') or 
            line.startswith('---') or 
            line.startswith('===') or
            len(line) > 200):  # Very long lines are likely not relevant context
            break
        # Add this line to relevant context
        relevant_lines.append(line)
        # Stop if we have enough context (2-3 lines is usually sufficient)
        if len(relevant_lines) >= 3:
            break
    # Join the relevant lines
    context = '\n'.join(relevant_lines).strip()
    # If we found meaningful context, return it
    if context and len(context) > 10:
        return context
    # Strategy 2: Fallback to character-based extraction with better boundaries
    # Look for natural paragraph breaks (double newlines)
    fallback_end = min(len(markdown_content), code_end_pos + max_chars)
    fallback_content = markdown_content[code_end_pos:fallback_end]
    # Find the next paragraph break
    next_break = fallback_content.find('\n\n')
    if next_break != -1:
        return fallback_content[:next_break].strip()
    # Strategy 3: Final fallback - just take the next reasonable amount
    return fallback_content.strip()


def extract_markdown_code_blocks(markdown_content: str, min_length: int = 3) -> List[Dict[str, Any]]:
    """Extract markdown code blocks (```) with intelligent context extraction"""
    code_blocks = []
    # Skip if content starts with triple backticks (edge case for files wrapped in backticks)
    content = markdown_content.strip()
    start_offset = 0
    if content.startswith('```'):
        # Skip the first triple backticks
        start_offset = 3
        # print("Skipping initial triple backticks")
    # Find all occurrences of triple backticks
    backtick_positions = []
    pos = start_offset
    while True:
        pos = markdown_content.find('```', pos)
        if pos == -1:
            break
        backtick_positions.append(pos)
        pos += 3
    # Process pairs of backticks
    i = 0
    while i < len(backtick_positions) - 1:
        start_pos = backtick_positions[i]
        end_pos = backtick_positions[i + 1]
        # Extract the content between backticks
        code_section = markdown_content[start_pos+3:end_pos]
        # Check if there's a language specifier on the first line
        lines = code_section.split('\n', 1)
        if len(lines) > 1:
            # Check if first line is a language specifier (no spaces, common language names)
            first_line = lines[0].strip()
            if first_line and not ' ' in first_line and len(first_line) < 20:
                language = first_line
                code_content = lines[1].strip() if len(lines) > 1 else ""
            else:
                language = ""
                code_content = code_section.strip()
        else:
            language = ""
            code_content = code_section.strip()
        # Only skip if code block is extremely short (likely empty or just whitespace)
        if len(code_content.strip()) < min_length:
            i += 2  # Move to next pair
            continue
        # Use intelligent context extraction instead of fixed character count
        context_before = extract_smart_context_before(markdown_content, start_pos)
        context_after = extract_smart_context_after(markdown_content, end_pos + 3)
        code_blocks.append({
            'code': code_content,
            'language': language,
            'type': 'markdown_code_block',
            'context_before': context_before,
            'context_after': context_after,
            'full_context': f"{context_before}\n\n{code_content}\n\n{context_after}"
        })
        # Move to next pair (skip the closing backtick we just processed)
        i += 2
    return code_blocks


def extract_command_examples(markdown_content: str, min_length: int = 3) -> List[Dict[str, Any]]:
    """Extract command line examples"""
    command_blocks = []
    # Match command line patterns with better boundary detection
    # Look for lines starting with '>' followed by command and output
    pattern = r'>\s*(\w+.*?)\n((?:[^>].*\n?)*?)(?=\n>|\n\n|\n[A-Z][a-z]|\n#|\n##|\n###|\n####|\n#####|\n######|$)'
    matches = re.finditer(pattern, markdown_content, re.DOTALL)
    for match in matches:
        command = match.group(1).strip()
        output = match.group(2).strip()
        # Additional filtering: ensure output doesn't contain new command patterns
        # and doesn't extend too far into the document
        lines = output.split('\n')
        filtered_lines = []
        for line in lines:
            # Stop if we hit another command pattern or section header
            if (line.strip().startswith('>') or 
                line.strip().startswith('#') or
                re.match(r'^[A-Z][a-z].*:', line.strip()) or
                len(line.strip()) > 200):  # Very long lines are likely not command output
                break
            filtered_lines.append(line)
        output = '\n'.join(filtered_lines).strip()
        if len(output.strip()) >= min_length:
            # Use intelligent context extraction instead of fixed character count
            context_before = extract_smart_context_before(markdown_content, match.start())
            context_after = extract_smart_context_after(markdown_content, match.end())
            command_blocks.append({
                'code': f"{command}\n{output}",
                'language': 'shell',
                'type': 'command_example',
                'command': command,
                'output': output,
                'context_before': context_before,
                'context_after': context_after,
                'full_context': f"{context_before}\n\n{command}\n{output}\n\n{context_after}"
            })
    return command_blocks


def extract_codebox_content(markdown_content: str, min_length: int = 3) -> List[Dict[str, Any]]:
    """Extract content from code boxes and copyable blocks"""
    codebox_blocks = []
    # Common patterns for code boxes
    patterns = [
        r'Copy\s*\n(.*?)(?=\n\n|\n[A-Z]|\n#|\n##|\n###|\n####|\n#####|\n######|$)',
        r'```\s*copy\s*\n(.*?)\n```',
        r'<code[^>]*>(.*?)</code>',
        r'<pre[^>]*>(.*?)</pre>'
    ]
    for pattern in patterns:
        matches = re.finditer(pattern, markdown_content, re.DOTALL | re.IGNORECASE)
        for match in matches:
            code_content = match.group(1).strip()
            if len(code_content.strip()) >= min_length:
                # Use intelligent context extraction instead of fixed character count
                context_before = extract_smart_context_before(markdown_content, match.start())
                context_after = extract_smart_context_after(markdown_content, match.end())
                codebox_blocks.append({
                    'code': code_content,
                    'language': 'text',
                    'type': 'codebox',
                    'context_before': context_before,
                    'context_after': context_after,
                    'full_context': f"{context_before}\n\n{code_content}\n\n{context_after}"
                })
    return codebox_blocks


def generate_code_example_summary(code: str, context_before: str, context_after: str) -> str:
    """
    Generate a summary for a code example using its surrounding context.
    Args:
        code: The code example
        context_before: Context before the code
        context_after: Context after the code
    Returns:
        A summary of what the code example demonstrates
    """
    model_choice = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4.1-nano")
    # Create the prompt
    prompt = f"""<context_before>
{context_before[-1000:] if len(context_before) > 1000 else context_before}
</context_before>
<code_example>
{code[:3000] if len(code) > 3000 else code}
</code_example>
<context_after>
{context_after[:1000] if len(context_after) > 1000 else context_after}
</context_after>
Based on the code example and its surrounding context, provide a concise summary (2-3 sentences) that describes what this code example demonstrates and its purpose. Focus on the practical application and key concepts illustrated.
"""
#     prompt = f"""<context_before>
# {context_before}
# </context_before>
# <code_example>
# {code}
# </code_example>
# <context_after>
# {context_after}
# </context_after>
# Based on the code example and its surrounding context, provide a concise summary (2-3 sentences) that describes what this code example demonstrates and its purpose. Focus on the practical application and key concepts illustrated.
# """
    try:
        response = openai.chat.completions.create(
            model=model_choice,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that provides concise code example summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating code example summary: {e}")
        return "Code example for demonstration purposes."


async def search_code_blocks(
    client: Client, 
    query: str, 
    match_count: int = 10, 
    filter_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Search for relevant code blocks using semantic similarity.
    Args:
        client: Supabase client instance
        query: Search query
        match_count: Number of matches to return
        filter_metadata: Optional metadata filters (e.g., {"language": "python"})
    Returns:
        List of relevant code blocks with similarity scores
    """
    try:
        # Create embedding for the query
        query_embedding = await create_embedding(query)
        
        # Build the search query
        def _run_rpc():
            return client.rpc(
                'match_code_blocks',
                {
                    'query_embedding': query_embedding,
                    'match_count': match_count,
                    'filter_metadata': filter_metadata or {}
                }
            ).execute()
        result = await asyncio.to_thread(_run_rpc)
        if result.data:
            # Convert the results back to code block format
            code_blocks = []
            for record in result.data:
                code_block = {
                    "code": record["code_text"],
                    "summary": record["summary"],
                    "context_before": record["context_before"],
                    "context_after": record["context_after"],
                    "type": record["code_type"],
                    "language": record["language"],
                    "index": record["index"],
                    "source_url": record["url"],
                    "similarity_score": record.get("similarity", 0.0)
                }
                code_blocks.append(code_block)
            return code_blocks
        else:
            return []
    except Exception as e:
        print(f"Error searching code blocks: {e}")
        return []


async def check_extracted_code_exists(client: Client, url: str) -> bool:
    """
    Check if code has already been extracted from a given URL.
    Args:
        client: Supabase client instance
        url: URL to check
    Returns:
        True if code exists for this URL, False otherwise
    """
    try:
        def _run():
            return client.table("extracted_code").select("url").eq("url", url).limit(1).execute()
        result = await asyncio.to_thread(_run)
        return len(result.data) > 0
    except Exception as e:
        print(f"Error checking extracted code existence: {e}")
        return False


def _format_embedding_for_vector_column(embedding: List[float]) -> str:
    """
    Convert a Python list of floats to PostgreSQL vector format.
    
    Args:
        embedding: List of float values
        
    Returns:
        String in PostgreSQL vector format: [1.0,2.0,3.0]
    """
    return '[' + ','.join(map(str, embedding)) + ']'


async def save_extracted_code_to_supabase(
    client: Client,
    url: str,
    extracted_code: List[Dict[str, Any]],
    total_code_blocks_found: int,
    extraction_method: str = "single_page"
) -> bool:
    """
    Save extracted code blocks to Supabase with batch operations.
    Args:
        client: Supabase client instance
        url: Source URL of the code
        extracted_code: List of extracted code blocks
        total_code_blocks_found: Total number of code blocks found
        extraction_method: Method used for extraction
    Returns:
        Boolean indicating success
    """
    try:
        if not extracted_code:
            # print(f"No code blocks to save for {url}")
            return True
        # Prepare embedding texts for all code blocks
        embedding_texts = []
        for code_block in extracted_code:
            code_text = code_block.get('code', '')
            summary = code_block.get('summary', '')
            context_before = code_block.get('context_before', '')
            context_after = code_block.get('context_after', '')
            # Combine relevant text for embedding
            embedding_text = f"Code: {code_text}\nSummary: {summary}\nContext: {context_before} {context_after}"
            embedding_texts.append(embedding_text)
        # print(f"Creating embeddings for {len(embedding_texts)} code blocks...")
        # Generate embeddings in batch
        embeddings = await create_embeddings_batch(embedding_texts)
        # Prepare batch data for insertion
        batch_data = []
        for i, code_block in enumerate(extracted_code):
            # Generate summary if enabled
            summary = ""
            if os.getenv("GENERATE_CODE_SUMMARY", "false").lower() == "true":
                summary = generate_code_example_summary(
                    code_block.get('code', ''),
                    code_block.get('context_before', ''),
                    code_block.get('context_after', '')
                )
            # Convert embedding to proper PostgreSQL vector format
            embedding = embeddings[i] if i < len(embeddings) else [0.0] * 1536
            data = {
                "url": url,
                "code_text": code_block.get('code', ''),
                "summary": summary or code_block.get('summary', ''),
                "context_before": code_block.get('context_before', ''),
                "context_after": code_block.get('context_after', ''),
                "code_type": code_block.get('type', ''),
                "language": code_block.get('language', ''),
                "index": code_block.get('index', 0),
                "extraction_method": extraction_method,
                "embedding": _format_embedding_for_vector_column(embedding)
            }
            batch_data.append(data)
        # Batch insert to Supabase with conflict resolution
        # print(f"Inserting {len(batch_data)} code blocks to database...")
        def _insert_batch():
            return client.table("extracted_code").upsert(batch_data, on_conflict="url,index").execute()
        result = await asyncio.to_thread(_insert_batch)
        if result.data:
            # print(f"✅ Successfully saved {len(result.data)}/{total_code_blocks_found} code blocks for {url}")
            return True
        else:
            # print(f"❌ Failed to save code blocks for {url}")
            return False
    except Exception as e:
        print(f"Error saving extracted code to Supabase: {e}")
        # Fallback to individual insertion if batch fails
        try:
            print("Attempting fallback to individual insertion...")
            success_count = 0
            for i, code_block in enumerate(extracted_code):
                try:
                    # Generate embedding for this specific block
                    embedding_text = f"Code: {code_block.get('code', '')}\nContext: {code_block.get('context_before', '')} {code_block.get('context_after', '')}"
                    embedding = await create_embedding(embedding_text)
                    data = {
                        "url": url,
                        "code_text": code_block.get('code', ''),
                        "summary": code_block.get('summary', ''),
                        "context_before": code_block.get('context_before', ''),
                        "context_after": code_block.get('context_after', ''),
                        "code_type": code_block.get('type', ''),
                        "language": code_block.get('language', ''),
                        "index": code_block.get('index', 0),
                        "extraction_method": extraction_method,
                        "embedding": _format_embedding_for_vector_column(embedding)
                    }
                    def _insert_one():
                        return client.table("extracted_code").upsert(data, on_conflict="url,index").execute()
                    result = await asyncio.to_thread(_insert_one)
                    if result.data:
                        success_count += 1
                except Exception as individual_error:
                    print(f"Failed to insert code block {i}: {individual_error}")
                    continue
            print(f"✅ Fallback saved {success_count}/{len(extracted_code)} code blocks")
            return success_count > 0
        except Exception as fallback_error:
            print(f"Fallback insertion also failed: {fallback_error}")
            return False


async def get_extracted_code_from_supabase(client: Client, url: str) -> Optional[List[Dict[str, Any]]]:
    """
    Retrieve extracted code from Supabase for a given URL.
    Args:
        client: Supabase client instance
        url: URL to retrieve code for
    Returns:
        List of code blocks, or None if not found
    """
    try:
        def _run():
            return client.table("extracted_code").select("*").eq("url", url).order("index").execute()
        result = await asyncio.to_thread(_run)
        if result.data and len(result.data) > 0:
            # Convert each record back to the original code block format
            code_blocks = []
            for record in result.data:
                code_block = {
                    "code": record["code_text"],
                    "summary": record["summary"],
                    "context_before": record["context_before"],
                    "context_after": record["context_after"],
                    "type": record["code_type"],
                    "language": record["language"],
                    "index": record["index"],
                    "source_url": record["url"]
                }
                code_blocks.append(code_block)
            return code_blocks
        else:
            return None
    except Exception as e:
        print(f"Error retrieving extracted code from Supabase: {e}")
        return None


async def clear_extracted_code_table(client: Client) -> bool:
    """
    Clear all records from the extracted_code table.
    Args:
        client: Supabase client instance
    Returns:
        True if successful, False otherwise
    """
    try:
        # First, get the count of records before deletion
        def _count():
            return client.table("extracted_code").select("id", count="exact").execute()
        count_result = await asyncio.to_thread(_count)
        count = count_result.count if count_result.count is not None else 0
        # Delete all records
        def _delete():
            return client.table("extracted_code").delete().neq("id", 0).execute()
        result = await asyncio.to_thread(_delete)
        print(f"   ✅ Cleared {count} records from extracted_code table")
        return True
    except Exception as e:
        print(f"   ❌ Error clearing extracted_code table: {e}")
        return False
