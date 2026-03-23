# Memory Server

A specialized MCP (Model Context Protocol) server for memory consolidation and retrieval using [mem0](https://github.com/mem0ai/mem0).

## Overview

The Memory Server provides comprehensive memory capabilities for AI agents through a hybrid dual-store architecture:

- **Vector Store (Supabase)**: Semantic similarity search over embedded memories
- **Graph Store (Neo4j)**: Entity-relationship extraction and querying

## Features

- **Semantic Memory Search**: Find relevant past interactions using natural language queries
- **Dual-Path Save Strategy**:
  1. LLM-extracted facts (searchable key points) - stored in both vector and graph stores
  2. Complete original content (verbatim) - stored in vector store only
- **Custom Prompts**: Optimized for materials science and chemistry research contexts
- **User-Scoped Memories**: All operations are scoped by user_id for personalization

## Tools

### `search_memory`
Search through stored memories for relevant information.

**Parameters:**
- `query` (str): What to search for
- `user_id` (str): User identifier for scoping memories

**Returns:** Relevant memories and entity relationships

### `save_to_memory`
Save important information to memory for future reference.

**Parameters:**
- `content` (str): Content to save (queries, solutions, preferences, etc.)
- `user_id` (str): User identifier for scoping memories

**Returns:** Status message

## Installation

```bash
cd memory_server
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

## Running the Server

```bash
# Using Python directly
python src/memory_mcp.py

# Or using uv
uv run src/memory_mcp.py
```

## Database Setup

### Supabase (Vector Store)

1. Create a Supabase project at [supabase.com](https://supabase.com)
2. Get your database connection string from Project Settings -> Connect -> Session pooler
3. The required tables are created automatically by mem0 on first use

### Neo4j (Graph Store)

1. Install Neo4j from [neo4j.com/download](https://neo4j.com/download/)
2. Start the database and set a password
3. Configure `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`

To disable graph memory (use vector store only), set `ENABLE_GRAPH_MEMORY=false`.
