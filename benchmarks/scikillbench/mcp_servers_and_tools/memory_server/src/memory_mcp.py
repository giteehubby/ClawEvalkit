"""
Memory Tools for Conversational System (MCP Server Version)
Provides the same functionality as direct memory_tools but as an MCP server.

Graph Memory:
- Enabled by default (extracts entities and relationships from conversations)
- Set ENABLE_GRAPH_MEMORY=false to disable and use only vector-based memory
- Requires Neo4j database with NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD for graph memory
"""

# Suppress noisy logging from external libraries
import logging
import sys
logging.basicConfig(level=logging.WARNING)
for logger_name in ["httpx", "openai", "mcp", "supabase", "neo4j", "mem0", "vecs", "numexpr"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# Create logger for this module (outputs to stderr, won't interfere with MCP stdio)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:  # Prevent duplicate handlers on reload
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter('[%(name)s] %(message)s'))
    logger.addHandler(_handler)

from mcp.server.fastmcp import FastMCP, Context
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
import os

# Load environment variables from the project root .env file
# Priority: .env file > shell environment (.bashrc) > code defaults
project_root = Path(__file__).resolve().parent.parent
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path, override=True)

# Also try loading from parent directory (workspace root)
workspace_root = project_root.parent
workspace_dotenv = workspace_root / '.env'
if workspace_dotenv.exists():
    load_dotenv(workspace_dotenv, override=True)

# ============================================================================
# CUSTOM MEMORY PROMPTS (same as conversational_system/config/custom_memory_prompts.py)
# ============================================================================

MATERIALS_SCIENCE_EXTRACTION_PROMPT = f"""You are a Materials Science and Chemistry Research Assistant specialized in accurately storing user preferences, technical solutions, API usage patterns, code implementation details, and scientific knowledge. Your role is to extract relevant information from conversations and organize them into distinct, manageable facts for easy retrieval when solving similar problems in the future.

EXTRACTION PURPOSE: The extracted facts will be used to help solve similar problems in the future. Therefore, focus on actionable implementation details that enable problem-solving, not just descriptions of what was asked.

IMPORTANT:
- For user preferences and configuration: Extract preferences about tools, databases, workflows
- For technical solutions: Extract HOW to implement solutions (methods, functions, parameters, patterns), NOT descriptions of what the user asked
- Every fact should help answer "How do I solve a similar problem?" not just "What did the user ask?"

Types of Information to Remember:

1. Personal Preferences and Configuration:
   - Preferred databases (Materials Project, AFLOW, OQMD, etc.)
   - API key locations and access methods (e.g., os.getenv('MP_API_KEY'))
   - Favorite tools and libraries for a specific task (pymatgen, ASE, VASP, etc.)
   - Research focus areas and materials of interest

2. Technical Implementation Details:
   - Specific API methods and functions
   - Function calls and their parameters
   - Data retrieval patterns and workflows
   - Field names and object attributes accessed
   - Computational methods and their parameters
   - Code patterns that successfully solved problems

3. Scientific Knowledge:
   - Material properties and characteristics
   - Crystal structures and space groups
   - Computational methods and techniques
   - Analysis procedures and best practices

4. API and Library Usage:
   - Specific methods and their purposes
   - Required parameters and field names
   - Object attributes and how to access them
   - Common usage patterns
   - Library versions and compatibility notes

5. Project Context:
   - Research goals and objectives
   - Current projects and their requirements
   - Collaboration details and data sources
   - Important dates and milestones

6. Other Information:
   - Common errors and troubleshooting solutions
   - Performance tips and optimizations
   - Any other technical details that help solve similar problems

Few-Shot Examples:

Input: Hi.
Output: {{"facts": []}}

Input: I prefer using the Materials Project API for crystal structure data.
Output: {{"facts": ["Prefers Materials Project API for crystal structure data"]}}

Input: My MP API key is stored in the MP_API_KEY environment variable.
Output: {{"facts": ["MP API key is accessed via os.getenv('MP_API_KEY')"]}}

Input: User asked: How to get formation energy? Solution: Use MPRester and call mpr.materials.summary.search() with fields=['formation_energy_per_atom'], then access via docs[0].formation_energy_per_atom.
Output: {{"facts": ["Use mpr.materials.summary.search() to retrieve formation energy", "Pass fields=['formation_energy_per_atom'] to materials.summary.search()", "Access formation energy via docs[0].formation_energy_per_atom"]}}

Input: I'm working with Silicon for my semiconductor research and prefer pymatgen for structure analysis.
Output: {{"facts": ["Works with Silicon for research", "Research focus is semiconductors", "Prefers pymatgen for structure analysis"]}}

Return the facts in JSON format as shown above.

Guidelines:
- Today's date is {datetime.now().strftime("%Y-%m-%d")}.
- Purpose: Extract information that helps solve similar problems in the future.
- For user preferences: Extract preferences about tools, databases, materials, workflows.
- For technical solutions: Extract implementation details - specific methods, functions, parameters, code patterns.
- When code/solutions are provided, extract HOW it works: API methods, function calls, parameters, field access patterns.
- Focus on actionable technical information that enables solving similar problems.
- If no relevant information is found, return an empty list for the "facts" key.
- Detect the language of user input and record facts in the same language. Normally, the user input is in English.
- The response must be valid JSON with a "facts" key containing a list of strings.

Following is a conversation between the user and the assistant. Extract relevant facts about user preferences, API keys, technical implementation details, API methods, code patterns, and scientific knowledge from the conversation and return them in JSON format as shown above.
"""

# Graph Memory Custom Prompt (for entity and relationship extraction)
MATERIALS_SCIENCE_GRAPH_PROMPT = """Focus on extracting technical implementation details and relationships in materials science code and research context. The purpose is to help solve similar problems in the future by capturing HOW solutions are implemented.

IMPORTANT:
- Extract specific API methods, function calls, and technical components from code
- Focus on implementation details that show how to solve problems, not just what was asked
- Capture relationships between methods, parameters, and data fields

Example Entity Types (adapt based on actual content):
   - Materials: Chemical elements, compounds, alloys, material IDs
   - Properties: Material properties
   - Tools/Libraries: Software and libraries
   - API Methods: Specific API methods and functions
   - Functions: Function calls and methods
   - Parameters: Function parameters and field names
   - Data Fields: Object attributes and accessed fields
   - Databases: Data sources (Materials Project, AFLOW, OQMD, etc.)
   - API Keys: Configuration methods
   - Units: Measurement units

Relationship Guidelines:
   - Extract relationships that help solve similar problems: both user preferences AND technical implementation
   - For user preferences: Capture tool preferences, database choices, workflow patterns (e.g., "user → prefers → Materials_Project")
   - For technical implementation: Show HOW code works through method calls, parameter passing, field access
   - Prefer specific technical relationships (e.g., "calls_method" over generic "uses")
   - Include relationships between methods and the data they retrieve
   - Include relationships between parameters and functions that accept them
   - Focus on actionable relationships that enable future problem-solving
"""

# ============================================================================
# MEMORY CONFIGURATION
# ============================================================================
# MEM0_USE_LLM: Whether to use LLM for intelligent memory extraction (default: true)
#   - true: LLM extracts key facts + saves original content (two saves)
#   - false: Only saves original content directly (one save, no LLM needed)
#
# MEM0_LLM_MODEL: Which model to use for memory extraction (default: gpt-4o-mini)
#
# ENABLE_GRAPH_MEMORY: Whether to use Neo4j graph for entity relationships (default: true)
# ============================================================================

MEM0_USE_LLM = os.getenv('MEM0_USE_LLM', 'true').lower() == 'true'
MEM0_LLM_MODEL = os.getenv('MEM0_LLM_MODEL', 'gpt-4o-mini')
ENABLE_GRAPH_MEMORY = os.getenv('ENABLE_GRAPH_MEMORY', 'true').lower() == 'true'


# Memory Server Context
@dataclass
class MemoryContext:
    """Manages mem0 instance for memory operations."""
    mem0: Any
    enable_graph: bool
    use_llm: bool


@asynccontextmanager
async def memory_lifespan(server: FastMCP) -> AsyncIterator[MemoryContext]:
    """Initialize and manage the mem0 memory instance."""
    from mem0 import Memory

    # Build configuration (same as memory_tools.py)
    config_dict = {
        "vector_store": {
            "provider": "supabase",
            "config": {
                "connection_string": os.getenv('SUPABASE_DATABASE_URL'),
                "collection_name": "conversational_memories"
            }
        },
    }

    # Add LLM config only if enabled
    if MEM0_USE_LLM:
        config_dict["llm"] = {
            "provider": "openai",
            "config": {
                "model": MEM0_LLM_MODEL
            }
        }
        config_dict["custom_fact_extraction_prompt"] = MATERIALS_SCIENCE_EXTRACTION_PROMPT
        logger.info(f"Memory LLM ENABLED - Using {MEM0_LLM_MODEL} for intelligent extraction")
    else:
        logger.info("Memory LLM DISABLED - Direct storage only (no extraction)")

    # Add graph store if enabled
    if ENABLE_GRAPH_MEMORY:
        config_dict["graph_store"] = {
            "provider": "neo4j",
            "config": {
                "url": os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
                "username": os.getenv('NEO4J_USER', 'neo4j'),
                "password": os.getenv('NEO4J_PASSWORD', 'password')
            },
            "custom_prompt": MATERIALS_SCIENCE_GRAPH_PROMPT
        }
        logger.info("Graph memory ENABLED - Entity relationships will be tracked")
    else:
        logger.info("Graph memory DISABLED - Using vector-based memory only")

    # Create mem0 instance
    mem0_instance = Memory.from_config(config_dict)

    try:
        yield MemoryContext(
            mem0=mem0_instance,
            enable_graph=ENABLE_GRAPH_MEMORY,
            use_llm=MEM0_USE_LLM
        )
    finally:
        logger.info("Memory Server shutting down...")


# Memory Server - FastMCP Application
mcp = FastMCP(
    "mcp_servers_and_tools/memory_server",
    lifespan=memory_lifespan,
    host=os.getenv("HOST", "127.0.0.1"),
    port=int(os.getenv("PORT", "8053"))
)


@mcp.tool()
async def search_memory(ctx: Context, query: str, user_id: str) -> str:
    """
    Search through stored memories

    Returns relevant memories that may help solve the current problem
    Use this to retrieve user preferences, API keys, similar problems, solutions, or relevant experience from past memories

    Args:
        ctx: MCP context
        query: What to search for
        user_id: User identifier extracted from message

    Returns:
        Formatted string with relevant memories (from vector store) and entity relationships (from graph store)
    """
    try:
        mem0 = ctx.request_context.lifespan_context.mem0
        enable_graph = ctx.request_context.lifespan_context.enable_graph

        search_result = mem0.search(query, user_id=user_id, limit=5)

        output_parts = []

        # Add vector store results
        if search_result and search_result.get('results'):
            vector_results = search_result['results']
            output_parts.append("Relevant memories:")
            for mem in vector_results:
                output_parts.append(f"- {mem['memory']}")

        # Add graph store results (entity relationships)
        if enable_graph and search_result and search_result.get('relations'):
            relations = search_result['relations'][:5]  # Limit to top 5 relations
            if relations:
                output_parts.append("\nRelated entity relationships:")
                for rel in relations:
                    source = rel.get('source', 'unknown')
                    relationship = rel.get('relationship', 'relates_to')
                    destination = rel.get('destination', 'unknown')
                    output_parts.append(f"- {source} → {relationship} → {destination}")

        if output_parts:
            return "\n".join(output_parts)

        return "No relevant memories found."
    except Exception as e:
        logger.error(f"Error searching memory: {e}")
        return "Error searching memories."


@mcp.tool()
async def save_to_memory(ctx: Context, content: str, user_id: str) -> str:
    """
    Save important information to memory

    IMPORTANT:
    - For solutions: Only call this AFTER the user confirms they are satisfied
    - For preferences/configuration: Can be called anytime
    - Do NOT save failed solutions or solutions the user is not happy with

    Behavior depends on MEM0_USE_LLM environment variable:
    - If MEM0_USE_LLM=true: Saves both LLM-extracted facts AND complete original content
    - If MEM0_USE_LLM=false: Only saves complete original content (no LLM processing)

    This builds a knowledge base for future reference

    Args:
        ctx: MCP context
        content: Content to save (e.g., user's query, solution code, explanation,
                 user preferences, API keys, how to access API keys, etc.)
        user_id: User identifier extracted from message

    Returns:
        Status message
    """
    try:
        mem0 = ctx.request_context.lifespan_context.mem0
        use_llm = ctx.request_context.lifespan_context.use_llm

        messages = [{"role": "user", "content": content}]

        if use_llm:
            # Save 1: LLM extracts key facts (vector + graph memory with custom prompts)
            mem0.add(messages, user_id=user_id, infer=True)

            # Save 2: Store complete original content as-is (vector only, no LLM processing)
            # Temporarily disable graph to avoid duplicate graph updates for same content
            original_enable_graph = mem0.enable_graph
            mem0.enable_graph = False
            mem0.add(messages, user_id=user_id, infer=False)
            mem0.enable_graph = original_enable_graph

            return "Information saved to memory successfully (facts + complete content)."
        else:
            # No LLM: Only save complete original content directly
            mem0.add(messages, user_id=user_id, infer=False)
            return "Information saved to memory successfully (direct storage)."
    except Exception as e:
        logger.error(f"Error saving to memory: {e}")
        return f"Error saving to memory: {str(e)}"


if __name__ == "__main__":
    mcp.run()
