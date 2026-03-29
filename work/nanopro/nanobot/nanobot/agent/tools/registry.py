"""Tool registry for dynamic tool management."""

import re
from typing import Any

from nanobot.agent.tools.base import Tool


class ToolRegistry:
    """
    Registry for agent tools.

    Allows dynamic registration and execution of tools.
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get all tool definitions in OpenAI format."""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> Any:
        """Execute a tool by name with given parameters."""
        _HINT = "\n\n[Analyze the error above and try a different approach.]"

        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found. Available: {', '.join(self.tool_names)}"

        try:
            # Attempt to cast parameters to match schema types
            params = tool.cast_params(params)

            # Validate parameters
            errors = tool.validate_params(params)
            if errors:
                return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors) + _HINT

            # Remap /root/ and /app/ paths to workspace equivalents before execution
            params = self._remap_tool_paths(tool, params)

            result = await tool.execute(**params)
            if isinstance(result, str) and result.startswith("Error"):
                return result + _HINT
            return result
        except Exception as e:
            return f"Error executing {name}: {str(e)}" + _HINT

    def _remap_tool_paths(self, tool: Tool, params: dict[str, Any]) -> dict[str, Any]:
        """Remap /root/ and /app/ paths in tool params to workspace equivalents.

        This handles SkillsBench tasks where the agent may reference paths like
        /root/some_file or /app/data that need to be mapped to the actual workspace.
        """
        workspace = getattr(tool, '_workspace', None)
        if not workspace:
            return params

        workspace = str(workspace)

        def _remap_value(value: Any) -> Any:
            if isinstance(value, str):
                result = value
                # Replace /root/ with workspace/root/
                if '/root' in result:
                    result = re.sub(r'/root/', f'{workspace}/root/', result)
                    result = re.sub(r'/root($|[\s])', f'{workspace}/root\\1', result)
                # Replace /app/ with workspace/ for SkillsBench compatibility
                if '/app' in result:
                    result = re.sub(r'/app/', f'{workspace}/', result)
                    result = re.sub(r'/app($|[\s])', f'{workspace}\\1', result)
                return result
            elif isinstance(value, dict):
                return {k: _remap_value(v) for k, v in value.items()}
            elif isinstance(value, (list, tuple)):
                return type(value)(_remap_value(item) for item in value)
            return value

        return _remap_value(params)

    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
