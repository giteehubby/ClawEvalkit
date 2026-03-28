"""
Collaboration Roles - Recipe T3: Minimal Collaboration

PlannerRole and ExecutorRole for lightweight two-agent collaboration.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import litellm
from litellm import acompletion

from .config import CollabConfig, RoleDefinition
from .event import CollabEvent

logger = logging.getLogger("agent.collab.roles")


class PlannerRole:
    """Planner role - generates execution plans."""

    DEFAULT_SYSTEM_PROMPT = """You are a planner agent. Your task is to analyze the user's request and create a structured execution plan.

When creating a plan:
1. Break down the task into clear, actionable steps
2. Consider dependencies between steps
3. Anticipate potential issues
4. Keep the plan concise but complete

Output your plan in the following format:
- Step 1: [action description]
- Step 2: [action description]
- ...

Be specific about what tools to use and what the expected outcomes are."""

    def __init__(
        self,
        config: CollabConfig,
        llm_call_fn,  # Async function reference to call LLM
        model: str,
        system_prompt: str | None = None,
    ):
        self.config = config
        self._llm_call = llm_call_fn
        self.model = model
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self._events: List[CollabEvent] = []

    async def generate_plan(
        self,
        task: str,
        context: str | None = None,
        iteration: int = 0,
    ) -> Dict[str, Any]:
        """Generate an execution plan for the given task.

        Returns:
            Dict with "plan" (list of steps), "rationale" (str), "iteration" (int)
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]

        if context:
            messages.append({"role": "user", "content": f"Context from previous attempts:\n{context}\n\nTask: {task}"})
        else:
            messages.append({"role": "user", "content": task})

        try:
            response = await self._llm_call(messages, max_tokens=1024)
            content = ""
            if hasattr(response, "choices") and response.choices:
                content = response.choices[0].message.content or ""

            # Parse the plan from the response
            plan = self._parse_plan(content)

            event = CollabEvent(
                event_type="plan_generated",
                role="planner",
                iteration=iteration,
                data={"plan": plan, "raw_response": content[:500]},
            )
            self._events.append(event)

            logger.info(f"[PlannerRole] Generated plan with {len(plan)} steps")

            return {
                "plan": plan,
                "rationale": content[:500],
                "iteration": iteration,
            }

        except Exception as e:
            logger.error(f"[PlannerRole] Plan generation failed: {e}")
            return {
                "plan": [{"step": "Fallback: Execute task directly", "action": "execute"}],
                "rationale": f"Planning failed: {e}",
                "iteration": iteration,
            }

    def _parse_plan(self, content: str) -> List[Dict[str, str]]:
        """Parse plan from LLM response content."""
        plan = []
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("- Step") or line.startswith("Step") or line.startswith("* "):
                # Extract step description
                step_text = line.lstrip("- *").lstrip("0123456789. ").strip()
                if step_text:
                    plan.append({
                        "step": len(plan) + 1,
                        "description": step_text,
                        "action": "continue",
                    })
        if not plan:
            # Fallback: treat each line as a step
            for line in lines:
                line = line.strip()
                if line and len(line) > 10:
                    plan.append({
                        "step": len(plan) + 1,
                        "description": line[:100],
                        "action": "continue",
                    })
        return plan

    def get_events(self) -> List[CollabEvent]:
        """Get all events recorded by this role."""
        return self._events.copy()


class ExecutorRole:
    """Executor role - executes plan steps using tools."""

    def __init__(
        self,
        config: CollabConfig,
        llm_call_fn,
        execute_tool_fn,
        model: str,
        system_prompt: str | None = None,
    ):
        self.config = config
        self._llm_call = llm_call_fn
        self._execute_tool = execute_tool_fn
        self.model = model
        self.system_prompt = system_prompt or ""
        self._events: List[CollabEvent] = []
        self._tool_defs: List[Dict] = []

    def set_tool_definitions(self, tool_defs: List[Dict]) -> None:
        """Set available tool definitions."""
        self._tool_defs = tool_defs

    async def execute_step(
        self,
        step: Dict[str, str],
        context: str | None = None,
        iteration: int = 0,
    ) -> Dict[str, Any]:
        """Execute a single plan step.

        Returns:
            Dict with "success" (bool), "result" (str), "error" (str | None)
        """
        step_num = step.get("step", "?")
        step_desc = step.get("description", "")

        logger.info(f"[ExecutorRole] Executing step {step_num}: {step_desc[:50]}...")

        messages = [
            {"role": "system", "content": self.system_prompt} if self.system_prompt else {"role": "system", "content": "You are an executor agent."},
        ]

        if context:
            messages.append({"role": "user", "content": f"Previous context:\n{context}\n\nCurrent step to execute: {step_desc}"})

        try:
            response = await self._llm_call(messages, tools=self._tool_defs if self._tool_defs else None)

            # Check if LLM wants to call tools
            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                message = choice.message

                if hasattr(message, "tool_calls") and message.tool_calls:
                    # Execute the tool call
                    for tc in message.tool_calls:
                        tool_name = tc.function.name
                        args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                        result = await self._execute_tool({
                            "id": tc.id,
                            "function": {"name": tool_name, "arguments": args}
                        })

                        event = CollabEvent(
                            event_type="step_executed",
                            role="executor",
                            iteration=iteration,
                            data={"step": step_num, "tool": tool_name, "result": result[:200]},
                        )
                        self._events.append(event)

                        return {
                            "success": not result.startswith("Error:"),
                            "result": result,
                            "tool_used": tool_name,
                            "error": None if not result.startswith("Error:") else result,
                        }
                else:
                    # No tool call, return content as result
                    content = message.content or ""
                    event = CollabEvent(
                        event_type="step_executed",
                        role="executor",
                        iteration=iteration,
                        data={"step": step_num, "content": content[:200]},
                    )
                    self._events.append(event)

                    return {
                        "success": True,
                        "result": content,
                        "tool_used": None,
                        "error": None,
                    }

            return {
                "success": False,
                "result": "",
                "error": "No response from LLM",
            }

        except Exception as e:
            logger.error(f"[ExecutorRole] Step execution failed: {e}")
            event = CollabEvent(
                event_type="step_executed",
                role="executor",
                iteration=iteration,
                data={"step": step_num, "error": str(e)},
            )
            self._events.append(event)

            return {
                "success": False,
                "result": "",
                "error": str(e),
            }

    def get_events(self) -> List[CollabEvent]:
        """Get all events recorded by this role."""
        return self._events.copy()


class VerifierRole:
    """Verifier role - checks executor output for errors."""

    DEFAULT_SYSTEM_PROMPT = """You are a verifier agent. Your task is to review the executor's output and identify any issues or errors.

Check for:
1. Did the executor complete the step correctly?
2. Are there any obvious errors or mistakes?
3. Is the output consistent with the task requirements?
4. Should the executor try a different approach?

Respond with:
- PASS: The step was completed successfully
- FAIL: The step has issues that need to be addressed
- REVISION: The step needs to be revised with specific feedback
"""

    def __init__(
        self,
        config: CollabConfig,
        llm_call_fn,
        model: str,
        system_prompt: str | None = None,
    ):
        self.config = config
        self._llm_call = llm_call_fn
        self.model = model
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self._events: List[CollabEvent] = []

    async def verify(
        self,
        step: Dict[str, str],
        result: str,
        iteration: int = 0,
    ) -> Dict[str, Any]:
        """Verify the executor's output.

        Returns:
            Dict with "verdict" (PASS/FAIL/REVISION), "feedback" (str), "suggestions" (list[str])
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Step: {step.get('description', '')}\n\nExecutor result:\n{result[:1000]}"},
        ]

        try:
            response = await self._llm_call(messages, max_tokens=512)

            if hasattr(response, "choices") and response.choices:
                content = response.choices[0].message.content or ""
                verdict = "PASS"
                feedback = content

                if content.upper().startswith("FAIL"):
                    verdict = "FAIL"
                elif content.upper().startswith("REVISION"):
                    verdict = "REVISION"

                event = CollabEvent(
                    event_type="critique",
                    role="verifier",
                    iteration=iteration,
                    data={"verdict": verdict, "feedback": content[:300]},
                )
                self._events.append(event)

                return {
                    "verdict": verdict,
                    "feedback": feedback,
                    "iteration": iteration,
                }

        except Exception as e:
            logger.error(f"[VerifierRole] Verification failed: {e}")

        return {
            "verdict": "PASS",
            "feedback": "Verification skipped due to error",
            "iteration": iteration,
        }

    def get_events(self) -> List[CollabEvent]:
        """Get all events recorded by this role."""
        return self._events.copy()
