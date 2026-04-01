#!/usr/bin/env python3
"""
Test for extract_code_from_url MCP tool to extract code from web URLs.
"""
import asyncio
import json
import subprocess
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def get_server_params() -> StdioServerParameters:
    # Provide minimal env to allow server startup
    import os
    return StdioServerParameters(
        command="python3",
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
            "GENERATE_CODE_SUMMARY": "false",
            "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "dummy"),
            "MCP_QUIET": "0",  # Changed to 0 for more verbose output
            "NODE_ENV": "development",  # Changed to development for more debug info
            "TRANSPORT": "stdio"  # Use stdio transport for MCP client
        }
    )


async def clear_supabase_tables(session):
    """Clear extracted_code table in Supabase before testing"""
    print("\n🧹 Clearing extracted_code table in Supabase...")
    
    try:
        # Import the supabase utils to clear tables directly
        import sys
        import os
        from pathlib import Path
        
        # Add the utils directory to Python path
        current_dir = Path(__file__).parent
        utils_path = current_dir.parent.parent / "utils"  # Go up to CASCADE root, then into utils
        sys.path.insert(0, str(utils_path))
        
        from supabase_utils import clear_supabase_tables as clear_tables
        
        # Get Supabase client
        import os
        from supabase import create_client
        
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        
        if url and key:
            supabase_client = create_client(url, key)
            clear_tables(supabase_client)
            print("✅ Successfully cleared extracted_code table")
        else:
            print("⚠️ Missing Supabase credentials (continuing without clearing)")
            
    except Exception as e:
        print(f"⚠️ Clear tables skipped: {e}")


async def test_retrieve_extracted_code(session, query: str, description: str):
    """Test retrieve_extracted_code MCP tool with a query"""
    print(f"\n{'='*60}")
    print(f"🔍 Testing Retrieve Extracted Code: {description}")
    print(f"🔍 Query: {query}")
    print(f"{'='*60}")
    
    try:
        # Call the MCP tool with a query
        print("\n📤 Calling retrieve_extracted_code MCP tool...")
        result = await session.call_tool("retrieve_extracted_code", {
            "query": query
        })
        
        if result.content:
            text = result.content[0].text
            print("\n📥 MCP tool response received")
            
            # Parse JSON response
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                print(f"\n❌ JSON Parse Error: {e}")
                print("\n📄 Raw response text:")
                print("-"*40)
                print(text[:1000])  # Print first 1000 chars
                print("-"*40)
                return
            
            # Print retrieval results
            print("\n📊 Retrieval Results:")
            print("-"*40)
            
            # Basic info
            success = data.get('success', False)
            error = data.get('error', '')
            
            print(f"✓ Success: {success}")
            
            if not success:
                print(f"✗ Error: {error}")
                return
            
            # Successful retrieval info
            print(f"✓ Query: {data.get('query', query)}")
            
            # Print retrieved code blocks
            if data.get('results'):
                results = data['results']
                print(f"\n📦 Retrieved {len(results)} code blocks:")
                print("="*60)
                
                for i, result_item in enumerate(results):
                    print(f"\n{'='*60}")
                    print(f"📌 Result #{i+1}/{len(results)}")
                    print(f"{'='*60}")
                    
                    # Print result details
                    print(f"✓ Source URL: {result_item.get('source_url', 'unknown')}")
                    print(f"✓ Language: {result_item.get('language', 'unknown')}")
                    print(f"✓ Type: {result_item.get('type', 'unknown')}")
                    print(f"✓ Similarity Score: {result_item.get('similarity_score', 'N/A')}")
                    print(f"✓ Code Length: {len(result_item.get('code', ''))} chars")
                    
                    # Print the code content
                    code_content = result_item.get('code', '')
                    if code_content:
                        print(f"\n📝 Code Content:")
                        print("-"*40)
                        print(code_content[:500])  # Show first 500 chars
                        if len(code_content) > 500:
                            print("...")
                        print("-"*40)
                    
                    # Print context if available
                    context_before = result_item.get('context_before', '')
                    context_after = result_item.get('context_after', '')
                    if context_before or context_after:
                        print(f"\n📋 Context:")
                        if context_before:
                            print(f"Before: {context_before[:200]}...")
                        if context_after:
                            print(f"After: {context_after[:200]}...")
                
                print(f"\n{'='*60}")
                print(f"✅ Total results retrieved: {len(results)}")
                
                # Summary statistics
                total_chars = sum(len(result_item.get('code', '')) for result_item in results)
                languages = {}
                for result_item in results:
                    lang = result_item.get('language', 'unknown')
                    languages[lang] = languages.get(lang, 0) + 1
                
                print(f"\n📊 Retrieval Statistics:")
                print(f"  • Total code characters: {total_chars:,}")
                print(f"  • Language distribution:")
                for lang, count in sorted(languages.items(), key=lambda x: x[1], reverse=True):
                    print(f"    - {lang}: {count} results")
                
            else:
                print("\n⚠️ No results found for the query")
            
            # Save complete response to file for detailed inspection
            output_file = f"code_retrieval_{description.replace(' ', '_').replace('-', '_')}.json"
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Full results saved to: {output_file}")
            
            print("\n" + "="*60)
            
        else:
            print("❌ No content returned from MCP tool")
            
    except Exception as e:
        print(f"\n❌ MCP tool call failed with exception:")
        print(f"  Type: {type(e).__name__}")
        print(f"  Message: {str(e)}")
        
        # Print full traceback
        import traceback
        print("\n📋 Full Traceback:")
        print("-"*40)
        traceback.print_exc()
        print("-"*40)


async def test_single_url_debug(session, url: str, description: str):
    """Test extract_code_from_url MCP tool with a single URL for debugging"""
    print(f"\n{'='*60}")
    print(f"🧪 Testing Single URL: {description}")
    print(f"🔗 URL: {url}")
    print(f"{'='*60}")
    
    try:
        # Call the MCP tool with a single URL
        print("\n📤 Calling MCP tool with single URL...")
        result = await session.call_tool("extract_code_from_url", {
            "url": url
        })
        
        if result.content:
            text = result.content[0].text
            print("\n📥 MCP tool response received")
            
            # Parse JSON response
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                print(f"\n❌ JSON Parse Error: {e}")
                print("\n📄 Raw response text:")
                print("-"*40)
                print(text[:1000])  # Print first 1000 chars
                print("-"*40)
                return
            
            # Print extraction results
            print("\n📊 Extraction Results:")
            print("-"*40)
            
            # Basic info
            success = data.get('success', False)
            error = data.get('error', '')
            
            print(f"✓ Success: {success}")
            
            if not success:
                print(f"✗ Error: {error}")
                print(f"✗ Error Type: {data.get('error_type', 'unknown')}")
                
                # Print any additional error context
                if 'traceback' in data:
                    print("\n📋 Traceback:")
                    print(data['traceback'])
                    
                # Check if it's a cache result
                if data.get('cached'):
                    print("📦 This was a cached result")
                    
                return
            
            # Successful extraction info
            print(f"✓ Crawl Method: {data.get('crawl_method', 'unknown')}")
            print(f"✓ Extraction Method: {data.get('extraction_method', 'unknown')}")
            print(f"✓ Doc System: {data.get('doc_system', 'unknown')}")
            print(f"✓ Content Length: {data.get('content_length', 0):,} chars")
            print(f"✓ Code Blocks Found: {data.get('code_blocks_found', 0)}")
            print(f"✓ Cached: {data.get('cached', False)}")
            
            # Print complete JSON for each code block
            if data.get('extracted_code'):
                code_blocks = data['extracted_code']
                print(f"\n📦 Complete JSON for all {len(code_blocks)} code blocks:")
                print("="*60)
                
                for i, block in enumerate(code_blocks):
                    print(f"\n{'='*60}")
                    print(f"📌 Code Block #{i+1}/{len(code_blocks)}")
                    print(f"{'='*60}")
                    
                    # Print the complete JSON for this block with nice formatting
                    print(json.dumps(block, indent=2, ensure_ascii=False))
                
                print(f"\n{'='*60}")
                print(f"✅ Total blocks extracted: {len(code_blocks)}")
                
                # Summary statistics
                total_chars = sum(len(block.get('code', '')) for block in code_blocks)
                total_lines = sum(len(block.get('code', '').split('\n')) for block in code_blocks)
                languages = {}
                for block in code_blocks:
                    lang = block.get('language', 'unknown')
                    languages[lang] = languages.get(lang, 0) + 1
                
                print(f"\n📊 Overall Statistics:")
                print(f"  • Total code characters: {total_chars:,}")
                print(f"  • Total code lines: {total_lines:,}")
                print(f"  • Language distribution:")
                for lang, count in sorted(languages.items(), key=lambda x: x[1], reverse=True):
                    print(f"    - {lang}: {count} blocks")
                
            else:
                print("\n⚠️ No code blocks extracted")
                if 'message' in data:
                    print(f"  Message: {data['message']}")
            
            # Save complete response to file for detailed inspection
            output_file = f"code_extraction_single_{description.replace(' ', '_').replace('-', '_')}.json"
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Full results saved to: {output_file}")
            
            # Also save just the code blocks for easier access
            if data.get('extracted_code'):
                blocks_file = f"code_blocks_single_{description.replace(' ', '_').replace('-', '_')}.json"
                with open(blocks_file, 'w') as f:
                    json.dump(data['extracted_code'], f, indent=2, ensure_ascii=False)
                print(f"💾 Code blocks only saved to: {blocks_file}")
            
            print("\n" + "="*60)
            
        else:
            print("❌ No content returned from MCP tool")
            
    except Exception as e:
        print(f"\n❌ MCP tool call failed with exception:")
        print(f"  Type: {type(e).__name__}")
        print(f"  Message: {str(e)}")
        
        # Print full traceback
        import traceback
        print("\n📋 Full Traceback:")
        print("-"*40)
        traceback.print_exc()
        print("-"*40)


async def test_url_list_debug(session, urls: list, description: str):
    """Test extract_code_from_url MCP tool with a list of URLs for debugging"""
    print(f"\n{'='*60}")
    print(f"🧪 Testing URL List: {description}")
    print(f"🔗 URLs: {len(urls)} URLs")
    for i, url in enumerate(urls, 1):
        print(f"  {i}. {url}")
    print(f"{'='*60}")
    
    try:
        # Call the MCP tool with a list of URLs
        print("\n📤 Calling MCP tool with URL list...")
        result = await session.call_tool("extract_code_from_url", {
            "urls": urls
        })
        
        if result.content:
            text = result.content[0].text
            print("\n📥 MCP tool response received")
            
            # Parse JSON response
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                print(f"\n❌ JSON Parse Error: {e}")
                print("\n📄 Raw response text:")
                print("-"*40)
                print(text[:1000])  # Print first 1000 chars
                print("-"*40)
                return
            
            # Print extraction results
            print("\n📊 Extraction Results:")
            print("-"*40)
            
            # Check if this is a URL list response (multiple URLs)
            if 'per_url_results' in data:
                print(f"✓ Processing URL list response with {len(data['per_url_results'])} URLs")
                
                total_blocks = 0
                successful_urls = 0
                per_url_results = data['per_url_results']
                
                for i, url_result in enumerate(per_url_results):
                    print(f"\n{'='*40}")
                    print(f"📌 URL Result #{i+1}/{len(per_url_results)}")
                    print(f"{'='*40}")
                    
                    success = url_result.get('success', False)
                    url = url_result.get('url', f'URL_{i+1}')
                    code_blocks_found = url_result.get('code_blocks_found', 0)
                    
                    print(f"✓ URL: {url}")
                    print(f"✓ Success: {success}")
                    print(f"✓ Code Blocks Found: {code_blocks_found}")
                    
                    if success:
                        successful_urls += 1
                        total_blocks += code_blocks_found
                        
                        # Print extraction method info
                        print(f"✓ Crawl Method: {url_result.get('crawl_method', 'unknown')}")
                        print(f"✓ Extraction Method: {url_result.get('extraction_method', 'unknown')}")
                        print(f"✓ Doc System: {url_result.get('doc_system', 'unknown')}")
                        print(f"✓ Cached: {url_result.get('cached', False)}")
                        
                        # Show first few code blocks
                        if url_result.get('extracted_code'):
                            code_blocks = url_result['extracted_code']
                            print(f"\n📦 First 3 code blocks (out of {len(code_blocks)}):")
                            
                            for j, block in enumerate(code_blocks[:3]):
                                print(f"\n  📌 Block {j+1}:")
                                print(f"    Language: {block.get('language', 'unknown')}")
                                print(f"    Type: {block.get('type', 'unknown')}")
                                print(f"    Length: {len(block.get('code', ''))} chars")
                                print(f"    Preview: {block.get('code', '')[:100]}...")
                    else:
                        error = url_result.get('error', 'Unknown error')
                        print(f"✗ Error: {error}")
                
                # Print overall summary
                summary = data.get('summary', {})
                print(f"\n{'='*60}")
                print(f"📊 Overall Summary:")
                print(f"  • Total URLs processed: {summary.get('total_unique_urls', len(per_url_results))}")
                print(f"  • Successful extractions: {successful_urls}")
                print(f"  • Total code blocks extracted: {data.get('total_code_blocks_found', total_blocks)}")
                print(f"  • Cached URLs: {summary.get('cached_urls', 0)}")
                print(f"  • Newly extracted URLs: {summary.get('newly_extracted_urls', 0)}")
                print(f"  • Success rate: {successful_urls/len(per_url_results)*100:.1f}%")
                
            else:
                # Single URL result
                print("✓ Processing single URL result")
                success = data.get('success', False)
                print(f"✓ Success: {success}")
                
                if success:
                    code_blocks = data.get('extracted_code', [])
                    print(f"✓ Code Blocks Found: {len(code_blocks)}")
                    print(f"✓ Crawl Method: {data.get('crawl_method', 'unknown')}")
                    print(f"✓ Extraction Method: {data.get('extraction_method', 'unknown')}")
                    print(f"✓ Doc System: {data.get('doc_system', 'unknown')}")
                    print(f"✓ Cached: {data.get('cached', False)}")
                else:
                    error = data.get('error', 'Unknown error')
                    print(f"✗ Error: {error}")
            
            # Save complete response to file for detailed inspection
            output_file = f"code_extraction_list_{description.replace(' ', '_').replace('-', '_')}.json"
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Full results saved to: {output_file}")
            
            print("\n" + "="*60)
            
        else:
            print("❌ No content returned from MCP tool")
            
    except Exception as e:
        print(f"\n❌ MCP tool call failed with exception:")
        print(f"  Type: {type(e).__name__}")
        print(f"  Message: {str(e)}")
        
        # Print full traceback
        import traceback
        print("\n📋 Full Traceback:")
        print("-"*40)
        traceback.print_exc()
        print("-"*40)


async def test_extract_code_debug():
    """Test extract_code_from_url MCP tool with debug output"""
    print("\n🚀 Starting extract_code_from_url MCP tool test...")
    
    # Test URLs
    test_urls = [
        "https://xtb-docs.readthedocs.io/en/latest/hessian.html"
    ]
    
    server_params = get_server_params()
    
    print("\n📡 Starting MCP server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            print("✅ MCP session initialized")
            await session.initialize()

            # Clear tables first
            await clear_supabase_tables(session)
            
            # Test 1: Extract code from URL
            await test_url_list_debug(session, [test_urls[0]], "")
            # await test_url_list_debug(session, test_urls, "XTB + ... Combined")
           
            # Test 2: Retrieve extracted code with query
            await test_retrieve_extracted_code(session, "single point hessian", "XTB SPH Query")
            
            print("\n" + "="*60)
            print("✅ All tests completed")
            print("="*60)


async def main() -> None:
    print("=" * 60)
    print("🔬 Extract Code from URL and Retrieve - Debug Test")
    print("=" * 60)
    
    try:
        await test_extract_code_debug()
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())