#!/usr/bin/env python3
"""
Claude Code Benchmark Runner - runs all questions from a benchmark JSON file.
Matches the behavior of test_workflow.py but uses Claude Code agent in Docker.
"""

import json
import os
import sys
import argparse
import subprocess
import fcntl
from pathlib import Path
from datetime import datetime

def load_questions_from_json(json_path):
    """
    Load questions from benchmark JSON file.
    Matches the format from test_workflow.py
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        questions = []
        for idx, entry in enumerate(data):
            user_queries = entry.get('user_query', {})
            output_type = entry.get('output_type', '')
            unit = entry.get('unit', '')

            # Process both question levels (0 and 1) if they exist and are non-empty
            for q_idx in ['0', '1']:
                if q_idx in user_queries:
                    base_query = user_queries[q_idx]
                    if not base_query or not base_query.strip():
                        continue  # skip empty queries

                    # Extract the specific tolerance for this question level
                    tolerance = entry.get('absolute_tolerance', 'N/A')
                    if isinstance(tolerance, dict):
                        tolerance = tolerance.get(q_idx, 'N/A')

                    questions.append({
                        'original_idx': idx,
                        'question_idx': q_idx,
                        'query': base_query,
                        'output_type': output_type,
                        'unit': unit,
                        'answer': entry.get('answer', 'N/A'),
                        'absolute_tolerance': tolerance,
                        'benchmark': json_path
                    })

        return questions
    except Exception as e:
        print(f"❌ Error loading questions from JSON: {e}")
        return []

def run_single_question(question_file, question_index, query_level, model, repetition, results_file, detail_log_file=None, enable_tracing=False, trace_dir="test_tracing"):
    """
    Run a single question using run_isolated_test.sh

    Args:
        question_file: Path to benchmark JSON file
        question_index: Index of the question in the benchmark
        query_level: "0" or "1" for question difficulty
        model: Claude model name
        repetition: Repetition number (1, 2, 3, ...)
        results_file: Path to save results
        detail_log_file: Path to detailed log file (if None, creates agent_logs)
        enable_tracing: Enable detailed tracing
        trace_dir: Directory to save trace files
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    runner_script = os.path.join(script_dir, "run_isolated_test.sh")

    # Ensure results directory exists
    results_dir = os.path.dirname(results_file)
    if results_dir:
        os.makedirs(results_dir, exist_ok=True)

    # Determine if we should create agent log (false when detail_log_file is provided)
    create_agent_log = "true" if detail_log_file is None else "false"

    cmd = [
        runner_script,
        question_file,
        str(question_index),
        query_level,
        model,
        str(repetition),
        create_agent_log,  # Parameter 6: create agent log
        results_file,  # Parameter 7: results file path
        "true" if enable_tracing else "false",  # Parameter 8: enable tracing
        trace_dir  # Parameter 9: trace directory
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minutes
            cwd=script_dir
        )

        # Capture full output (script output + agent output)
        full_output = result.stdout
        if result.stderr:
            full_output += "\n=== STDERR ===\n" + result.stderr

        # If detail log file is provided, append the output with file lock
        if detail_log_file:
            lock_file = detail_log_file + '.lock'
            try:
                with open(lock_file, 'w') as lock_f:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)

                    with open(detail_log_file, 'a', encoding='utf-8') as log_f:
                        log_f.write(f"\n{'='*80}\n")
                        log_f.write(f"Question Index: {question_index} | Level: {query_level} | Repetition: {repetition}\n")
                        log_f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                        log_f.write(f"{'='*80}\n")
                        log_f.write(full_output)
                        log_f.write(f"\n{'='*80}\n\n")

                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                print(f"⚠️  Warning: Failed to write to detail log: {e}")

        print(f"Question {question_index} (Level {query_level}) Rep {repetition} completed")
        return True

    except subprocess.TimeoutExpired:
        print(f"⏰ Question {question_index} (Level {query_level}) Rep {repetition} timed out (30 min)")

        # Log timeout to detail log
        if detail_log_file:
            try:
                with open(detail_log_file + '.lock', 'w') as lock_f:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
                    with open(detail_log_file, 'a', encoding='utf-8') as log_f:
                        log_f.write(f"\n{'='*80}\n")
                        log_f.write(f"Question Index: {question_index} | Level: {query_level} | Repetition: {repetition}\n")
                        log_f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                        log_f.write(f"{'='*80}\n")
                        log_f.write(f"ERROR: Timeout (30 minutes exceeded)\n")
                        log_f.write(f"{'='*80}\n\n")
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
            except:
                pass

        # Create a timeout result record and append to results file
        try:
            # Load question to get details
            with open(question_file, 'r') as f:
                benchmark_data = json.load(f)
                question_entry = benchmark_data[question_index]
                question_text = question_entry['user_query'].get(query_level, 'Unknown question')
                answer = question_entry.get('answer', 'N/A')
                tolerance = question_entry.get('absolute_tolerance', 'N/A')

                # Get the specific tolerance for this level
                if isinstance(tolerance, dict):
                    tolerance = tolerance.get(query_level, 'N/A')

            timeout_result = {
                "level_id": int(query_level),
                "question": question_text,
                "repetition": repetition,
                "timestamp": datetime.now().isoformat(),
                "execution_time_seconds": 1800.0,  # 30 minutes
                "processed_output": "Workflow Failed",
                "answer": json.dumps(answer),
                "tolerance": json.dumps(tolerance),
                "benchmark": question_file
            }

            # Append to results file with file lock
            lock_file = results_file + '.lock'
            with open(lock_file, 'w') as lock_f:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)

                # Read existing results
                if os.path.exists(results_file):
                    with open(results_file, 'r') as f:
                        results = json.load(f)
                else:
                    results = []

                # Append new result
                results.append(timeout_result)

                # Write back
                with open(results_file, 'w') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)

                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            print(f"⚠️  Warning: Failed to create timeout result record: {e}")

        return True
    except Exception as e:
        print(f"⚠️  Question {question_index} (Level {query_level}) Rep {repetition} error: {e}")

        # Log error to detail log
        if detail_log_file:
            try:
                with open(detail_log_file + '.lock', 'w') as lock_f:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
                    with open(detail_log_file, 'a', encoding='utf-8') as log_f:
                        log_f.write(f"\n{'='*80}\n")
                        log_f.write(f"Question Index: {question_index} | Level: {query_level} | Repetition: {repetition}\n")
                        log_f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                        log_f.write(f"{'='*80}\n")
                        log_f.write(f"ERROR: {str(e)}\n")
                        log_f.write(f"{'='*80}\n\n")
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
            except:
                pass

        # Create an error result record and append to results file
        try:
            # Load question to get details
            with open(question_file, 'r') as f:
                benchmark_data = json.load(f)
                question_entry = benchmark_data[question_index]
                question_text = question_entry['user_query'].get(query_level, 'Unknown question')
                answer = question_entry.get('answer', 'N/A')
                tolerance = question_entry.get('absolute_tolerance', 'N/A')

                # Get the specific tolerance for this level
                if isinstance(tolerance, dict):
                    tolerance = tolerance.get(query_level, 'N/A')

            error_result = {
                "level_id": int(query_level),
                "question": question_text,
                "repetition": repetition,
                "timestamp": datetime.now().isoformat(),
                "execution_time_seconds": 0.0,
                "processed_output": "Workflow Failed",
                "answer": json.dumps(answer),
                "tolerance": json.dumps(tolerance),
                "benchmark": question_file
            }

            # Append to results file with file lock
            lock_file = results_file + '.lock'
            with open(lock_file, 'w') as lock_f:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)

                # Read existing results
                if os.path.exists(results_file):
                    with open(results_file, 'r') as f:
                        results = json.load(f)
                else:
                    results = []

                # Append new result
                results.append(error_result)

                # Write back
                with open(results_file, 'w') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)

                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        except Exception as write_err:
            print(f"⚠️  Warning: Failed to create error result record: {write_err}")

        return True

def main():
    parser = argparse.ArgumentParser(description="Claude Code Benchmark Runner")
    parser.add_argument("--benchmark", type=str, required=True,
                        help="Path to benchmark JSON file")
    parser.add_argument("--repeat", type=int, default=3,
                        help="Number of repetitions per question (default: 3)")
    parser.add_argument("--results-file", type=str, required=True,
                        help="Path to save results JSON file")
    parser.add_argument("--detail-log-dir", type=str, default=None,
                        help="Directory to save detailed log files (default: same as results)")
    parser.add_argument("--model", type=str, default="claude-sonnet-4-5",
                        help="Claude model to use (default: claude-sonnet-4-5)")
    parser.add_argument("--parallel", type=int, default=0,
                        help="Number of parallel workers (0 = sequential, default: 0)")
    parser.add_argument("--enable-tracing", action="store_true",
                        help="Enable detailed tracing of agent execution")
    parser.add_argument("--trace-dir", type=str, default=None,
                        help="Directory to save trace files (default: test_tracing/trace_<timestamp>)")

    args = parser.parse_args()

    # Determine trace directory
    if args.enable_tracing:
        if args.trace_dir:
            trace_dir = args.trace_dir
        else:
            # Create timestamp-based trace directory matching results
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trace_dir = f"test_tracing/trace_{timestamp}"
        os.makedirs(trace_dir, exist_ok=True)
    else:
        trace_dir = "test_tracing"  # Will not be used if tracing is disabled

    print(f"\n{'='*80}")
    print(f"Claude Code Benchmark: {os.path.basename(args.benchmark)}")
    print(f"{'='*80}")
    print(f"Benchmark file: {args.benchmark}")
    print(f"Repetitions: {args.repeat}")
    print(f"Results file: {args.results_file}")
    print(f"Model: {args.model}")
    print(f"Parallel workers: {args.parallel if args.parallel > 0 else 'Sequential'}")
    if args.enable_tracing:
        print(f"Tracing: Enabled ({trace_dir})")
    print(f"{'='*80}\n")

    # Create detailed log file
    if args.detail_log_dir:
        # Use specified log directory
        benchmark_name = os.path.basename(args.results_file).replace('.json', '')
        detail_log_file = os.path.join(args.detail_log_dir, f"{benchmark_name}_detail.log")
    else:
        # Default: same directory as results file
        detail_log_file = args.results_file.replace('.json', '_detail.log')

    print(f"📝 Detailed log: {detail_log_file}\n")

    # Initialize detail log file with header
    with open(detail_log_file, 'w', encoding='utf-8') as f:
        f.write(f"{'='*80}\n")
        f.write(f"Claude Code Detailed Log - {os.path.basename(args.benchmark)}\n")
        f.write(f"{'='*80}\n")
        f.write(f"Benchmark: {args.benchmark}\n")
        f.write(f"Model: {args.model}\n")
        f.write(f"Repetitions: {args.repeat}\n")
        f.write(f"Parallel workers: {args.parallel if args.parallel > 0 else 'Sequential'}\n")
        f.write(f"Started: {datetime.now().isoformat()}\n")
        f.write(f"{'='*80}\n\n")

    # Load questions
    questions = load_questions_from_json(args.benchmark)
    if not questions:
        print("❌ No questions loaded from benchmark file!")
        return 1

    num_entries = len(set((q['original_idx'] for q in questions)))
    print(f"📋 Loaded {len(questions)} sub-questions from {num_entries} original entries")
    print(f"📋 Total runs: {len(questions)} questions × {args.repeat} repetitions = {len(questions) * args.repeat} runs")
    print("")

    # Run each question with repetitions
    if args.parallel > 0:
        # Parallel execution using ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, as_completed

        print(f"🚀 Running with {args.parallel} parallel workers\n")

        # Build task list
        tasks = []
        for idx, question_item in enumerate(questions, 1):
            original_idx = question_item['original_idx']
            question_idx = question_item['question_idx']
            query = question_item['query']

            for rep in range(1, args.repeat + 1):
                tasks.append((args.benchmark, original_idx, question_idx, args.model, rep, args.results_file, detail_log_file, args.enable_tracing, trace_dir))

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(run_single_question, *task): task
                for task in tasks
            }

            for future in as_completed(futures):
                task = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"⚠️  Task exception: {e}")

    else:
        # Sequential execution
        print(f"📝 Running sequentially\n")

        for idx, question_item in enumerate(questions, 1):
            original_idx = question_item['original_idx']
            question_idx = question_item['question_idx']
            query = question_item['query']

            print(f"\n{'='*80}")
            print(f"Question {idx}/{len(questions)}: Entry {original_idx} Level {question_idx}")
            print(f"{'='*80}")
            print(f"Query: {query[:150]}...")
            print("")

            for rep in range(1, args.repeat + 1):
                print(f"--- Repetition {rep}/{args.repeat} ---")

                run_single_question(
                    question_file=args.benchmark,
                    question_index=original_idx,  # Use original index for benchmark lookup
                    query_level=question_idx,
                    model=args.model,
                    repetition=rep,
                    results_file=args.results_file,
                    detail_log_file=detail_log_file,
                    enable_tracing=args.enable_tracing,
                    trace_dir=trace_dir
                )

    print(f"\n{'='*80}")
    print(f"Benchmark Completed!")
    print(f"{'='*80}")
    print(f"Results saved to: {args.results_file}")
    print(f"Detailed log saved to: {detail_log_file}")
    print(f"{'='*80}\n")

    return 0

if __name__ == "__main__":
    sys.exit(main())
