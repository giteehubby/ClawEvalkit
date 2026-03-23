# MLflow Tracing Guide

This system has integrated MLflow tracing to automatically record the complete agent execution process, including:
- Orchestrator tool calls (search_memory, solve_with_deep_solver, execute_code, etc.)
- DeepSolver internal 4-agent workflow (Solution Researcher, Code Agent, Debug Agents, Output Processor)
- Each agent's inputs, outputs, tool calls, and execution time
- Complete hierarchy of LLM calls and tool usage

## How to View Traces

### 1. Launch the System

**Option A: Using Docker (Recommended)**

```bash
docker compose up -d
```

This automatically starts:
- **Streamlit frontend** (port 8501): Web interface for user interaction
- **MLflow tracking server** (port 5001): Tracing and experiment tracking UI

**Option B: Manual Setup**

1. First, start the MLflow tracking server:

```bash
nohup mlflow server --host 127.0.0.1 --port 5001 --backend-store-uri ./mlruns --default-artifact-root ./mlruns > mlflow.log 2>&1 &
```

2. Then, launch the Streamlit app:

```bash
cd conversational_system
./launch.sh
```

**What happens:**
1. The Streamlit app launches in your browser (or navigate to http://localhost:8501)
2. Register a new account or log in with existing credentials
3. Start asking questions - each conversation is automatically traced
4. MLflow tracing runs in the background, recording all agent executions
5. **After each conversation turn**, check the terminal output and you'll see a direct link to the trace

**View Traces Anytime:**
- Click the trace URL printed in the terminal for immediate access to that specific trace
- Access the MLflow UI at http://localhost:5001 to browse all traces, compare runs, or review historical traces

**Security Note:** Both servers bind to localhost (127.0.0.1) by default. If running on a remote server, use SSH tunnels:

```bash
# Tunnel for Streamlit frontend and MLflow UI
ssh -f -N -L 8501:localhost:8501 -L 5001:localhost:5001 username@your_remote_server_ip
```

### 2. Navigate to Experiment

1. In the MLflow UI left sidebar, find and click the **`conversational_system`** experiment
2. You will see a list of all runs, each run corresponds to one conversation turn

### 3. View Complete Agent Trace

Each conversation produces multiple traces:
- **Individual API calls** (embedding/completion): Single span, shorter execution time
- **Complete agent trace**: Multiple spans, contains full tool call hierarchy ⭐

**How to quickly find the complete agent trace:**

1. Click on a run to enter the run details page
2. Switch to the **`Traces`** tab
3. **Sort**: Click the `Execution Time` column header, select **descending order** (longest execution time on top)
4. **Identify the correct trace**: Find the trace whose Request starts with `[SYSTEM: user_id=...`
   - This is the agent trace containing the complete conversation logic
   - Usually has the longest execution time and most spans
5. Click to enter the trace and view the complete execution hierarchy

### 4. Trace Content Explanation

The complete agent trace contains the following information:

**Orchestrator Level:**
- `AgentRunner.run` - Top-level agent execution
- `MaterialsScienceAssistant` - Orchestrator agent
- Tool call spans:
  - `search_memory` - Memory search (input: query + user_id, output: relevant memories)
  - `solve_with_deep_solver` - Call DeepSolver (if used)
  - `check_installed_packages`, `install_dependencies`, `execute_code` - Direct execution (if used)
  - `save_to_memory` - Save successful solution (if user satisfied)

**DeepSolver Internal Levels (if solve_with_deep_solver was used):**
- `SolutionResearcherAgent` - Phase 1: Research
- `CodeExecutionAgent` - Phase 2: Code execution
- `DebugAgent1/2/3` - Phase 3: Parallel debugging (if needed)
- `OutputProcessorAgent` - Phase 4: Output processing

Each span contains:
- **Inputs**: Tool input parameters
- **Outputs**: Tool return results
- **Execution time**: Time taken
