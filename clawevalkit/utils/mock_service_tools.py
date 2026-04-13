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
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if self.method == "GET":
                    resp = await client.get(self.endpoint_url, params=kwargs)
                else:
                    resp = await client.post(
                        self.endpoint_url,
                        json=kwargs,
                        headers={"Content-Type": "application/json"},
                    )
                resp.raise_for_status()
                data = resp.json()
                return json.dumps(data, ensure_ascii=False, indent=2)
        except httpx.HTTPStatusError as e:
            return f"Error: HTTP {e.response.status_code} - {e.response.text}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
