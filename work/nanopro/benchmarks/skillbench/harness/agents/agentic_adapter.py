#!/usr/bin/env python3
"""
Agentic Adapter for SkillBench

A bounded, multi-turn agent that can read/write files and run commands.
Designed for reproducibility and safety with hard limits.

Version: 0.2.0
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from harness.agents.http_utils import build_ssl_context

# =============================================================================
# Configuration
# =============================================================================

ADAPTER_VERSION = "0.2.0"

@dataclass
class AgentConfig:
    """Hard limits and settings for the agentic loop."""
    max_steps: int = 15              # Max agentic iterations
    max_tool_calls: int = 50         # Total tool calls across all steps
    max_wall_time_s: float = 180.0   # Wall clock timeout (3 minutes)
    max_bash_time_s: float = 30.0    # Per-bash-command timeout
    temperature: float = 0.0         # Deterministic
    max_tokens: int = 4096           # Per-response token limit
    model: str = "claude-sonnet-4-20250514"


# =============================================================================
# Tool Definitions
# =============================================================================

TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file. Returns the file content as a string.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file (relative to repo root)"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file (relative to repo root)"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_directory",
        "description": "List files and directories in a path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to list (relative to repo root, defaults to '.')"
                }
            },
            "required": []
        }
    },
    {
        "name": "run_tests",
        "description": "Run the test suite. Returns test output and pass/fail status.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "done",
        "description": "Signal that you have completed the task. Call this when you believe the fix is complete and tests pass.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what you changed"
                }
            },
            "required": ["summary"]
        }
    }
]


# =============================================================================
# Tool Execution
# =============================================================================

@dataclass
class ExecutionState:
    """Track execution state and limits."""
    repo_path: pathlib.Path
    config: AgentConfig
    start_time: float = field(default_factory=time.time)
    steps: int = 0
    tool_calls: int = 0
    done: bool = False
    done_summary: str = ""
    traces: list = field(default_factory=list)
    files_modified: set = field(default_factory=set)
    # Token tracking for cost estimation
    input_tokens: int = 0
    output_tokens: int = 0

    def check_limits(self) -> str | None:
        """Return error message if limits exceeded, None otherwise."""
        elapsed = time.time() - self.start_time
        if elapsed > self.config.max_wall_time_s:
            return f"Wall time limit exceeded ({elapsed:.1f}s > {self.config.max_wall_time_s}s)"
        if self.steps > self.config.max_steps:
            return f"Step limit exceeded ({self.steps} > {self.config.max_steps})"
        if self.tool_calls > self.config.max_tool_calls:
            return f"Tool call limit exceeded ({self.tool_calls} > {self.config.max_tool_calls})"
        return None


def execute_tool(name: str, args: dict, state: ExecutionState) -> str:
    """Execute a tool and return the result."""
    state.tool_calls += 1

    # Record trace
    trace_entry = {
        "tool": name,
        "args": args,
        "timestamp": time.time() - state.start_time,
    }

    try:
        if name == "read_file":
            result = _tool_read_file(args, state)
        elif name == "write_file":
            result = _tool_write_file(args, state)
        elif name == "list_directory":
            result = _tool_list_directory(args, state)
        elif name == "run_tests":
            result = _tool_run_tests(args, state)
        elif name == "done":
            result = _tool_done(args, state)
        else:
            result = f"Unknown tool: {name}"

        trace_entry["result"] = result[:500] if len(result) > 500 else result
        trace_entry["success"] = True
    except Exception as e:
        result = f"Error: {e}"
        trace_entry["result"] = result
        trace_entry["success"] = False

    state.traces.append(trace_entry)
    return result


def _tool_read_file(args: dict, state: ExecutionState) -> str:
    path = state.repo_path / args.get("path", "")
    if not path.exists():
        return f"File not found: {args.get('path')}"
    if not path.is_file():
        return f"Not a file: {args.get('path')}"
    # Safety: don't read files outside repo
    try:
        path.resolve().relative_to(state.repo_path.resolve())
    except ValueError:
        return "Error: Cannot read files outside repository"
    content = path.read_text(encoding="utf-8", errors="replace")
    if len(content) > 50000:
        return content[:50000] + "\n... (truncated)"
    return content


def _tool_write_file(args: dict, state: ExecutionState) -> str:
    path = state.repo_path / args.get("path", "")
    content = args.get("content", "")
    # Safety: don't write files outside repo
    try:
        path.resolve().relative_to(state.repo_path.resolve())
    except ValueError:
        return "Error: Cannot write files outside repository"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    state.files_modified.add(str(args.get("path")))
    return f"Wrote {len(content)} bytes to {args.get('path')}"


def _tool_list_directory(args: dict, state: ExecutionState) -> str:
    path = state.repo_path / args.get("path", ".")
    if not path.exists():
        return f"Directory not found: {args.get('path', '.')}"
    if not path.is_dir():
        return f"Not a directory: {args.get('path', '.')}"
    try:
        path.resolve().relative_to(state.repo_path.resolve())
    except ValueError:
        return "Error: Cannot list directories outside repository"

    items = []
    for item in sorted(path.iterdir()):
        suffix = "/" if item.is_dir() else ""
        items.append(f"{item.name}{suffix}")
    return "\n".join(items) if items else "(empty directory)"


def _tool_run_tests(args: dict, state: ExecutionState) -> str:
    # Look for test command in TASK.md or use default
    test_cmd = os.environ.get(
        "SKILLBENCH_TEST_CMD",
        "python3 -m unittest discover -s tests -p 'test_*.py'"
    )

    try:
        proc = subprocess.run(
            test_cmd,
            shell=True,
            cwd=state.repo_path,
            capture_output=True,
            text=True,
            timeout=state.config.max_bash_time_s,
        )
        output = proc.stdout + proc.stderr
        if proc.returncode == 0:
            return f"Tests PASSED\n\n{output}"
        else:
            return f"Tests FAILED (exit code {proc.returncode})\n\n{output}"
    except subprocess.TimeoutExpired:
        return f"Tests timed out after {state.config.max_bash_time_s}s"
    except Exception as e:
        return f"Error running tests: {e}"


def _tool_done(args: dict, state: ExecutionState) -> str:
    state.done = True
    state.done_summary = args.get("summary", "")
    return "Task marked as complete."


# =============================================================================
# API Client
# =============================================================================

def call_anthropic_api(
    messages: list[dict],
    config: AgentConfig,
    system: str | None = None,
) -> dict:
    """Make a request to the Anthropic API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    api_url = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
    version = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")

    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required")

    model = os.environ.get("SKILLBENCH_AGENT_MODEL", config.model)

    payload = {
        "model": model,
        "max_tokens": config.max_tokens,
        "messages": messages,
        "tools": TOOLS,
        "temperature": config.temperature,
    }
    if system:
        payload["system"] = system

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": version,
        },
        method="POST",
    )

    timeout = float(os.environ.get("SKILLBENCH_AGENT_REQUEST_TIMEOUT", "120"))

    with urllib.request.urlopen(req, timeout=timeout, context=build_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


# =============================================================================
# Agent Loop
# =============================================================================

def build_system_prompt(task_text: str, skill_text: str | None) -> str:
    """Build the system prompt for the agent."""
    parts = [
        "You are an autonomous code agent tasked with fixing bugs in code.",
        "You work in a repository and have access to tools to read files, write files, list directories, and run tests.",
        "",
        "Guidelines:",
        "- First explore the codebase to understand the structure",
        "- Read the relevant files to understand the bug",
        "- Make minimal, focused changes to fix the bug",
        "- Run tests to verify your fix works",
        "- Call the 'done' tool when you believe the fix is complete",
        "",
        "Be efficient - you have limited steps and time.",
    ]

    if skill_text:
        parts.extend([
            "",
            "=== SKILL GUIDANCE ===",
            skill_text,
            "=== END SKILL GUIDANCE ===",
        ])

    return "\n".join(parts)


def run_agent(
    repo_path: pathlib.Path,
    task_text: str,
    skill_text: str | None = None,
    config: AgentConfig | None = None,
) -> dict:
    """Run the agentic loop and return results."""
    config = config or AgentConfig()
    state = ExecutionState(repo_path=repo_path, config=config)

    system = build_system_prompt(task_text, skill_text)
    messages = [
        {"role": "user", "content": f"Please fix the following bug:\n\n{task_text}"}
    ]

    final_status = "incomplete"
    error_message = None

    while not state.done:
        # Check limits
        limit_error = state.check_limits()
        if limit_error:
            final_status = "timeout"
            error_message = limit_error
            break

        state.steps += 1

        try:
            response = call_anthropic_api(messages, config, system)
        except Exception as e:
            final_status = "api_error"
            error_message = str(e)
            break

        # Track token usage
        usage = response.get("usage", {})
        state.input_tokens += usage.get("input_tokens", 0)
        state.output_tokens += usage.get("output_tokens", 0)

        # Extract response content
        content = response.get("content", [])
        stop_reason = response.get("stop_reason")

        # Build assistant message
        assistant_content = []
        tool_uses = []

        for block in content:
            if block.get("type") == "text":
                assistant_content.append(block)
            elif block.get("type") == "tool_use":
                assistant_content.append(block)
                tool_uses.append(block)

        messages.append({"role": "assistant", "content": assistant_content})

        # If no tool calls, agent is done thinking
        if not tool_uses:
            if stop_reason == "end_turn":
                # Agent finished without calling done - might be stuck
                final_status = "no_action"
                error_message = "Agent finished without calling done or making changes"
            break

        # Execute tools and collect results
        tool_results = []
        for tool_use in tool_uses:
            tool_name = tool_use.get("name")
            tool_input = tool_use.get("input", {})
            tool_id = tool_use.get("id")

            result = execute_tool(tool_name, tool_input, state)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result,
            })

            # Check if done was called
            if state.done:
                break

        messages.append({"role": "user", "content": tool_results})

    if state.done:
        final_status = "complete"

    # Build result
    elapsed = time.time() - state.start_time
    return {
        "status": final_status,
        "steps": state.steps,
        "tool_calls": state.tool_calls,
        "elapsed_s": round(elapsed, 2),
        "files_modified": list(state.files_modified),
        "done_summary": state.done_summary,
        "error": error_message,
        "traces": state.traces,
        "adapter_version": ADAPTER_VERSION,
        # Token usage for cost tracking
        "input_tokens": state.input_tokens,
        "output_tokens": state.output_tokens,
    }


# =============================================================================
# Main Entry Point
# =============================================================================

def _read_file(path: pathlib.Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def main() -> int:
    task_path = os.environ.get("SKILLBENCH_TASK_PATH")
    skill_path = os.environ.get("SKILLBENCH_SKILL_PATH")
    include_skill_body = os.environ.get("SKILLBENCH_INCLUDE_SKILL_BODY") == "1"
    trace_output_path = os.environ.get("SKILLBENCH_TRACE_OUTPUT")

    # Read task
    task_text = ""
    if task_path:
        task_md = pathlib.Path(task_path) / "TASK.md"
        task_text = _read_file(task_md)

    if not task_text:
        print("No task provided", file=sys.stderr)
        return 2

    # Read skill if applicable
    skill_text = None
    if include_skill_body and skill_path:
        skill_md = pathlib.Path(skill_path) / "SKILL.md"
        skill_text = _read_file(skill_md)

    # Get repo path (current directory)
    repo_path = pathlib.Path.cwd()

    # Configure from environment
    config = AgentConfig(
        max_steps=int(os.environ.get("SKILLBENCH_AGENT_MAX_STEPS", "15")),
        max_tool_calls=int(os.environ.get("SKILLBENCH_AGENT_MAX_TOOL_CALLS", "50")),
        max_wall_time_s=float(os.environ.get("SKILLBENCH_AGENT_MAX_WALL_TIME", "180")),
        temperature=float(os.environ.get("SKILLBENCH_AGENT_TEMPERATURE", "0.0")),
        max_tokens=int(os.environ.get("SKILLBENCH_AGENT_MAX_TOKENS", "4096")),
    )

    # Run agent
    result = run_agent(
        repo_path=repo_path,
        task_text=task_text,
        skill_text=skill_text,
        config=config,
    )

    # Write full trace to file if path provided
    if trace_output_path:
        trace_path = pathlib.Path(trace_output_path)
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_data = {
            "adapter_version": ADAPTER_VERSION,
            "status": result["status"],
            "steps": result["steps"],
            "tool_calls": result["tool_calls"],
            "elapsed_s": result["elapsed_s"],
            "files_modified": result["files_modified"],
            "done_summary": result.get("done_summary"),
            "error": result.get("error"),
            "traces": result.get("traces", []),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
        }
        trace_path.write_text(json.dumps(trace_data, indent=2), encoding="utf-8")

    # Write summary to stderr for debugging
    print(json.dumps({
        "status": result["status"],
        "steps": result["steps"],
        "tool_calls": result["tool_calls"],
        "elapsed_s": result["elapsed_s"],
        "files_modified": result["files_modified"],
        "error": result.get("error"),
    }, indent=2), file=sys.stderr)

    # Return success if agent completed
    if result["status"] == "complete":
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
