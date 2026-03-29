"""
Handoff Manager - Recipe T3: Minimal Collaboration

Manages role handoffs, queues, and context passing between planner and executor.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .config import CollabConfig, HandoffPolicy
from .event import CollabEvent
from .roles import PlannerRole, ExecutorRole, VerifierRole

logger = logging.getLogger("agent.collab.handoff")


class HandoffManager:
    """Manages handoffs between collaboration roles.

    Flow (planner_executor mode):
        Task → Planner generates plan → Executor executes → [Critique on error] → Planner revises → Executor re-executes

    Flow (executor_verifier mode):
        Task → Executor executes → Verifier checks → [On fail] → Executor revises → Verifier checks again
    """

    def __init__(
        self,
        config: CollabConfig,
        planner: PlannerRole,
        executor: ExecutorRole,
        verifier: VerifierRole | None = None,
    ):
        self.config = config
        self.policy = config.handoff_policy
        self.planner = planner
        self.executor = executor
        self.verifier = verifier

        self._handoff_count = 0
        self._events: List[CollabEvent] = []
        self._current_context: Dict[str, Any] = {}

    def reset(self) -> None:
        """Reset collaboration session state."""
        self._handoff_count = 0
        self._events.clear()
        self._current_context.clear()

    def register_events(self, events: List[CollabEvent]) -> None:
        """Register external collaboration events into the session log."""
        if events:
            self._events.extend(events)

    def record_handoff(self, from_role: str, to_role: str, reason: str, iteration: int = 0, **data) -> CollabEvent:
        """Record a role handoff event."""
        event = CollabEvent(
            event_type="handoff",
            role=from_role,
            iteration=iteration,
            data={
                "from": from_role,
                "to": to_role,
                "reason": reason,
                **data,
            },
        )
        self._events.append(event)
        return event

    def should_handoff(self, trigger: str) -> bool:
        """Check if a handoff should occur based on the policy."""
        if trigger == "always":
            return True
        if trigger == "manual":
            return False
        if self.policy.trigger == "always":
            return True
        if self.policy.trigger == "manual":
            return False
        return self.policy.trigger == trigger

    def can_handoff(self) -> bool:
        """Check if more handoffs are allowed."""
        return self._handoff_count < self.config.max_handoffs

    async def execute_planner_executor(
        self,
        task: str,
        initial_context: str | None = None,
    ) -> Dict[str, Any]:
        """Execute the planner-executor collaboration flow.

        Returns:
            Dict with "success", "result", "events", "iterations"
        """
        iteration = 0
        all_events: List[CollabEvent] = []
        final_result = ""

        # Generate initial plan
        plan_result = await self.planner.generate_plan(task, context=initial_context, iteration=iteration)
        all_events.extend(self.planner.get_events())
        iteration += 1

        if not plan_result.get("plan"):
            return {
                "success": False,
                "result": "Failed to generate plan",
                "events": all_events,
                "iterations": iteration,
            }

        # Execute plan steps
        context = initial_context or ""
        current_plan = plan_result["plan"]

        for step in current_plan:
            step_result = await self.executor.execute_step(step, context=context, iteration=iteration)
            all_events.extend(self.executor.get_events())
            iteration += 1

            is_error = step_result.get("error") is not None

            # Handle critique based on frequency setting
            should_critique = (
                (self.config.critique_frequency == "every_step") or
                (self.config.critique_frequency == "on_error" and is_error)
            )

            if should_critique and self.verifier:
                verify_result = await self.verifier.verify(step, step_result.get("result", ""), iteration=iteration)
                all_events.extend(self.verifier.get_events())
                iteration += 1

                if verify_result.get("verdict") in ("FAIL", "REVISION") and self.can_handoff():
                    # Trigger revision through planner
                    self._handoff_count += 1
                    revision_context = f"Previous step failed: {step_result.get('error', 'Unknown error')}\nFeedback: {verify_result.get('feedback', '')}"
                    new_plan_result = await self.planner.generate_plan(
                        task,
                        context=revision_context,
                        iteration=iteration,
                    )
                    all_events.extend(self.planner.get_events())
                    iteration += 1

                    if new_plan_result.get("plan"):
                        current_plan = new_plan_result["plan"]

                if step_result.get("result"):
                    context += f"\nStep {step['step']}: {step_result['result']}"

            elif step_result.get("result"):
                context += f"\nStep {step['step']}: {step_result['result']}"

            final_result = step_result.get("result", final_result)

        # Check if we need a final handoff
        if self.should_handoff("on_success") and self.can_handoff():
            logger.info(f"[HandoffManager] Final handoff triggered after {self._handoff_count} handoffs")

        return {
            "success": not any(e.data.get("error") for e in all_events if e.data.get("step")),
            "result": final_result,
            "events": all_events,
            "iterations": iteration,
            "handoff_count": self._handoff_count,
        }

    async def execute_executor_verifier(
        self,
        task: str,
        initial_context: str | None = None,
    ) -> Dict[str, Any]:
        """Execute the executor-verifier collaboration flow.

        Returns:
            Dict with "success", "result", "events", "iterations"
        """
        if not self.verifier:
            raise ValueError("VerifierRole is required for executor_verifier mode")

        iteration = 0
        all_events: List[CollabEvent] = []
        context = initial_context or ""

        # Execute initial attempt
        step = {"step": 1, "description": task, "action": "execute"}
        step_result = await self.executor.execute_step(step, context=context, iteration=iteration)
        all_events.extend(self.executor.get_events())
        iteration += 1

        final_result = step_result.get("result", "")

        # Verify result
        max_verification_attempts = 3
        for attempt in range(max_verification_attempts):
            verify_result = await self.verifier.verify(step, final_result, iteration=iteration)
            all_events.extend(self.verifier.get_events())
            iteration += 1

            if verify_result.get("verdict") == "PASS":
                break

            if self.can_handoff() and attempt < max_verification_attempts - 1:
                self._handoff_count += 1
                # Re-execute with feedback
                revision_context = f"{context}\nVerification feedback: {verify_result.get('feedback', '')}"
                step_result = await self.executor.execute_step(step, context=revision_context, iteration=iteration)
                all_events.extend(self.executor.get_events())
                iteration += 1
                final_result = step_result.get("result", final_result)
            else:
                break

        return {
            "success": verify_result.get("verdict") == "PASS",
            "result": final_result,
            "events": all_events,
            "iterations": iteration,
            "handoff_count": self._handoff_count,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the collaboration session."""
        event_summary = {
            "total_events": len(self._events),
            "by_type": {},
            "by_role": {},
        }
        for event in self._events:
            event_summary["by_type"][event.event_type] = event_summary["by_type"].get(event.event_type, 0) + 1
            event_summary["by_role"][event.role] = event_summary["by_role"].get(event.role, 0) + 1
        return {
            "total_handoffs": self._handoff_count,
            "max_handoffs": self.config.max_handoffs,
            "mode": self.config.mode,
            "event_count": len(self._events),
            "events": event_summary,
        }

    def get_events(self) -> List[CollabEvent]:
        """Get all events recorded."""
        return self._events.copy()
