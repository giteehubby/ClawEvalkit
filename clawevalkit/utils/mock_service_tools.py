"""Mock service tools for ClawEval benchmark.

Dynamically registers task-specific mock service tools as native NanoBotAgent tools,
allowing the LLM to call them directly instead of constructing curl commands.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from nanobot.agent.tools.base import Tool


class MockServiceTool(Tool):
    """A generic HTTP tool that calls a mock service endpoint."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        endpoint_url: str,
        method: str = "POST",
    ):
        self._name = name
        self._description = description
        self._parameters = parameters
        self.endpoint_url = endpoint_url
        self.method = method.upper()

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        # Parameter alias mapping for known mismatches between task.yaml schema
        # and mock service expectations.
        mapped_kwargs = self._map_params(self.name, kwargs)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if self.method == "GET":
                    resp = await client.get(self.endpoint_url, params=mapped_kwargs)
                else:
                    resp = await client.post(
                        self.endpoint_url,
                        json=mapped_kwargs,
                        headers={"Content-Type": "application/json"},
                    )
                resp.raise_for_status()
                data = resp.json()
                return json.dumps(data, ensure_ascii=False, indent=2)
        except httpx.HTTPStatusError as e:
            return f"Error: HTTP {e.response.status_code} - {e.response.text}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    @staticmethod
    def _map_params(tool_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Map parameter aliases to the names expected by mock services."""
        result = dict(kwargs)
        tn = tool_name.lower()

        # calendar_list_events: task.yaml uses start_date/end_date but
        # mock service expects date/days.
        if tn == "calendar_list_events":
            if "start_date" in result and "date" not in result:
                result["date"] = result.pop("start_date")
            if "end_date" in result and "days" not in result:
                try:
                    from datetime import datetime
                    start = datetime.strptime(result.get("date", result.get("start_date", "")), "%Y-%m-%d")
                    end = datetime.strptime(result.pop("end_date"), "%Y-%m-%d")
                    delta = (end - start).days + 1
                    result["days"] = max(delta, 1)
                except Exception:
                    # If we can't parse dates, default to 7 days
                    result["days"] = 7
            # Ensure days is present if date is present
            if "date" in result and "days" not in result:
                result["days"] = 1

        # scheduler_list_jobs: mock service does not handle status="all" correctly
        # (it treats "all" as a literal status string instead of "return everything").
        # Removing the parameter lets the service return all jobs.
        if tn == "scheduler_list_jobs" and result.get("status") == "all":
            result.pop("status", None)

        return result
