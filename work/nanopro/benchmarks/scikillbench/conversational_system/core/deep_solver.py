"""
DeepSolver - Deep Problem-Solving Workflow Wrapper

Wraps the existing 4-agent system as a tool for Orchestrator

Workflow:
1. Solution Researcher: Deep research using web search and code extraction
2. Code Agent: Code execution and verification
3. Debug Agents (3 parallel): Systematic debugging with multiple strategies if debugging is needed
4. Output Processor: Select best result and format detailed explanation

All internal agents have search_memory capability built-in to leverage past memories
"""

from __future__ import annotations

import os
import sys
import asyncio
import time
from typing import Dict, Any
from agents import function_tool, Runner

# Import MLflow for tracing
try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    print("⚠️  MLflow not available - tracing disabled")

# Add project root to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
conversational_system_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(conversational_system_dir)

sys.path.insert(0, project_root)

# Import agents from deep_solver_with_memory
from conversational_system.deep_solver_with_memory import (
    create_solution_researcher_agent,
    create_code_agent,
    create_debug_agents,
    create_output_processor_agent
)


class DeepSolver:
    """
    Deep problem-solving workflow that wraps the 4-agent system.

    This class manages the complete research-code-debug-process workflow
    and enhances all internal agents with memory search capability.
    """

    def __init__(self):
        """Initialize DeepSolver."""
        self.solution_researcher = None
        self.code_agent = None
        self.debug_agents = None
        self.output_processor = None
        self._initialized = False
        self._init_lock = asyncio.Lock()  # Thread-safe initialization lock

    async def _initialize_agents(self):
        """
        Initialize all internal agents.

        This is done lazily to avoid initialization overhead.
        Uses async lock to ensure thread-safe initialization.
        """
        # Use async lock to prevent concurrent initialization
        async with self._init_lock:
            # Double-check pattern: check again after acquiring lock
            if self._initialized:
                return

            print("🔧 Initializing DeepSolver agents...")

            # Create agents (they already have search_memory built-in)
            self.solution_researcher = await create_solution_researcher_agent()
            self.code_agent = await create_code_agent()
            self.debug_agents = await create_debug_agents()
            self.output_processor = await create_output_processor_agent()

            self._initialized = True
            print("✅ DeepSolver agents initialized")

    async def solve(
        self,
        query: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Execute the full problem-solving workflow.

        Args:
            query: User's problem/question
            user_id: User identifier (for memory context)

        Returns:
            Dictionary containing:
            - original_user_query: Original user query
            - success: Whether solution was successful
            - final_code: Final working code solution
            - execution_results: Raw execution output and results
            - explanation: Detailed explanation (from free_form output)
        """
        # Ensure agents are initialized
        await self._initialize_agents()

        print(f"\n🚀 DeepSolver starting workflow for query: {query[:100]}...")

        workflow_start_time = time.time()

        # DO NOT create manual spans - let autolog handle everything automatically
        # Manual spans interfere with the trace hierarchy
        try:
            # Phase 1: Solution Research
            # Autolog will automatically capture tool calls within this agent
            print("📚 Phase 1: Solution Research...")
            phase1_start = time.time()

            solution_input = f"User ID: {user_id}\nQuery: {query}"
            runner = Runner()
            solution_result = await runner.run(self.solution_researcher, solution_input, max_turns=1000)

            if not solution_result or not hasattr(solution_result, 'final_output'):
                raise ValueError("Solution Researcher failed to produce valid output")

            solution_data = solution_result.final_output
            phase1_time = time.time() - phase1_start
            print(f"   ✓ Research complete. Packages needed: {solution_data.required_packages}")

            # Phase 2: Code Execution
            # Autolog will automatically capture this agent call
            print("💻 Phase 2: Code Execution...")
            phase2_start = time.time()

            code_input = (
                f"User ID: {user_id}\n"
                f"Original user query: {query}\n"
                f"Required packages: {solution_data.required_packages}\n"
                f"Code solution:\n{solution_data.code_solution}"
            )

            runner = Runner()
            code_result = await runner.run(self.code_agent, code_input, max_turns=1000)

            if not code_result or not hasattr(code_result, 'final_output'):
                raise ValueError("Code Agent failed to produce valid output")

            code_data = code_result.final_output
            phase2_time = time.time() - phase2_start

            # Phase 3: Debugging (if needed)
            if code_data.needs_debugging:
                print("🐛 Phase 3: Debugging (3 parallel agents)...")
                phase3_start = time.time()

                debug_input = (
                    f"User ID: {user_id}\n"
                    f"Original user query: {query}\n"
                    f"Failed code: {code_data.executed_code}\n"
                    f"Execution output: {code_data.execution_output}"
                )

                # Run 3 debug agents in parallel
                debug_tasks = [
                    Runner().run(agent, debug_input, max_turns=1000)
                    for agent in self.debug_agents
                ]
                debug_results = await asyncio.gather(*debug_tasks, return_exceptions=True)

                print("   ✓ Debugging complete")

                # Validate debug results
                valid_results = []
                for i, result in enumerate(debug_results):
                    if isinstance(result, Exception):
                        print(f"   ⚠️ Debug agent {i+1} failed: {str(result)}")
                        continue
                    if result and hasattr(result, 'final_output'):
                        valid_results.append(result.final_output)
                    else:
                        print(f"   ⚠️ Debug agent {i+1} returned invalid output")

                if not valid_results:
                    raise ValueError("All debug agents failed to produce valid output")

                print(f"   ✓ {len(valid_results)}/{len(debug_results)} debug agents succeeded")
                phase3_time = time.time() - phase3_start

                # Phase 4: Output Processing (from debug results)
                print("📊 Phase 4: Processing debug results...")
                phase4_start = time.time()

                debug_result_texts = []
                for i, result in enumerate(valid_results):
                    debug_result_texts.append(
                        f"Debug Result {i+1}:\n"
                        f"  Code: {result.final_code}\n"
                        f"  Output: {result.execution_output}"
                    )

                processor_input = (
                    f"Original user query: {query}\n"
                    + "\n\n".join(debug_result_texts)
                )

                runner = Runner()
                final_result = await runner.run(self.output_processor, processor_input, max_turns=1000)

                if not final_result or not hasattr(final_result, 'final_output'):
                    raise ValueError("Output Processor failed to produce valid output")

                final_data = final_result.final_output
                phase4_time = time.time() - phase4_start

            else:
                print("✅ Phase 3: Code executed successfully, no debugging needed")

                # Phase 4: Output Processing (from successful execution)
                print("📊 Phase 4: Processing successful execution...")
                phase4_start = time.time()

                processor_input = (
                    f"Original user query: {query}\n"
                    f"Successful execution:\n"
                    f"  Code: {code_data.executed_code}\n"
                    f"  Output: {code_data.execution_output}"
                )

                runner = Runner()
                final_result = await runner.run(self.output_processor, processor_input, max_turns=1000)

                if not final_result or not hasattr(final_result, 'final_output'):
                    raise ValueError("Output Processor failed to produce valid output")

                final_data = final_result.final_output
                phase4_time = time.time() - phase4_start

            workflow_time = time.time() - workflow_start_time
            print("✅ DeepSolver workflow complete!\n")

            # Return FinalResult
            return {
                "success": final_data.success,
                "final_code": final_data.final_code,
                "execution_results": final_data.execution_results,
                "explanation": final_data.processed_output,
                "original_user_query": query
            }

        except Exception as e:
            workflow_time = time.time() - workflow_start_time
            print(f"❌ DeepSolver error: {str(e)}")

            return {
                "success": False,
                "final_code": "",
                "execution_results": f"DeepSolver encountered an error: {str(e)}",
                "explanation": "Failed to solve the problem. Please try rephrasing your question or providing more details.",
                "original_user_query": query
            }


# Global DeepSolver instance
_deep_solver_instance = None


def get_deep_solver() -> DeepSolver:
    """Get or create the global DeepSolver instance."""
    global _deep_solver_instance
    if _deep_solver_instance is None:
        _deep_solver_instance = DeepSolver()
    return _deep_solver_instance


# Function tool for Orchestrator

@function_tool
async def solve_with_deep_solver(
    query: str,
    user_id: str
) -> Dict[str, Any]:
    """
    Solve complex materials science problems through comprehensive research,
    code generation, execution, and debugging workflow.

    Use this when:
    - Memory doesn't have sufficient relevant solutions
    - Problem requires research and experimentation
    - Quick solution attempts failed
    - You are uncertain about the approach

    Returns comprehensive solution with working code, execution results,
    and detailed explanation. Has 30-minute timeout for very complex problems.

    Args:
        query: User's computational problem/question
        user_id: User identifier for memory context

    Returns:
        Dictionary with: success (bool), final_code (str), execution_results (str),
        explanation (str), original_user_query (str)
    """
    solver = get_deep_solver()

    # 30-minute timeout for deep solver workflow
    TIMEOUT_SECONDS = 1800  # 30 minutes

    try:
        result = await asyncio.wait_for(
            solver.solve(query, user_id),
            timeout=TIMEOUT_SECONDS
        )
        return result

    except asyncio.TimeoutError:
        print(f"⏱️ DeepSolver timeout after {TIMEOUT_SECONDS} seconds (30 minutes)")

        # Return friendly timeout message instead of crashing
        return {
            "success": False,
            "final_code": "",
            "execution_results": "DeepSolver timed out after 30 minutes",
            "explanation": (
                "I apologize, but I wasn't able to complete this analysis. "
                "This problem appears to be quite complex.\n\n"
                "I suggest we break this down into smaller, more manageable steps:\n\n"
                "1. Could you help me understand which specific part you'd like to tackle first?\n"
                "2. Are there any intermediate results or partial solutions that would be helpful?\n"
                "3. Would you like to focus on a specific aspect of the problem (e.g., data retrieval, "
                "structure optimization, property calculation, visualization)?\n\n"
                "Please let me know how you'd like to proceed, and I'll help you solve this step by step."
            ),
            "original_user_query": query
        }


# Export
__all__ = [
    'DeepSolver',
    'get_deep_solver',
    'solve_with_deep_solver'
]
