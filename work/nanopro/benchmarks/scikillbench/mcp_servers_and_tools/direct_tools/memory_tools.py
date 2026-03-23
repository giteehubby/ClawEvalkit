"""
Memory Tools for Conversational System
All agents (Orchestrator and internal agents in DeepSolver) can use these tools

Graph Memory:
- Enabled by default (extracts entities and relationships from conversations)
- Set ENABLE_GRAPH_MEMORY=false to disable and use only vector-based memory
- Requires Neo4j database with NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD for graph memory
"""

import os
from mem0 import Memory
from agents import function_tool
from .custom_memory_prompts import (
    MATERIALS_SCIENCE_EXTRACTION_PROMPT,
    MATERIALS_SCIENCE_GRAPH_PROMPT
)


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

# Base configuration dictionary for from_config method
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
    print(f"✅ Memory LLM ENABLED - Using {MEM0_LLM_MODEL} for intelligent extraction")
else:
    print("ℹ️  Memory LLM DISABLED - Direct storage only (no extraction)")

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
    print("✅ Graph memory ENABLED - Entity relationships will be tracked")
else:
    print("ℹ️  Graph memory DISABLED - Using vector-based memory only")

print("✅ Custom materials science prompts ENABLED (vector + graph)")

# Create global memory instance with custom prompt
mem0 = Memory.from_config(config_dict)


@function_tool
async def search_memory(query: str, user_id: str) -> str:
    """
    Search through stored memories

    Returns relevant memories that may help solve the current problem
    Use this to retrieve user preferences, API keys, similar problems, solutions, or relevant experience from past memories

    Args:
        query: What to search for
        user_id: User identifier extracted from message

    Returns:
        Formatted string with relevant memories (from vector store) and entity relationships (from graph store)
    """
    try:
        search_result = mem0.search(query, user_id=user_id, limit=5)

        output_parts = []

        # Add vector store results
        if search_result and search_result.get('results'):
            vector_results = search_result['results']
            output_parts.append("Relevant memories:")
            for mem in vector_results:
                output_parts.append(f"- {mem['memory']}")

        # Add graph store results (entity relationships)
        if ENABLE_GRAPH_MEMORY and search_result and search_result.get('relations'):
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
        print(f"Error searching memory: {e}")
        return "Error searching memories."


@function_tool
async def save_to_memory(content: str, user_id: str) -> str:
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
        content: Content to save (e.g., user's query, solution code, explanation,
                 user preferences, API keys, how to access API keys, etc.)
        user_id: User identifier extracted from message

    Returns:
        Status message
    """
    try:
        messages = [{"role": "user", "content": content}]

        if MEM0_USE_LLM:
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
        print(f"Error saving to memory: {e}")
        return f"Error saving to memory: {str(e)}"


# Export public interfaces
__all__ = [
    'mem0',
    'search_memory',
    'save_to_memory',
    'ENABLE_GRAPH_MEMORY'  # For checking if graph memory is enabled
]
