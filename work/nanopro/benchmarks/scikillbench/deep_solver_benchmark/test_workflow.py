#!/usr/bin/env python3
"""
Enhanced test script with parallel debugging workflow.
Supports both single-query and batch question modes.
"""

import sys
import os
# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Add project root for absolute imports when invoked from benchmark
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file (if exists)
# Priority: .env file > shell environment (.bashrc) > code defaults
from dotenv import load_dotenv
load_dotenv(override=True)

# Enable MLflow autolog BEFORE importing any agent modules
import mlflow
mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001"))
mlflow.openai.autolog(disable=False, log_traces=True)  # Use basic parameters only
mlflow.tracing.enable()
EXPERIMENT_NAME = "test_workflow_oct_13_gpt4.1mini"
mlflow.set_experiment(EXPERIMENT_NAME)

from utils.quiet_utils import setup_quiet_mode, silence_external_output, reapply_quiet_mode
setup_quiet_mode()

# Configure OpenAI Agents SDK tracing
try:
    # Tracing is enabled by default to capture detailed LLM interactions (OPENAI_API_KEY needs to be set as an environment variable).
    # Comment this line and uncomment the lines below to disable tracing if needed.
    print("📊 OpenAI Agents SDK tracing enabled for detailed LLM interaction capture")
    # from agents import set_tracing_disabled
    # set_tracing_disabled(True)
    # print("OpenAI Agents SDK tracing disabled")
except ImportError:
    print("⚠️ OpenAI Agents SDK tracing function not available")

from utils import retry_with_backoff, call_tool_with_retry, get_supabase_client, clear_supabase_tables
from utils.mcp_server_manager import cleanup_mcp_servers, get_mcp_server_info

import sys
import os
import asyncio
import traceback
import time
import argparse
import json
from datetime import datetime
import subprocess
from typing import List
import threading
import psutil

# Import output types
from deep_solver_benchmark.deep_solver.output_types import FinalResult

# Global variable to track MCP server PIDs for this process
_MCP_SERVER_PIDS = set()
_MCP_SERVER_LOCK = threading.Lock()

def register_mcp_server_pid(pid: int):
    """Register an MCP server PID for this process."""
    with _MCP_SERVER_LOCK:
        _MCP_SERVER_PIDS.add(pid)

def unregister_mcp_server_pid(pid: int):
    """Unregister an MCP server PID."""
    with _MCP_SERVER_LOCK:
        _MCP_SERVER_PIDS.discard(pid)

def get_current_process_mcp_pids():
    """Get all MCP server PIDs registered by this process."""
    with _MCP_SERVER_LOCK:
        return _MCP_SERVER_PIDS.copy()

def kill_specific_process(pid: int, timeout: int = 3):
    """
    Kill a specific process by PID and wait for termination.
    """
    try:
        # Check if process exists
        if not psutil.pid_exists(pid):
            return
        
        # Try graceful termination first
        process = psutil.Process(pid)
        process.terminate()
        
        # Wait for graceful termination
        try:
            process.wait(timeout=timeout)
            return
        except psutil.TimeoutExpired:
            pass
        
        # Force kill if graceful termination failed
        process.kill()
        process.wait(timeout=1)
        
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
        # Process already terminated or we don't have permission
        pass

def find_mcp_processes():
    """Find MCP-related processes using process group and working directory isolation"""
    import os
    
    current_pid = os.getpid()
    current_process = psutil.Process(current_pid)
    current_working_dir = os.getcwd()
    
    mcp_processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'ppid', 'cwd']):
            try:
                if proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    # Look for MCP-related processes
                    if any(keyword in cmdline.lower() for keyword in [
                        'tavily-mcp', 'workspace_server', 'research_server', 
                        'mcp_code_executor', 'research_mcp.py'
                    ]):
                        proc_obj = psutil.Process(proc.info['pid'])
                        current_create_time = current_process.create_time()
                        proc_create_time = proc_obj.create_time()
                        
                        # Method 1: Check if it's a direct child of current process
                        is_child = proc.info['ppid'] == current_pid
                        
                        # Method 2: Check if it's in the same process group (for shared servers)
                        # This ensures we only kill servers started by our process group
                        try:
                            current_pgid = os.getpgid(current_pid)
                            proc_pgid = os.getpgid(proc.info['pid'])
                            same_process_group = current_pgid == proc_pgid
                        except (OSError, ProcessLookupError):
                            same_process_group = False
                        
                        # Method 3: Check if it's a Tavily process started by this process
                        # (Tavily processes are unique per process and should be cleaned)
                        is_tavily = 'tavily-mcp' in cmdline.lower()
                        time_diff = abs(proc_create_time - current_create_time)
                        is_recent_tavily = is_tavily and time_diff < 10  # Tavily processes started within 10 seconds
                        
                        # Very conservative approach: Only kill processes that are direct children of current process
                        # or recent Tavily processes (which are unique per process)
                        should_kill = is_child or is_recent_tavily
                        
                        if should_kill:
                            mcp_processes.append(proc.info['pid'])
                            print(f"🔍 Found MCP process {proc.info['pid']}: {cmdline[:100]}... (will kill)")
                        else:
                            print(f"🔍 Found MCP process {proc.info['pid']}: {cmdline[:100]}... (will NOT kill - not a child)")
                            
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        print(f"⚠️  Error finding MCP processes: {e}")
    
    return mcp_processes

def load_questions_from_json(json_path):
    """
    Load questions from benchmark JSON file.
    Each entry contains user_query with variants, output_type and unit information.
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        questions = []
        for idx, entry in enumerate(data):
            user_queries = entry.get('user_query', {})
            output_type = entry.get('output_type', '')
            unit = entry.get('unit', '')
            
            # Process both questions (0 and 1) from each entry if they exist and are non-empty
            for q_idx in ['0', '1']:
                if q_idx in user_queries:
                    base_query = user_queries[q_idx]
                    if not base_query or not base_query.strip():
                        continue  # skip empty queries
                    
                    # Extract the specific tolerance for this question level
                    tolerance = entry.get('absolute_tolerance', 'N/A')
                    if isinstance(tolerance, dict):
                        tolerance = tolerance.get(q_idx, 'N/A')
                    
                    # Add output_type and unit information to the question
                    enhanced_query = f"{base_query} You MUST provide the successful code solution and the execution result. Importantly, you MUST output a final answer according to the execution result in the format of {output_type}, considering the unit {unit} (if any). But you should NOT output unit in the answer. CRITICAL FORMAT REQUIREMENTS: Your final answer must use standard Python data types only (int, float, list, str) - do NOT use numpy array format like 'array([...])'. All lists should be in standard Python list format like [1.2, 3.4, 5.6]. The shape information in the output_type is for your reference to ensure correct dimensions."
                    questions.append({
                        'original_idx': idx,
                        'question_idx': q_idx,
                        'query': enhanced_query,
                        'output_type': output_type,
                        'unit': unit,
                        'answer': entry.get('answer', 'N/A'),
                        'absolute_tolerance': tolerance
                    })
        
        return questions
    except Exception as e:
        print(f"Error loading questions from JSON: {e}")
        return []

# batch questions - USING EMPTY LIST FOR NOW
QUESTIONS = []

# examples of questions
# QUESTIONS = [
#     # 'Write code for querying the formation energy and the bulk modulus of Li6FeN4 (Materials Project ID: mp-1029739). My MP_API_KEY is "your-mp-api-key".'
# ]

async def run_agent_with_tracking(agent, input_data: str, agent_name: str, step_number: int = None):
    """Run an agent and track execution with MLflow tracing."""
    print(f"🚀 Starting {agent_name}...")
    
    start_time = time.time()
    
    # Create a trace span for this agent
    span_name = f"{agent_name} (Step {step_number})" if step_number else agent_name
    with mlflow.start_span(name=span_name) as span:
        try:
            from agents import Runner
            runner = Runner()
            
            # Set basic span attributes
            span.set_attribute("agent.name", agent_name)
            span.set_attribute("agent.type", type(agent).__name__)
            span.set_attribute("agent.input_length", len(input_data))
            if step_number:
                span.set_attribute("step.number", step_number)
            
            # Let MLflow autolog handle tool discovery and logging automatically
            # Just set basic span attributes for agent identification
            span.set_inputs({
                "agent_input": input_data,
                "agent_name": agent_name,
                "agent_type": type(agent).__name__
            })
            
            # Run the agent
            result = await runner.run(agent, input_data, max_turns=1000)
            
            end_time = time.time()
            execution_time = end_time - start_time
            print(f"✅ {agent_name} completed in {execution_time:.2f}s")
            
            # Set completion attributes
            span.set_attribute("agent.execution_time_seconds", execution_time)
            span.set_attribute("agent.success", True)
            
            # Set basic outputs
            output = str(result.final_output) if hasattr(result, 'final_output') else str(result)
            span.set_outputs({
                "agent_output": output[:1000] + "..." if len(output) > 1000 else output,
                "execution_time_seconds": execution_time,
                "agent_name": agent_name
            })
            
            return result, start_time, end_time
            
        except Exception as e:
            end_time = time.time()
            execution_time = end_time - start_time
            print(f"❌ {agent_name} failed after {execution_time:.2f}s: {e}")
            
            # Set error attributes
            span.set_attribute("agent.execution_time_seconds", execution_time)
            span.set_attribute("agent.success", False)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))
            
            # Set error status
            span.set_status(status="ERROR")
            
            raise

async def materials_agent_workflow(user_query: str) -> FinalResult:
    """
    Main workflow orchestrating all agents with parallel debugging.
    Assumes MLflow run is already active.
    """
    print(f"\n{'='*80}")
    print("🚀 STARTING MATERIALS AGENT WORKFLOW")
    print(f"{'='*80}")
    
    # Reapply quiet mode to silence any loggers created during imports
    reapply_quiet_mode()
    
    # Create a trace span for the entire workflow
    with mlflow.start_span(name="Materials_Agent_Workflow") as workflow_span:
        # Log workflow start and parameters
        workflow_start_time = time.time()
        
        workflow_span.set_attribute("workflow.query_length", len(user_query))
        workflow_span.set_inputs({"user_query": user_query[:500] + "..." if len(user_query) > 500 else user_query})
        
        # Step 1: Solution Research
        print(f"\n{'🔬 STEP 1: SOLUTION RESEARCH'}")
        print("-" * 50)
        
        # Import and create solution researcher agent
        from deep_solver_benchmark.deep_solver.solution_researcher import create_solution_researcher_agent
        
        solution_researcher = await create_solution_researcher_agent()
        
        result, start_time, end_time = await run_agent_with_tracking(
            solution_researcher, user_query, "Solution Researcher", step_number=1
        )
        solution_response = result.final_output
        
        # Step 2: Code Execution
        print(f"\n{'⚡ STEP 2: CODE EXECUTION'}")
        print("-" * 50)
        
        # Import and create code agent
        from deep_solver_benchmark.deep_solver.code_agent import create_code_agent
        
        code_agent = await create_code_agent()
        
        # Prepare input for code agent based on solution research
        code_input = f"Original User Query: {user_query}\n\nSolution Research Results:\nRequired Packages: {solution_response.required_packages}\nCode Solution:\n{solution_response.code_solution}"
        
        result, start_time, end_time = await run_agent_with_tracking(
            code_agent, code_input, "Code Agent", step_number=2
        )
        execution_report = result.final_output
        
        # Check if debugging is needed
        if execution_report.needs_debugging:
            print(f"\n{'🔧 STEP 3: PARALLEL DEBUGGING'}")
            print("-" * 50)
            
            # Import and create debug agents
            from deep_solver_benchmark.deep_solver.debug_agent import create_debug_agents
            
            # Create three debug agents
            debug_agent_1, debug_agent_2, debug_agent_3 = await create_debug_agents()
            
            # Create debugging input
            debug_input = f"Original User Query: {user_query}\n\nSolution Research Results:\nRequired Packages: {solution_response.required_packages}\nCode Solution:\n{solution_response.code_solution}\n\nExecution Report:\nExecuted Code:\n{execution_report.executed_code}\nExecution Output:\n{execution_report.execution_output}\n\nDEBUGGING TASK: Fix the code to address the issues shown in the execution output."
            
            # Run debug agents in parallel
            try:
                print("🚀 Starting 3 parallel debug agents...")
                debug_tasks = [
                    run_agent_with_tracking(debug_agent_1, debug_input, "Debug Agent 1", step_number=3),
                    run_agent_with_tracking(debug_agent_2, debug_input, "Debug Agent 2", step_number=3),
                    run_agent_with_tracking(debug_agent_3, debug_input, "Debug Agent 3", step_number=3)
                ]
                
                # Wait for all debug agents (handle individual failures)
                debug_task_results = await asyncio.gather(*debug_tasks, return_exceptions=True)
                
                # Process results - filter out exceptions
                debug_results = []
                for i, task_result in enumerate(debug_task_results, 1):
                    if isinstance(task_result, Exception):
                        print(f"❌ Debug Agent {i} failed: {task_result}")
                    else:
                        result, start_time, end_time = task_result
                        debug_results.append(result.final_output)
                        print(f"✅ Debug Agent {i} completed successfully")
                
            except Exception as e:
                print(f"❌ Critical error in parallel debugging: {e}")
                debug_results = []
            
            if not debug_results:
                # No successful debug results
                print(f"❌ All debug agents failed - no successful debugging results")
                all_failed_by_exception = all(isinstance(tr, Exception) for tr in debug_task_results)
                return FinalResult(
                    original_user_query=user_query,
                    success=False,
                    final_code=execution_report.executed_code,
                    execution_results=(
                        "All debug agents failed due to exceptions" if all_failed_by_exception 
                        else "No successful debug results returned"
                    ),
                    processed_output="Workflow Failed"
                )
            
            print(f"✅ Parallel debugging completed - got {len(debug_results)} successful results")
            
            # Log parallel debugging results
            mlflow.log_param("parallel_debugging_enabled", True)
            mlflow.log_param("debug_agents_attempted", 3)
            mlflow.log_param("debug_agents_successful", len(debug_results))
            mlflow.log_param("debug_agents_failed", 3 - len(debug_results))
            
            # Step 4: Output Processing and Selection
            print(f"\n{'📊 STEP 4: OUTPUT PROCESSING AND SELECTION'}")
            print("-" * 50)
            
            # Import and create output processor agent
            from deep_solver_benchmark.deep_solver.output_processor_agent import create_output_processor_agent
            
            try:
                output_processor = await create_output_processor_agent()
                
                # Prepare input for output processor with available debug results
                processor_input = f"Original Query: {user_query}\n\n"
                for i, result in enumerate(debug_results, 1):
                    processor_input += f"DEBUG RESULT {i}:\nFinal Code:\n{result.final_code}\nExecution Output:\n{result.execution_output}\n\n"
                processor_input += "INSTRUCTIONS: Evaluate all debug results, select the best one that meets the user requirements, and process the output accordingly. If the best result still fails to meet requirements, output 'Failed' in processed_output."
                
                result, start_time, end_time = await run_agent_with_tracking(
                    output_processor, processor_input, "Output Processor", step_number=4
                )
                final_result = result.final_output
                print(f"🎯 Final Success: {final_result.success}")
                
            except Exception as e:
                print(f"❌ Output Processor failed: {e}")
                final_result = FinalResult(
                    original_user_query=user_query,
                    success=False,
                    final_code=debug_results[0].final_code if debug_results else execution_report.executed_code,
                    execution_results=f"Output Processor failed: {str(e)}",
                    processed_output="Workflow Failed"
                )
        
        else:
            print(f"\n{'✅ STEP 3: NO DEBUGGING NEEDED'}")
            print("-" * 50)
            
            # Log that no debugging was needed
            mlflow.log_param("parallel_debugging_enabled", False)
            mlflow.log_param("debug_agents_attempted", 0)
            mlflow.log_param("debug_agents_successful", 0)
            mlflow.log_param("debug_agents_failed", 0)
            
            # Step 4: Output Processing (successful execution)
            print(f"\n{'📊 STEP 4: OUTPUT PROCESSING'}")
            print("-" * 50)
            
            # Import and create output processor agent
            from deep_solver_benchmark.deep_solver.output_processor_agent import create_output_processor_agent
            
            try:
                output_processor = await create_output_processor_agent()
                
                # Prepare input for output processor with successful execution
                processor_input = f"Original Query: {user_query}\n\nSUCCESSFUL EXECUTION:\nFinal Code:\n{execution_report.executed_code}\nExecution Results:\n{execution_report.execution_output}"
                
                result, start_time, end_time = await run_agent_with_tracking(
                    output_processor, processor_input, "Output Processor", step_number=4
                )
                final_result = result.final_output
                print(f"🎯 Final Success: {final_result.success}")
                
            except Exception as e:
                print(f"❌ Output Processor failed: {e}")
                final_result = FinalResult(
                    original_user_query=user_query,
                    success=False,
                    final_code=execution_report.executed_code,
                    execution_results=f"Output Processor failed: {str(e)}",
                    processed_output="Workflow Failed"
                )
        
        import sys
        is_single_query = len(sys.argv) == 1 or '--batch' not in sys.argv
        is_called_as_module = __name__ != "__main__"
        if is_single_query and not is_called_as_module:
            print(f"\n{'='*80}")
            print("✅ WORKFLOW COMPLETED")
            print(f"{'='*80}")
            print(f"Success: {final_result.success}")
            print(f"===FINAL_PROCESSED_OUTPUT_START===")
            print(final_result.processed_output)
            print(f"===FINAL_PROCESSED_OUTPUT_END===")
        
        # Log final workflow results
        workflow_end_time = time.time()
        total_workflow_time = workflow_end_time - workflow_start_time
        
        mlflow.log_param("workflow_end_time", workflow_end_time)
        mlflow.log_metric("total_workflow_execution_time", total_workflow_time)
        mlflow.log_param("workflow_success", final_result.success)
        mlflow.log_param("needs_debugging", execution_report.needs_debugging if 'execution_report' in locals() else False)
        
        # Log workflow-level tool usage summary
        all_tool_names = []
        total_tool_calls = 0
        total_successful_tools = 0
        total_failed_tools = 0
        
        # Collect tool usage from all agents (if available in MLflow context)
        # This creates a comprehensive view of the entire workflow
        workflow_tools_summary = {
            "total_agents": 4 if execution_report.needs_debugging else 3,
            "debugging_enabled": execution_report.needs_debugging if 'execution_report' in locals() else False,
            "workflow_steps_completed": 4 if execution_report.needs_debugging else 3,
            "final_success": final_result.success
        }
        
        # Log a simple workflow summary (detailed report is handled by single_question_runner)
        workflow_summary = {
            "query": user_query,
            "total_duration": total_workflow_time,
            "success": final_result.success,
            "debugging_required": execution_report.needs_debugging if 'execution_report' in locals() else False,
            "steps_completed": 4 if execution_report.needs_debugging else 3
        }
        
        # Set workflow span outputs and final attributes
        workflow_span.set_attribute("workflow.execution_time", total_workflow_time)
        workflow_span.set_attribute("workflow.success", final_result.success)
        workflow_span.set_attribute("workflow.debugging_required", execution_report.needs_debugging if 'execution_report' in locals() else False)
        workflow_span.set_attribute("workflow.steps_completed", 4 if execution_report.needs_debugging else 3)
        
        workflow_span.set_outputs({
            "final_result": {
                "success": final_result.success,
                "processed_output": final_result.processed_output[:200] + "..." if len(final_result.processed_output) > 200 else final_result.processed_output,
                "execution_results": final_result.execution_results[:200] + "..." if len(final_result.execution_results) > 200 else final_result.execution_results
            }
        })
        
        return final_result

def record_failed_attempt(save_path, question_idx, question, rep, error_message, error_type="general", answer="N/A", tolerance="N/A"):
    """
    Record a failed attempt in the results file.
    
    Args:
        save_path: Either a directory path or a .json file path
    """
    import json
    import os
    from datetime import datetime
    
    failed_data = {
        "level_id": question_idx,
        "question": question,
        "repetition": rep,
        "timestamp": datetime.now().isoformat(),
        "answer": str(answer),
        "tolerance": str(tolerance),
        "processed_output": "Workflow Failed"
    }
    
    # Handle both directory paths and .json file paths
    if save_path.endswith('.json'):
        results_file = save_path
    else:
        results_file = os.path.join(save_path, "results.json")
    if os.path.exists(results_file):
        with open(results_file, "r") as f:
            all_results = json.load(f)
    else:
        all_results = []
    
    all_results.append(failed_data)
    
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"📁 Failed attempt recorded: Q{question_idx}_R{rep} -> {error_type}")

def clean_all_mcp_processes():
    """
    Clean MCP processes - first try registered PIDs, then fallback to psutil search.
    """
    import concurrent.futures
    
    # First try registered PIDs
    pids_to_kill = get_current_process_mcp_pids()
    
    # If no registered PIDs, try to find MCP processes using psutil
    if not pids_to_kill:
        found_pids = find_mcp_processes()
        if found_pids:
            print(f"🧹 Found {len(found_pids)} MCP processes using psutil: {found_pids}")
            pids_to_kill = found_pids
        else:
            print("🧹 No MCP processes found to clean")
            return
    
    print(f"🧹 Cleaning {len(pids_to_kill)} MCP processes: {pids_to_kill}")
    
    # Kill each process
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(kill_specific_process, pid, 3) for pid in pids_to_kill]
        concurrent.futures.wait(futures, timeout=5)
    
    # Clear the registered PIDs
    with _MCP_SERVER_LOCK:
        _MCP_SERVER_PIDS.clear()

def force_cleanup_all_mcp_processes():
    """
    Force cleanup MCP processes - first try registered PIDs, then fallback to psutil search.
    """
    import concurrent.futures
    
    # First try registered PIDs
    pids_to_kill = get_current_process_mcp_pids()
    
    # If no registered PIDs, try to find MCP processes using psutil
    if not pids_to_kill:
        found_pids = find_mcp_processes()
        if found_pids:
            print(f"🧹 Found {len(found_pids)} MCP processes using psutil for force cleanup: {found_pids}")
            pids_to_kill = found_pids
        else:
            print("🧹 No MCP processes found to force clean")
            return
    
    print(f"🧹 Force cleaning {len(pids_to_kill)} MCP processes: {pids_to_kill}")
    
    # Force kill each process
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(kill_specific_process, pid, 1) for pid in pids_to_kill]
        concurrent.futures.wait(futures, timeout=3)
    
    # Clear the registered PIDs
    with _MCP_SERVER_LOCK:
        _MCP_SERVER_PIDS.clear()

def clean_temp_code_directory():
    """
    Clean all files in the temp_code directory to prevent conflicts between runs.
    This removes all temporary files including external program outputs.
    """
    import shutil
    temp_code_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_code")
    if os.path.exists(temp_code_dir):
        try:
            # Remove all contents of the directory
            for filename in os.listdir(temp_code_dir):
                file_path = os.path.join(temp_code_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            pass
        except Exception as e:
            pass
    else:
        os.makedirs(temp_code_dir, exist_ok=True)

async def run_batch_questions(questions, results_file="results.json", repeat=3):
    """
    Run a batch of questions with full process isolation and MCP cleanup.
    Each run creates a unique timestamped directory.
    """
    from datetime import datetime
    
    # Create unique timestamped directory for this run
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_save_dir = os.path.join(results_file, f"{EXPERIMENT_NAME}_{timestamp}")
    os.makedirs(unique_save_dir, exist_ok=True)
    
    print(f"📁 Results will be saved to: {unique_save_dir}")
    print(f"📋 Running {len(questions)} questions, {repeat} repetitions each")
    try:
        for idx, question in enumerate(questions, 1):
            print(f"\n{'='*30} Question {idx} {'='*30}")
            print(question)
            for rep in range(1, repeat + 1):
                print(f"\n--- Repetition {rep}/{repeat} for Question {idx} ---")
                print("🧹 Pre-cleaning temp_code directory...")
                clean_temp_code_directory()
                # Note: MCP servers are now managed by MCPServerManager and will be reused
                time.sleep(1)
                cmd = [
                    sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "single_question_runner.py"),
                    "--question-idx", str(idx),
                    "--query", question,
                    "--rep", str(rep),
                    "--experiment-name", EXPERIMENT_NAME,
                    "--results-file", unique_save_dir,
                    "--expected-answer", "N/A",
                    "--tolerance", "N/A",
                    "--benchmark", "batch_mode"
                ]
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=False,
                        text=True,
                        timeout=1800,
                        cwd=os.getcwd(),
                        close_fds=True,  # Close file descriptors in child process
                        stdin=subprocess.DEVNULL 
                    )
                    if result.returncode == 0:
                        print(f"✅ Question {idx} repetition {rep} completed successfully")
                    else:
                        print(f"❌ Question {idx} repetition {rep} failed with return code {result.returncode}")
                        # Show error output for debugging (only when failed)
                        if result.stderr:
                            print(f"🚨 Error: {result.stderr[:500]}..." if len(result.stderr) > 500 else f"🚨 Error: {result.stderr}")
                        if result.stdout:
                            print(f"📄 Output: {result.stdout[:300]}..." if len(result.stdout) > 300 else f"📄 Output: {result.stdout}")
                        # Record non-zero exit as a failed attempt  
                        record_failed_attempt(unique_save_dir, idx, question, rep, f"Process exited with code {result.returncode}", "exit_code")
                except subprocess.TimeoutExpired:
                    print(f"⏰ Question {idx} repetition {rep} timed out after 30 minutes")
                    # Record timeout as a failed attempt
                    record_failed_attempt(unique_save_dir, idx, question, rep, "Timeout after 30 minutes", "timeout")
                except Exception as e:
                    print(f"❌ Question {idx} repetition {rep} failed with error: {e}")
                    # Record general exception as a failed attempt
                    record_failed_attempt(unique_save_dir, idx, question, rep, str(e), "exception")
                
                # MCP servers are now managed by MCPServerManager and will be reused
                # Only cleanup at the very end of all tests
                time.sleep(0.5)
                
                # Reset file descriptors to prevent leakage
                try:
                    import gc
                    gc.collect()
                except:
                    pass
    
    except KeyboardInterrupt:
        print("\n\n🛑 Batch run interrupted by user")
        print("🧹 Final cleanup of MCP servers...")
        await cleanup_mcp_servers()
    
    print(f"\n🎉 Batch run completed! Results saved to: {unique_save_dir}")
    return unique_save_dir

async def run_batch_questions_from_data(questions_data, results_file="results.json", repeat=3, benchmark_name=None):
    """
    Run a batch of questions from JSON data with full process isolation and MCP cleanup.
    Uses unified directory for all questions to accumulate results in one JSON file.
    """
    from datetime import datetime
    import os
    # Create directory for results file if it doesn't exist
    results_dir = os.path.dirname(results_file)
    if results_dir:  # Only create directory if there's a path
        os.makedirs(results_dir, exist_ok=True)
    num_entries = len(set((q['original_idx'] for q in questions_data)))
    print(f"📁 Results will be saved to: {results_file}")
    print(f"📋 Running {len(questions_data)} sub-questions (from {num_entries} original entries), {repeat} repetitions each")
    try:
        for idx, question_item in enumerate(questions_data, 1):
            original_idx = question_item['original_idx']
            question_idx = question_item['question_idx']
            query = question_item['query']
            output_type = question_item['output_type']
            unit = question_item['unit']
            answer = question_item.get('answer', 'N/A')
            tolerance = question_item.get('absolute_tolerance', 'N/A')
            question_id = original_idx + 1
            level = question_idx
            print(f"\n{'='*30} Question {question_id} (Level {level}) {'='*30}")
            print(f"Question ID: {question_id}, Level: {level}")
            print(f"Output Type: {output_type}")
            print(f"Unit: {unit}")
            print(f"Query: {query[:200]}...")
            for rep in range(1, repeat + 1):
                print(f"\n--- Repetition {rep}/{repeat} for Question {question_id} (Level {level}) ---")
                print("🧹 Pre-cleaning temp_code directory...")
                clean_temp_code_directory()
                # Note: MCP servers are now managed by MCPServerManager and will be reused
                time.sleep(1)
                cmd = [
                    sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "single_question_runner.py"),
                    "--question-idx", str(level),
                    "--query", query,
                    "--rep", str(rep),
                    "--experiment-name", EXPERIMENT_NAME,
                    "--results-file", results_file,
                    "--expected-answer", str(answer),
                    "--tolerance", str(tolerance),
                    "--benchmark", benchmark_name if benchmark_name else "unknown"
                ]
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=False,
                        text=True,
                        timeout=1800,
                        cwd=os.getcwd(),
                        close_fds=True, # Close file descriptors in child process
                        stdin=subprocess.DEVNULL  
                    )
                    if result.returncode == 0:
                        print(f"✅ Question {question_id} (Level {level}) repetition {rep} completed successfully")
                    else:
                        print(f"❌ Question {question_id} (Level {level}) repetition {rep} failed with return code {result.returncode}")
                        # Show error output for debugging (only when failed)
                        if result.stderr:
                            print(f"🚨 Error: {result.stderr[:500]}..." if len(result.stderr) > 500 else f"🚨 Error: {result.stderr}")
                        if result.stdout:
                            print(f"📄 Output: {result.stdout[:300]}..." if len(result.stdout) > 300 else f"📄 Output: {result.stdout}")
                        record_failed_attempt(results_file, int(level), query, rep, f"Process exited with code {result.returncode}", "exit_code", answer, tolerance)
                except subprocess.TimeoutExpired:
                    print(f"⏰ Question {question_id} (Level {level}) repetition {rep} timed out after 30 minutes")
                    record_failed_attempt(results_file, int(level), query, rep, "Timeout after 30 minutes", "timeout", answer, tolerance)
                except Exception as e:
                    print(f"❌ Question {question_id} (Level {level}) repetition {rep} failed with error: {e}")
                    record_failed_attempt(results_file, int(level), query, rep, str(e), "exception", answer, tolerance)
                # MCP servers are now managed by MCPServerManager and will be reused
                time.sleep(0.5)
                
                # Reset file descriptors to prevent leakage
                try:
                    import gc
                    gc.collect()
                except:
                    pass
    except KeyboardInterrupt:
        print("\n\n🛑 Batch run interrupted by user")
        print("🧹 Final cleanup of MCP servers...")
        await cleanup_mcp_servers()
    print(f"\n🎉 Batch run completed! Results saved to: {results_file}")
    return results_file



def main():
    """
    Parse command line arguments and run in either batch, benchmark test, or single-query mode.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", action="store_true", help="Run in batch mode with preset questions")
    parser.add_argument("--benchmark", type=str, help="Path to benchmark JSON file to test")

    parser.add_argument("--repeat", type=int, default=1, help="Number of repetitions (default: 1)")
    parser.add_argument('--results-file', type=str, help='Directory to save results (required for batch/benchmark mode)')
    args = parser.parse_args()
    
    if args.batch:
        if not args.results_file:
            print("❌ Error: --results-file is required for batch mode")
            return
        asyncio.run(run_batch_questions(QUESTIONS, args.results_file, args.repeat))
    elif args.benchmark:
        if not args.results_file:
            print("❌ Error: --results-file is required for benchmark mode")
            return
        print(f"🧪 Testing benchmark from {args.benchmark}")
        # Instead of test_benchmark_question, run all questions in the benchmark
        questions_data = load_questions_from_json(args.benchmark)
        if not questions_data:
            print("❌ No questions loaded from JSON file!")
            return
        asyncio.run(run_batch_questions_from_data(questions_data, args.results_file, args.repeat, args.benchmark))
    else:
        asyncio.run(async_single_query_main())

async def async_single_query_main():
    """
    Single-query mode: prompt user for query, run the parallel debugging workflow, and log results.
    """
    from datetime import datetime
    
    query = input("\n🤔 Enter your materials science query (press Enter when done): ").strip()
    
    # Clear Supabase tables and temp code before starting
    supabase_client = get_supabase_client()
    clear_supabase_tables(supabase_client)
    
    print("🧹 Cleaning temp_code directory...")
    clean_temp_code_directory()
    
    try:
        with mlflow.start_run(run_name=f"parallel_workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
            mlflow.log_param("query", query)
            mlflow.log_param("query_type", "materials_science")
            mlflow.log_param("workflow_type", "parallel_debugging")
            mlflow.log_param("tracking_enabled", True)
            
            try:
                # Run the new parallel debugging workflow
                final_result = await materials_agent_workflow(query)
                
                # Log results with consistent format
                output = f"""
WORKFLOW RESULTS:
================
Success: {final_result.success}
Original Query: {final_result.original_user_query}

Final Code:
-----------
{final_result.final_code}

Execution Results:
-----------------
{final_result.execution_results}

Processed Output:
----------------
{final_result.processed_output}

===FINAL_PROCESSED_OUTPUT_START===
{final_result.processed_output}
===FINAL_PROCESSED_OUTPUT_END===
"""
                
                print(f"\n{'='*80}")
                print("FINAL WORKFLOW OUTPUT")
                print(f"{'='*80}")
                print(output)
                
                # Single-query mode - no need to save to JSON file
                print(f"📁 Single-query mode - result not saved to file")
                
            except Exception as e:
                print(f"⚠️  Workflow error: {e}")
                output = f"❌ Workflow failed.\n\nError: {str(e)}\n\nTraceback:\n{traceback.format_exc()}\n\n===FINAL_PROCESSED_OUTPUT_START===\nWorkflow Failed\n===FINAL_PROCESSED_OUTPUT_END==="
                print(output)
                
                # Single-query mode - no need to save error to JSON file
                print(f"📁 Single-query mode - error not saved to file")
                
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during test: {str(e)}")
        print(traceback.format_exc())
        raise
    finally:
            print("🧹 Single-query session cleanup completed")

if __name__ == "__main__":
    """
    Main entrypoint. Supports both single-query and batch modes.
    Batch mode uses separate processes for each question to avoid MCP connection issues.
    """
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        # MCP servers are now managed by MCPServerManager
    except Exception as e:
        print(f"\nTest failed: {e}")
        # MCP servers are now managed by MCPServerManager
    finally:
        # MCP servers are now managed by MCPServerManager
        pass
