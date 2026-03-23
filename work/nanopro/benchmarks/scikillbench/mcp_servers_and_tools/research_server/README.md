# Research Server

A specialized MCP server for code research and analysis workflows. Provides tools for extracting, analyzing, and discovering code patterns across repositories and documentation.

## Features

- **Code Extraction**: Extract code blocks from URLs and store in database
- **Semantic Search**: Retrieve code examples using natural language queries
- **Quick Introspection**: Inspect packages, classes, methods, and functions
- **Runtime Probing**: Probe code snippets for errors
- **Knowledge Graph**: Parse local packages and query code patterns (optional)

## Tools

| Tool | Description |
|------|-------------|
| `extract_code_from_url` | Extract code blocks from URLs and store in database |
| `retrieve_extracted_code` | Search and retrieve extracted code examples |
| `quick_introspect` | Quick introspection of packages, classes, methods, and functions |
| `runtime_probe_snippet` | Runtime probing of code snippets for KeyError and AttributeError |
| `parse_local_package` | Parse and analyze local Python packages (requires USE_KNOWLEDGE_GRAPH=true) |
| `query_knowledge_graph` | Query Neo4j knowledge graph for code patterns (requires USE_KNOWLEDGE_GRAPH=true) |

## Installation

```bash
cd research_server
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
python src/research_mcp.py

# Or using uv
uv run src/research_mcp.py
```

## Database Setup

### Supabase

1. Go to [supabase.com](https://supabase.com) and create a new project
2. In your project dashboard, go to **Project Settings**:
   - **Data API** → Copy **Project URL** → `SUPABASE_URL`
   - **API Keys** → Click **Legacy anon, service_role API keys** → Click **Reveal** on service_role → `SUPABASE_SERVICE_KEY`
3. Go to **SQL Editor** and run the schema from `extracted_code.sql`

### Neo4j (Optional)

Required only if `USE_KNOWLEDGE_GRAPH=true`:

1. Install Neo4j from [neo4j.com/download](https://neo4j.com/download/)
2. Start the database and set a password
3. Configure `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`
