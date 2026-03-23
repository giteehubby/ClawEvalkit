#!/usr/bin/env python3
"""
Single question runner - executes one repetition of one question in isolation.
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

from utils.quiet_utils import setup_quiet_mode, silence_external_output, reapply_quiet_mode
from utils import get_supabase_client, clear_supabase_tables, retry_with_backoff, call_tool_with_retry

setup_quiet_mode()

import sys
import os
import asyncio
import logging
import traceback
import time
import argparse
from datetime import datetime

import mlflow

# MLflow configuration is handled in test_workflow.py to avoid duplication

async def run_single_question(question_idx, query, rep, experiment_name, results_file, expected_answer, tolerance, benchmark):
    """Run a single question repetition."""
    
    import os
    # Create directory for results file if it doesn't exist
    results_dir = os.path.dirname(results_file)
    if results_dir:  # Only create directory if there's a path
        os.makedirs(results_dir, exist_ok=True)
    
    # Clear Supabase tables before each question to ensure independent queries
    supabase_client = get_supabase_client()
    clear_supabase_tables(supabase_client)
    
    # Import the complete workflow function
    from test_workflow import materials_agent_workflow
    
    # Reapply quiet mode after imports to silence any newly created loggers
    reapply_quiet_mode()
    
    print("🔄 Starting complete materials agent workflow for this run...")
    
    mlflow.set_experiment(experiment_name)
    run_name = f"workflow_batch_q{question_idx}_rep{rep}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    with mlflow.start_run(run_name=run_name):
        mlflow.log_param("query", query)
        mlflow.log_param("query_type", "materials_science")
        mlflow.log_param("tracking_enabled", True)
        mlflow.log_param("repeat_index", rep)
        
        # Record start time for execution
        workflow_start_time = time.time()
        
        try:
            result = await materials_agent_workflow(query)
            
            # Calculate execution time
            workflow_end_time = time.time()
            execution_time = workflow_end_time - workflow_start_time
            # Ensure we have a proper FinalResult object
            if not hasattr(result, 'processed_output'):
                # If somehow we get an invalid result, treat as failure
                print("⚠️  Warning: Invalid result object, treating as failure")
                result_data = {
                    "level_id": question_idx,
                    "question": query,
                    "repetition": rep,
                    "timestamp": datetime.now().isoformat(),
                    "execution_time_seconds": execution_time,
                    "processed_output": "Workflow Failed",
                    "success": False,
                    "error": "Invalid result object returned",
                    "benchmark": benchmark
                }
            else:
                # Normal successful workflow result
                result_data = {
                    "level_id": question_idx,
                    "question": query,
                    "repetition": rep,
                    "timestamp": datetime.now().isoformat(),
                    "execution_time_seconds": execution_time,
                    "answer": str(expected_answer),
                    "tolerance": str(tolerance),
                    "processed_output": result.processed_output,
                    "benchmark": benchmark
                }
        except Exception as e:
            # Calculate execution time even for failures
            workflow_end_time = time.time()
            execution_time = workflow_end_time - workflow_start_time
            
            print(f"⚠️  Workflow failed: {e}")
            print(traceback.format_exc())
            # Always record failure as a result
            result_data = {
                "level_id": question_idx,
                "question": query,
                "repetition": rep,
                "timestamp": datetime.now().isoformat(),
                "execution_time_seconds": execution_time,
                "answer": str(expected_answer),
                "tolerance": str(tolerance),
                "processed_output": "Workflow Failed",
                "benchmark": benchmark
            }
            result = f"❌ Workflow failed.\n\nError: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        
        # Handle both FinalResult objects and string errors for display
        if hasattr(result, 'processed_output'):
            output = f"""
WORKFLOW RESULTS:
================
Success: {result.success}
Original Query: {result.original_user_query}

Final Code:
-----------
{result.final_code}

Execution Results:
-----------------
{result.execution_results}

===FINAL_PROCESSED_OUTPUT_START===
{result.processed_output}
===FINAL_PROCESSED_OUTPUT_END===
"""
        else:
            output = f"{str(result)}\n\n===FINAL_PROCESSED_OUTPUT_START===\nWorkflow Failed\n===FINAL_PROCESSED_OUTPUT_END==="
        
        print(f"\n{'='*80}\n🎯 FINAL OUTPUT\n{'='*80}\n{output}")
        
        # Use the result_data we already created (ensures all cases are recorded)
        import json
        
        # When saving results:
        # Use results_file directly
        if os.path.exists(results_file):
            with open(results_file, "r") as f:
                all_results = json.load(f)
        else:
            all_results = []
        
        all_results.append(result_data)

        with open(results_file, "w") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

        # Cleanup crawler/browser WITHIN async context to prevent hanging on exit
        try:
            from mcp_servers_and_tools.direct_tools.research_tools import cleanup_crawler
            await cleanup_crawler()
        except Exception:
            pass  # Ignore cleanup errors

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question-idx", type=int, required=True)
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--rep", type=int, required=True)
    parser.add_argument("--experiment-name", type=str, required=True)
    parser.add_argument("--results-file", type=str, required=True)
    parser.add_argument("--expected-answer", type=str, required=True)
    parser.add_argument("--tolerance", type=str, required=True)
    parser.add_argument("--benchmark", type=str, required=True)
    args = parser.parse_args()
    
    # Record start time for critical error handling
    main_start_time = time.time()
    
    try:
        await run_single_question(
            args.question_idx,
            args.query,
            args.rep,
            args.experiment_name,
            args.results_file,
            args.expected_answer,
            args.tolerance,
            args.benchmark
        )
    except Exception as e:
        print(f"❌ Critical error on question {args.question_idx} repetition {args.rep}: {e}")
        
        # Save critical error to consolidated JSON file (e.g., import errors, MLflow setup failures)
        import json
        import os
        from datetime import datetime
        
        # Record execution time for critical errors (time from start of main to error)
        critical_error_time = time.time()
        # Use actual time elapsed before critical error occurred
        execution_time = critical_error_time - main_start_time
        
        critical_error_data = {
            "level_id": args.question_idx,
            "question": args.query,
            "repetition": args.rep,
            "timestamp": datetime.now().isoformat(),
            "execution_time_seconds": execution_time,
            "answer": str(args.expected_answer),
            "tolerance": str(args.tolerance),
            "processed_output": "Workflow Failed",
            "benchmark": args.benchmark
        }
        
        # Append to results file
        results_file = args.results_file
        if os.path.exists(results_file):
            with open(results_file, "r") as f:
                all_results = json.load(f)
        else:
            all_results = []
        
        all_results.append(critical_error_data)
        
        with open(results_file, "w") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        
        print(f"📁 Critical error recorded to: {results_file}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSingle run interrupted by user")
        # MCP servers are now managed by MCPServerManager
    except Exception as e:
        print(f"\nSingle run failed: {e}")
        sys.exit(1)
    finally:
        # Explicitly cleanup crawler/browser to prevent hanging on exit
        try:
            from mcp_servers_and_tools.direct_tools.research_tools import cleanup_crawler
            asyncio.run(cleanup_crawler())
        except Exception:
            pass  # Ignore cleanup errors
