# Local Development & Benchmark Guide

This guide covers local development setup (without Docker) and running benchmarks. For quick start with Docker, see the [main README](../README.md).

## Prerequisites
- Python 3.12 or higher
- Node.js (for mcp workspace-server)
- Git

## 1. Clone and Navigate
```bash
git clone https://github.com/CederGroupHub/CASCADE.git
cd CASCADE
```

## 2. Install uv Package Manager
```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 3. Set Up Virtual Environment
```bash
# Create a new virtual environment
uv venv

# Activate the virtual environment
source .venv/bin/activate  # for Linux/Mac
# or
.venv\Scripts\activate     # for Windows
```

## 4. Install Dependencies
```bash
# Install Python dependencies (with some materials science/chemistry packages like pymatgen)
uv pip install -r deep_solver_benchmark/requirements.txt

# Install and build Node.js dependencies for workspace_server
cd mcp_servers_and_tools/workspace_server
npm install
npm run build
cd ../..

# Install Playwright browser (required for web crawling in research_server)
playwright install chromium
```

## 5. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your API keys and credentials
```

The `.env.example` file contains all required variables with comments. Priority: `.env` file > shell environment > code defaults.

Alternatively, you can add `export VAR=value` lines to your `~/.bashrc` (remember to run `source ~/.bashrc` after editing).

### 5.1 Supabase Database Setup

The project uses Supabase for storing extracted code blocks and enabling semantic search. Follow these steps:

1. **Create a Supabase Project**:
   - Go to [supabase.com](https://supabase.com)
   - Sign up or log in
   - Create a new project
   - Wait for the project to be set up

2. **Get Your Supabase Credentials**:
   - In your Supabase project dashboard, go to **Project Settings**:
     - **Data API** → Copy **Project URL** → `SUPABASE_URL`
     - **API Keys** → Click **Legacy anon, service_role API keys** → Click **Reveal** on service_role → `SUPABASE_SERVICE_KEY`
     - Click **Connect** (top center) → Change Method to **Session pooler** → Copy and replace `[YOUR-PASSWORD]` with your password → `SUPABASE_DATABASE_URL`

   *Note: Supabase UI may change over time. Look for API keys and connection strings in Project Settings. Free-tier Supabase projects may be paused after inactivity - check your project status and resume if needed before running the system.*

3. **Set Up the Database Schema**:
   - In your Supabase project dashboard, go to SQL Editor
   - Copy and paste the contents of `mcp_servers_and_tools/research_server/extracted_code.sql`
   - Run the SQL script to create the required table and functions

   The script creates:
   - `extracted_code` table for storing code blocks with embeddings
   - Indexes for efficient querying
   - `match_code_blocks` function for semantic search
   - Unique constraints to prevent duplicates

4. **Fill in Supabase credentials in your `.env` file** (SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_DATABASE_URL)

### 5.2 Neo4j Database Setup (for Knowledge Graph)
Here we use Neo4j for knowledge graph storage. Choose one of the following setup methods:

#### Option A: Neo4j Desktop
1. **Install Neo4j Desktop**:
   - Download from [neo4j.com/download](https://neo4j.com/download/)
   - Install and launch Neo4j Desktop

2. **Create a New Database**:
   - Open Neo4j Desktop
   - Create a new project and database
   - Set a password for the `neo4j` user
   - Start the database

3. **Fill in Neo4j credentials in your `.env` file** (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

#### Option B: Command Line (Linux)
For running Neo4j on a Linux server: 

1. **Download and Install Neo4j**:
   ```bash
   # Download Neo4j 2025.08.0
   # **Prerequisite:** Neo4j 2025.08.0 requires Java 21. You need to install Java 21 first.
   cd /tmp
   wget https://dist.neo4j.org/neo4j-community-2025.08.0-unix.tar.gz
   
   # Extract to user directory
   tar -xzf neo4j-community-2025.08.0-unix.tar.gz
   mv neo4j-community-2025.08.0 ~/neo4j
   
   # Configure security settings (bind to localhost only)
   echo "server.bolt.listen_address=localhost:7687" >> ~/neo4j/conf/neo4j.conf
   echo "server.http.listen_address=localhost:7474" >> ~/neo4j/conf/neo4j.conf
   ```

2. **Start Neo4j with Java 21**:

   **Note:** The `JAVA_HOME` path may vary. Find yours with: `find /usr/lib/jvm -name "java-21*" -type d 2>/dev/null | head -1`

   **Tip:** Add `export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64` to your `~/.bashrc` to avoid repeating it.

   ```bash
   ~/neo4j/bin/neo4j start    # Start server
   ~/neo4j/bin/neo4j status   # Check status
   ~/neo4j/bin/neo4j stop     # Stop server
   ```

3. **Set Initial Password**:
   ```bash
   # Connect (default password is 'neo4j'), then set your new password
   ~/neo4j/bin/cypher-shell -u neo4j -p neo4j
   ```

4. **Fill in Neo4j credentials in your `.env` file** (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

## 6. Test the Setup

### 6.1 Start MLflow Server
In a separate terminal window, start MLflow from the appropriate directory based on your use case:

**For Benchmark Tests (deep_solver_benchmark):**
```bash
cd deep_solver_benchmark
nohup mlflow server --host 127.0.0.1 --port 5001 --backend-store-uri ./mlruns --default-artifact-root ./mlruns > mlflow.log 2>&1 &
```

**For Conversational System:**
```bash
cd conversational_system
nohup mlflow server --host 127.0.0.1 --port 5001 --backend-store-uri ./mlruns --default-artifact-root ./mlruns > mlflow.log 2>&1 &
```

*Note: MLflow data is stored in the `mlruns/` directory where you start the server. Choose the directory based on which component you're testing.*

**Security Note:** The MLflow server binds to localhost (127.0.0.1) only. To view the MLflow UI from your local machine while running on a remote server, set up an SSH tunnel:

```bash
ssh -f -N -L 5001:localhost:5001 username@your_remote_server_ip
```

### 6.2 Verify Supabase Setup

Make sure your Supabase project is properly configured:

1. **Login to Supabase**: Visit [https://supabase.com](https://supabase.com) and ensure you're logged in
2. **Check Project Status**: Verify your Supabase project is active
3. **Verify Database Schema**: Ensure the `extracted_code` table exists in your project
4. **Test API Connection**: Verify your `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are working

You can test the connection by running a simple query in your Supabase SQL Editor:
```sql
SELECT COUNT(*) FROM extracted_code;
```

### 6.3 Start Neo4j

#### Option A: Local Neo4j Desktop
Make sure Neo4j Desktop is running:

1. Open the Neo4j Desktop application.
2. Ensure your Local instance shows a green "RUNNING" status.
3. Usually, the `neo4j` database will start automatically (you should see `neo4j` listed under Databases).

**Access Local Neo4j from Remote Server:**
```bash
# When running tests on a remote server while Neo4j runs locally (e.g., on your laptop)
ssh -N -f -R 7687:localhost:7687 -R 7474:localhost:7474 username@your_remote_server_ip
```

#### Option B: Remote Neo4j Server
If you installed Neo4j on a remote Linux server, start it with `~/neo4j/bin/neo4j start` (see section 5.2 for details).

#### Remote Access via SSH Tunnel
To access Neo4j running on a remote server from your local machine:

**From Mac/Linux to Remote Server:**
```bash
# Establish SSH tunnel for Neo4j access
ssh -f -N -L 17474:localhost:7474 -L 17687:localhost:7687 username@remote_server_ip

# Access Neo4j Browser in your local browser:
# http://localhost:17474

# Connect via cypher-shell (if installed locally):
cypher-shell -u neo4j -p your_password -a localhost:17687
```

### 6.4 Run Conversational System
To run the conversational system locally:

```bash
cd conversational_system
./launch.sh
```

This starts the Streamlit web interface at http://localhost:8501.

**Remote access:** If running on a remote server, set up SSH tunnels first:
```bash
ssh -f -N -L 8501:localhost:8501 username@your_remote_server
```
Then access http://localhost:8501 on your local machine.

### 6.5 Run Benchmark Tests for DeepSolver
Choose one of the following testing modes:

**Note on Tool Configuration**: The agents use direct tools by default. To switch to MCP servers, modify the agent files: uncomment the MCP-based agent block and comment out the direct-tools agent block. 

**Single-Query Mode** (recommended when you want to quickly ask a single question):
```bash
cd deep_solver_benchmark
python -u test_workflow.py
```
This starts a single-query session where you can input questions one by one.

**Batch Mode** (for automated testing):
```bash
cd deep_solver_benchmark
python -u test_workflow.py --batch --repeat REPEAT --results-file RESULTS_FILE
```
This runs predefined questions with multiple repetitions. You can modify the question list in `test_workflow.py`.

**Benchmark Mode** (run benchmark JSONs and compute accuracy):

**Note 1:** Before running pymatgen-db related benchmarks, you need to set up MongoDB and ensure it is active:

```bash
# Navigate to pymatgen-db solution directory
cd ../benchmark_tasks_and_results/questions_and_answers/data/data_management/pymatgen-db_solution_code

# Extract MongoDB archive for linux (only needed once)
tar -xzf mongodb-linux-x86_64-ubuntu2204-7.0.8.tgz

# Create test database directory (only needed once)
mkdir test_db

# Start MongoDB server
./mongodb-linux-x86_64-ubuntu2204-7.0.8/bin/mongod --dbpath test_db --bind_ip 127.0.0.1 --logpath mongodb.log --fork

# In a new terminal window, make sure the virtual environment is activated
cd CASCADE
source .venv/bin/activate

# IMPORTANT: Verify you're using the venv's mgdb (not system version)
which mgdb  # Should show: .venv/bin/mgdb

cd benchmark_tasks_and_results/questions_and_answers/data/data_management/pymatgen-db_solution_code

# Insert VASP data (only needed once)
mgdb insert -c db.json Li2O

# Test if pymatgen-db is working correctly
python -u pymatgen-db_density_change.py
```

*Note: If `which mgdb` shows a path outside the virtual environment (e.g., `~/.local/bin/mgdb`), you may get "ModuleNotFoundError: No module named 'pymatgen.db'". In that case, use the full path: `.venv/bin/mgdb insert -c db.json Li2O`*

**NOTE 2**: XTB is required for xtb benchmarks and must be installed separately: Download from: https://github.com/grimme-lab/xtb/releases
We used xtb version 6.7.1 (edcfbbe) compiled by 'albert@albert-system' on 2024-07-22

**NOTE 3**: The `EnumerateStructureTransformation` in pymatgen is needed for a disorder-order transformation task in the pymatgen_data_process benchmark. It requires the enumlib library to be installed on the system. Instructions for installing enumlib can be found at its Github page: https://github.com/msg-byu/enumlib . Overall, you need to make sure that enum.x and makestr.x (or makeStr.py for more recent versions) are properly compiled and in your executable PATH.

**NOTE 4**: LAMMPS and its Python interface is required for md benchmarks. You may refer to LAMMPS_INSTALLATION_README.md for installation guidance, though the specific setup may vary depending on your system configuration.

**Run benchmark tests:**
```bash
cd deep_solver_benchmark
# Example: run a benchmark JSON file and save results to a JSON file
python -u test_workflow.py --benchmark ../benchmark_tasks_and_results/questions_and_answers/computation/specialized_models_and_toolkits/mlip.json --repeat 3 --results-file ../benchmark_tasks_and_results/test_results/results_timestamp/results_mlip.json

# Or you can modify the run_benchmark.sh to run more benchmark files
nohup ./run_benchmark.sh > benchmark_output.log 2>&1 &

# After runs finish, evaluate accuracy for a single result file:
cd ../benchmark_tasks_and_results/evaluation
python -u benchmark_evaluator.py --results-file ../test_results/results_timestamp/results_mlip.json
# Or evaluate accuracy across all result files in a directory
python -u benchmark_evaluator.py --results-dir ../test_results/results_timestamp
```
Results for run_benchmark.sh:
- Run logs are saved under the `benchmark_tasks_and_results/test_log/` directory
- Result JSON files are saved under the `benchmark_tasks_and_results/test_results/results_timestamp` directory (`results_timestamp` is a placeholder; replace it with an actual timestamp (default) or your custom directory name)
- The evaluator writes a consolidated JSON to `benchmark_tasks_and_results/evaluation/` and prints overall, each level (0 or 1), per benchmark JSON file, and per-question accuracy and average execution time to the console
- Evaluation rule: attempts with processed_output equal to "Workflow Failed" are excluded from both numerator and denominator for accuracy calculation and excluded from average time calculation; attempts marked as "Failed" are included (to measure agent-side failures)

**For vLLM and Non-OpenAI Models:**
To use vLLM or other non-OpenAI models, set these environment variables in your `.env` file or shell:

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
AGENT_MODEL_NAME=your-model-name
REQUIRE_OPENAI_API_KEY=false
USE_ADAPTIVE_AGENTS=true
```

Note: You also need to modify the openai-agents SDK. See [ADAPTIVE_AGENTS.md](../conversational_system/ADAPTIVE_AGENTS.md) for the required SDK modification and vLLM server setup.

### 6.6 Using Baselines/Ablation Studies
The `deep_solver_benchmark/baselines/` and `deep_solver_benchmark/ablation_studies/` folders contain baseline and ablation study implementations. For the Claude Code baseline, see [baselines/claude_code/README.md](baselines/claude_code/README.md). For other baselines:

1. **Replace the corresponding code files in `deep_solver_benchmark/deep_solver/`** with the versions in the `baselines/` or `ablation_studies/` folder
2. **Run the tests as usual** using the methods described in section 6.5 (also supporting vLLM with non-OpenAI models)