# CASCADE

CASCADE (Cumulative Agentic Skill Creation through Autonomous Development and Evolution) is a multi-agent system for materials science and chemistry research.

## Quick Start (Docker)

The fastest way to get started is using Docker.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [Git](https://git-scm.com/downloads)
- A [Supabase](https://supabase.com) account
- Neo4j database (local installation)

### 1. Clone the Repository

```bash
git clone https://github.com/CederGroupHub/CASCADE.git
cd CASCADE
```

### 2. Set Up Supabase

1. Go to [supabase.com](https://supabase.com) and create a new project
2. In your project dashboard, go to **Project Settings**:
   - **Data API** → Copy **Project URL** → `SUPABASE_URL`
   - **API Keys** → Click **Legacy anon, service_role API keys** → Click **Reveal** on service_role → `SUPABASE_SERVICE_KEY`
   - Click **Connect** (top center) → Change Method to **Session pooler** → Copy and replace `[YOUR-PASSWORD]` with your password → `SUPABASE_DATABASE_URL`
3. Go to **SQL Editor** and run the schema from `mcp_servers_and_tools/research_server/extracted_code.sql`

*Note: Supabase UI may change over time. Look for API keys and connection strings in Project Settings. Free-tier Supabase projects may be paused after inactivity - check your project status and resume if needed before running the system.*

### 3. Set Up Neo4j

#### Option A: Neo4j Desktop 
1. Download from [neo4j.com/download](https://neo4j.com/download/)
2. Create a new project and database
3. Set a password and start the database

#### Option B: Command Line (Linux)

**Prerequisite:** Java 21 is required

```bash
# Download and extract
wget https://dist.neo4j.org/neo4j-community-2025.08.0-unix.tar.gz
tar -xzf neo4j-community-2025.08.0-unix.tar.gz
mv neo4j-community-2025.08.0 ~/neo4j

# Configure to bind to localhost only
echo "server.bolt.listen_address=localhost:7687" >> ~/neo4j/conf/neo4j.conf
echo "server.http.listen_address=localhost:7474" >> ~/neo4j/conf/neo4j.conf

# Start Neo4j (JAVA_HOME path may vary on your system)
# Find yours: find /usr/lib/jvm -name "java-21*" -type d 2>/dev/null | head -1
# Tip: Add "export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64" to ~/.bashrc
~/neo4j/bin/neo4j start

# Set initial password (default password is 'neo4j', then set your new password)
~/neo4j/bin/cypher-shell -u neo4j -p neo4j
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
nano .env  # Fill in your API keys and credentials from steps 2-3

# Set your user ID for Docker (required for correct file permissions)
echo "UID=$(id -u)" >> .env
echo "GID=$(id -g)" >> .env
```

*Priority: `.env` file takes precedence. If a variable is not set in `.env`, it falls back to shell environment variables.*

### 5. Start the Services

```bash
# Make sure Supabase and Neo4j are running first. For Neo4j on Linux:
~/neo4j/bin/neo4j status

# Create the SQLite database file if it doesn't exist (prevents Docker from mounting it as a directory)
touch conversational_system/conversations.db

# Start CASCADE with Docker (open cascade.log to view real-time output)
docker compose up > cascade.log 2>&1 &
```

### 6. Access the Application

- **CASCADE UI**: http://localhost:8501
- **MLflow UI**: http://localhost:5001 (traces and experiments)
- **Neo4j Browser**: http://localhost:7474 (optional)

**Remote access:** If running on a remote server, set up SSH tunnels first:
```bash
ssh -f -N -L 8501:localhost:8501 -L 5001:localhost:5001 -L 7474:localhost:7474 username@your_remote_server
```
Then access the URLs above on your local machine.

---

## Using Local Models (vLLM)

CASCADE supports local models via vLLM or other OpenAI-compatible servers.

### Environment Variables

Add these to your `.env` file:

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
AGENT_MODEL_NAME=your-model-name
REQUIRE_OPENAI_API_KEY=false
USE_ADAPTIVE_AGENTS=true
```

### Setup Guide

For vLLM deployment, SDK modifications, and detailed configuration, see [Adaptive Agents Documentation](conversational_system/ADAPTIVE_AGENTS.md).

---

## Management Commands

```bash
# Stop services
docker compose down

# Rebuild after code changes
docker compose up --build > cascade.log 2>&1 &
```

---

## Data Persistence

Data is stored on your local filesystem and persists across container restarts:
- `./conversational_system/conversations.db` - Conversation history
- `./conversational_system/saved_code/` - Saved code files
- `./conversational_system/mlruns/` - MLflow tracking data

Neo4j data is stored in your local Neo4j installation.

To reset all data, manually delete these files/directories.

---

## Project Structure

```
CASCADE/
├── conversational_system/           # Main conversational agent system
│   ├── frontend/                    # Streamlit web interface
│   ├── core/                        # Orchestrator and DeepSolver agents
│   ├── deep_solver_with_memory/     # Multi-agent workflow (4-agent architecture)
│   ├── launch.sh                    # Launch script for local development
│   ├── conversations.db             # SQLite database (created after first conversation)
│   ├── ADAPTIVE_AGENTS.md           # vLLM and non-OpenAI model configuration
│   └── MLFLOW_TRACING.md            # MLflow tracing guide
├── deep_solver_benchmark/           # Benchmark suite and testing
│   ├── deep_solver/                 # Main agent implementations
│   ├── deep_solver_free_form/       # Free-form output variant
│   ├── baselines/                   # Baseline implementations (including Claude Code)
│   ├── ablation_studies/            # Ablation study variants
│   ├── data_for_demonstration/      # Data files for free-form demonstrations
│   ├── README.md                    # Benchmark overview and quick start
│   ├── DEVELOPMENT.md               # Local development and benchmark guide
│   └── requirements.txt             # Python dependencies
├── mcp_servers_and_tools/           # MCP servers and direct tools
│   ├── research_server/             # Code extraction and knowledge graph
│   ├── memory_server/               # Memory consolidation
│   ├── workspace_server/            # Code execution environment
│   └── direct_tools/                # Direct tool implementations (non-MCP)
├── benchmark_tasks_and_results/     # Benchmark questions, answers, and results
│   ├── questions_and_answers/       # Benchmark JSON files (download required)
│   ├── demonstration/               # Free-form demonstration examples
│   └── evaluation/                  # Evaluation scripts
├── docker/                          # Docker configuration
├── utils/                           # Shared utilities
└── .env.example                     # Environment variable template
```

*Note: Benchmark data files require separate download. See [benchmark_tasks_and_results/README.md](benchmark_tasks_and_results/README.md) for instructions.*

---

## Additional Documentation

| Document | Description |
|----------|-------------|
| [Development Guide](deep_solver_benchmark/DEVELOPMENT.md) | Local development setup (No Docker) for conversational system and benchmarks |
| [Adaptive Agents](conversational_system/ADAPTIVE_AGENTS.md) | Using vLLM and non-OpenAI models |
| [Benchmark README](deep_solver_benchmark/README.md) | Benchmark structure and variants |
