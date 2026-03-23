#!/usr/bin/env python3
"""
Claude Code Runner for Materials Science Benchmark

This script runs Claude Code agent in complete isolation to answer benchmark questions.
- Runs in Docker container with tmpfs (no persistent storage in /tmp)
- Cannot access benchmark answers or previous results
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from pathlib import Path
import re

async def run_claude_code_agent(base_query: str, output_type: str, unit: str, query_level: str, model: str, enable_tracing: bool = False):
    """
    Run Claude Code agent on a benchmark question.

    Args:
        base_query: The question text
        output_type: Expected output type (e.g., "float", "int", "list")
        unit: Unit for the answer (e.g., "eV", "Å")
        query_level: "0" or "1" for question difficulty level
        model: Claude model name (e.g., "claude-sonnet-4-5")
        enable_tracing: Whether to collect detailed tracing information

    Returns:
        Tuple of (result_dict, full_log_text, trace_data or None)
    """
    from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

    # Build enhanced query
    enhanced_query = f"{base_query} You MUST provide the successful code solution and the execution result. Importantly, you MUST output a final answer according to the execution result in the format of {output_type}, considering the unit {unit} (if any). But you should NOT output unit in the answer. CRITICAL FORMAT REQUIREMENTS: Your final answer must use standard Python data types only (int, float, list, str) - do NOT use numpy array format like 'array([...])'. All lists should be in standard Python list format like [1.2, 3.4, 5.6]. The shape information in the output_type is for your reference to ensure correct dimensions."

    # Create temporary workspace in tmpfs
    workspace_dir = Path(f"/tmp/claude_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Configure agent to work in isolated tmpfs environment
    system_prompt = """You are a materials science and chemistry expert. Answer the user's question based on the provided information, your knowledge, and your available tools. You should identify the most useful tools and use them to solve the user's question

IMPORTANT CONSTRAINTS:
- You are not allowed to call tools infinitely. You should make structured output once you have the solution or you have tried your best to solve the question but you still cannot solve it
- If you encounter the same error repeatedly or are stuck in a debugging loop, recognize this and give up instead of continuing indefinitely
- If you still cannot solve the question after your best effort, you MUST output the structured response with the following format: { "original_user_query": "exact text of the user's query", "success": false, "final_code": "# The final code with all imports and logic (even though it might still have errors or does not meet the user's requirements)", "execution_results": "Raw execution output (even though it might still show errors or does not meet the user's requirements)", "processed_output": "Failed" }. Note: For the processed_output field, you MUST output "Failed" (exactly this word, nothing else)
- Your code MUST include environment variable setup where needed (e.g., os.getenv("MP_API_KEY") for Materials Project queries. Note: this is not provided in the user query but are stored in the environment variables exactly called 'MP_API_KEY')
- When using MPRester, you MUST use the code 'from mp_api.client import MPRester' with os.getenv('MP_API_KEY') instead of 'from pymatgen.ext.matproj import MPRester'

REQUIRED OUTPUT FORMAT:
At the end, output a single JSON object with these exact fields (do NOT output something else):
{
  "original_user_query": "exact text of the user's query",
  "success": true or false (boolean),
  "final_code": "# The final working code with all imports and logic",
  "execution_results": "Raw execution output and results",
  "processed_output": "The final answer - this is the key field for automated evaluation. Please output the final answer in the exact format specified in the user's query, or Failed if you cannot solve the question after your best effort"
}
"""

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        cwd=str(workspace_dir),           # Working directory in tmpfs
        model=model,                      # Claude model to use
        permission_mode='bypassPermissions',  # Allow file operations in tmpfs
        max_turns=1000
    )

    start_time = datetime.now()

    # Initialize variables for error handling
    processed_output = None
    full_output = ""
    result_message = None
    trace_data = None

    try:
        # Use ClaudeSDKClient for better connection management (similar to SciLeoAgent)
        messages = []

        async def run_with_client():
            async with ClaudeSDKClient(options=options) as client:
                # Send the query
                await client.query(enhanced_query)

                # Receive responses
                async for message in client.receive_response():
                    messages.append(message)

                    # Optional: print message content for debugging
                    if hasattr(message, 'content'):
                        for block in message.content:
                            if hasattr(block, 'text'):
                                # Can add debug logging here if needed
                                pass

        # Wrap in timeout (30 minutes = 1800 seconds)
        await asyncio.wait_for(run_with_client(), timeout=1800)

        # Build detailed trace log if tracing is enabled
        if enable_tracing:
            trace_lines = []
            trace_lines.append("="*80)
            trace_lines.append(f"TRACING LOG - {datetime.now().isoformat()}")
            trace_lines.append("="*80)
            trace_lines.append(f"Question: {base_query}")
            trace_lines.append(f"Query Level: {query_level}")
            trace_lines.append(f"Model: {model}")
            trace_lines.append(f"Start Time: {start_time.isoformat()}")
            trace_lines.append("="*80)
            trace_lines.append("")
            trace_lines.append(f"Total Messages Collected: {len(messages)}")
            trace_lines.append("")

            for idx, msg in enumerate(messages):
                msg_type = type(msg).__name__
                trace_lines.append(f"\n{'='*80}")
                trace_lines.append(f"Message {idx + 1}/{len(messages)} - Type: {msg_type}")
                trace_lines.append(f"{'='*80}")

                # Extract different message attributes based on type
                if hasattr(msg, 'role'):
                    trace_lines.append(f"Role: {msg.role}")

                if hasattr(msg, 'content'):
                    trace_lines.append(f"\nContent:")
                    trace_lines.append(f"{'-'*40}")
                    trace_lines.append(str(msg.content))
                    trace_lines.append(f"{'-'*40}")

                if hasattr(msg, 'tool_name'):
                    trace_lines.append(f"\nTool Name: {msg.tool_name}")

                if hasattr(msg, 'tool_input'):
                    trace_lines.append(f"\nTool Input:")
                    trace_lines.append(f"{'-'*40}")
                    trace_lines.append(str(msg.tool_input))
                    trace_lines.append(f"{'-'*40}")

                if hasattr(msg, 'tool_output'):
                    trace_lines.append(f"\nTool Output:")
                    trace_lines.append(f"{'-'*40}")
                    trace_lines.append(str(msg.tool_output))
                    trace_lines.append(f"{'-'*40}")

                if hasattr(msg, 'result'):
                    trace_lines.append(f"\nResult:")
                    trace_lines.append(f"{'-'*40}")
                    trace_lines.append(str(msg.result))
                    trace_lines.append(f"{'-'*40}")

                if hasattr(msg, 'error'):
                    trace_lines.append(f"\n⚠️ ERROR:")
                    trace_lines.append(f"{'-'*40}")
                    trace_lines.append(str(msg.error))
                    trace_lines.append(f"{'-'*40}")

            trace_data = "\n".join(trace_lines)

        # Look for ResultMessage only (the final message type)
        for msg in messages:
            msg_type = type(msg).__name__
            if msg_type == "ResultMessage":
                result_message = msg
                break

        # Extract processed_output from ResultMessage
        # ResultMessage has a 'result' field which is a string containing the agent's final output
        if result_message and hasattr(result_message, 'result'):
            full_output = result_message.result

            # Extract JSON from markdown code blocks (```json ... ```)
            json_code_block_pattern = r'```json\s*\n(.*?)\n```'
            code_block_matches = re.finditer(json_code_block_pattern, full_output, re.DOTALL)

            for match in code_block_matches:
                try:
                    result_json = json.loads(match.group(1))
                    if 'processed_output' in result_json:
                        processed_output = result_json['processed_output']
                        break
                except:
                    continue

        # If extraction failed (no ResultMessage or no valid JSON), mark as "Failed"
        if processed_output is None:
            processed_output = "Failed"

        # Convert processed_output to string for benchmark evaluator compatibility
        # The evaluator expects string format and will parse it back to native types
        if not isinstance(processed_output, str):
            processed_output = json.dumps(processed_output, ensure_ascii=False)

    except asyncio.TimeoutError:
        # Timeout (30 minutes exceeded)
        processed_output = "Workflow Failed"
        full_output = "Error: Workflow timeout (30 minutes exceeded)"
        if enable_tracing and trace_data:
            trace_data += f"\n\n{'='*80}\n⚠️ TIMEOUT ERROR\n{'='*80}\n"
            trace_data += "Workflow timeout (30 minutes exceeded)\n"

    except Exception as e:
        # System error
        processed_output = "Workflow Failed"
        full_output = f"Error: {str(e)}"
        if enable_tracing and trace_data:
            trace_data += f"\n\n{'='*80}\n⚠️ EXCEPTION ERROR\n{'='*80}\n"
            trace_data += f"{str(e)}\n"

    # Calculate execution time
    execution_time = (datetime.now() - start_time).total_seconds()

    # Add execution metadata to trace
    if enable_tracing and trace_data:
        trace_data += f"\n\n{'='*80}\n"
        trace_data += f"EXECUTION SUMMARY\n"
        trace_data += f"{'='*80}\n"
        trace_data += f"End Time: {datetime.now().isoformat()}\n"
        trace_data += f"Execution Time: {execution_time:.2f} seconds\n"
        trace_data += f"Processed Output: {processed_output}\n"
        trace_data += f"{'='*80}\n"

    # Build result dictionary (matching your benchmark format)
    result = {
        "level_id": int(query_level),
        "question": base_query,
        "repetition": 1,  # Will be overwritten by run_isolated_test.sh
        "timestamp": datetime.now().isoformat(),
        "execution_time_seconds": execution_time,
        "processed_output": processed_output,
        # answer, tolerance, benchmark will be added by run_isolated_test.sh
    }

    # Build log (just the final output from agent)
    log_text = f"""{"="*80}
Claude Code Baseline Run - {datetime.now().isoformat()}
{"="*80}
Question: {base_query}
Query Level: {query_level}
Model: {model}
{"="*80}

AGENT OUTPUT:
{full_output}

{"="*80}
FINAL RESULT
{"="*80}
Processed Output: {processed_output}
Execution Time: {execution_time:.2f}s
{"="*80}
"""

    # Output result as JSON with markers for host script to parse
    print("\n" + "="*80)
    print("CLAUDE_CODE_RESULT_START")
    print(json.dumps(result, indent=2))
    print("CLAUDE_CODE_RESULT_END")
    print("="*80)

    # Output trace data if tracing is enabled
    if enable_tracing and trace_data:
        print("\n" + "="*80)
        print("CLAUDE_CODE_TRACE_START")
        print(trace_data)
        print("CLAUDE_CODE_TRACE_END")
        print("="*80)

    return result, log_text, trace_data

async def main():
    """
    Main entry point - parses command line arguments and runs agent.

    Called by run_isolated_test.sh from inside Docker container.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Claude Code Runner for Materials Science Benchmark")
    parser.add_argument("--query", required=True, help="The question text")
    parser.add_argument("--output-type", default="", help="Expected output type (e.g., float, int, list)")
    parser.add_argument("--unit", default="", help="Unit for the answer")
    parser.add_argument("--query-level", default="1", choices=["0", "1"],
                        help="Question difficulty level (0=easier, 1=harder)")
    parser.add_argument("--model", default="claude-sonnet-4-5",
                        help="Claude model to use")
    parser.add_argument("--enable-tracing", action="store_true",
                        help="Enable detailed tracing of agent execution")

    args = parser.parse_args()

    # Run agent and get result + log
    result, log_text, trace_data = await run_claude_code_agent(
        base_query=args.query,
        output_type=args.output_type,
        unit=args.unit,
        query_level=args.query_level,
        model=args.model,
        enable_tracing=args.enable_tracing
    )

    # Print log to stdout (will be saved by run_isolated_test.sh)
    print("\n" + "="*80)
    print("CLAUDE_CODE_LOG_START")
    print(log_text)
    print("CLAUDE_CODE_LOG_END")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
