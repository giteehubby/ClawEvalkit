"""
PreflightCheck 模块 - 工具调用前检查
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("control.preflight")


@dataclass
class PreflightResult:
    """Preflight 检查结果"""
    passed: bool
    warnings: list[str] = None
    errors: list[str] = None
    suggestions: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.errors is None:
            self.errors = []
        if self.suggestions is None:
            self.suggestions = []


class PreflightCheck:
    """工具调用前检查模块"""

    def __init__(self, enabled: bool = False, check_params: bool = True, check_suitability: bool = False):
        self.enabled = enabled
        self.check_params = check_params
        self.check_suitability = check_suitability
        self._check_history: list[dict[str, Any]] = []

    def check_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        task_context: str = "",
    ) -> PreflightResult:
        """检查工具调用"""
        if not self.enabled:
            return PreflightResult(passed=True)

        warnings = []
        errors = []
        suggestions = []

        # 参数检查
        if self.check_params:
            param_result = self._check_params(tool_name, tool_input)
            warnings.extend(param_result.warnings)
            errors.extend(param_result.errors)
            suggestions.extend(param_result.suggestions)

        # 适用性检查
        if self.check_suitability and task_context:
            suit_result = self._check_suitability(tool_name, tool_input, task_context)
            warnings.extend(suit_result.warnings)
            suggestions.extend(suit_result.suggestions)

        passed = len(errors) == 0
        result = PreflightResult(
            passed=passed,
            warnings=warnings,
            errors=errors,
            suggestions=suggestions,
        )

        self._record_check(tool_name, result)
        return result

    def _check_params(self, tool_name: str, tool_input: dict[str, Any]) -> PreflightResult:
        """检查参数"""
        warnings = []
        errors = []
        suggestions = []
        normalized_tool = (tool_name or "").strip().lower()

        # 检查空参数
        for key, value in tool_input.items():
            if value is None or value == "":
                warnings.append(f"Parameter '{key}' is empty")
            elif isinstance(value, str) and len(value) > 10000:
                warnings.append(f"Parameter '{key}' is very long ({len(value)} chars)")
                suggestions.append(f"Consider if '{key}' needs to be this long")

        # 特定工具检查
        if normalized_tool == "read_file":
            path = tool_input.get("path", "")
            if path and not any(path.startswith(p) for p in ["/", "./", "../"]):
                warnings.append(f"Read path '{path}' may be relative; consider using absolute path")

        elif normalized_tool == "write_file":
            path = tool_input.get("path", "")
            content = tool_input.get("content", "")
            if not path:
                errors.append("write_file requires 'path' parameter")
            if not content:
                warnings.append("write_file content is empty")

        elif normalized_tool == "edit_file":
            path = tool_input.get("path", "")
            old_text = tool_input.get("old_text", "")
            if not path:
                errors.append("edit_file requires 'path' parameter")
            if old_text == "":
                warnings.append("edit_file old_text is empty")

        elif normalized_tool == "list_dir":
            path = tool_input.get("path", "")
            if not path:
                errors.append("list_dir requires 'path' parameter")

        elif normalized_tool == "exec":
            command = tool_input.get("command", "")
            if not command:
                errors.append("exec requires 'command' parameter")
            elif any(danger in command.lower() for danger in ["rm -rf", "sudo", "chmod 777"]):
                warnings.append(f"Bash command contains potentially dangerous operation: {command[:50]}...")
                suggestions.append("Verify this command is intentional and safe")

        elif normalized_tool == "web_fetch":
            url = tool_input.get("url", "")
            if url and not (url.startswith("http://") or url.startswith("https://")):
                errors.append(f"web_fetch requires valid URL, got: {url}")

        elif normalized_tool == "web_search":
            query = tool_input.get("query", "")
            if not query:
                errors.append("web_search requires 'query' parameter")

        return PreflightResult(passed=len(errors) == 0, warnings=warnings, errors=errors, suggestions=suggestions)

    def _check_suitability(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        task_context: str,
    ) -> PreflightResult:
        """检查工具对任务的适用性"""
        warnings = []
        suggestions = []

        # 简单的关键词检查
        task_lower = task_context.lower()
        normalized_tool = (tool_name or "").strip().lower()

        if normalized_tool == "web_fetch" and any(word in task_lower for word in ["file", "local", "disk"]):
            warnings.append("Task mentions local operations but WebFetch is being used")
            suggestions.append("Consider using read_file for local files")

        elif normalized_tool == "read_file" and any(word in task_lower for word in ["web", "url", "http"]):
            warnings.append("Task mentions web operations but Read is being used")
            suggestions.append("Consider using web_fetch for URLs")

        elif normalized_tool == "exec" and any(word in task_lower for word in ["edit", "write", "create file"]):
            warnings.append("Task involves file editing but Bash is being used")
            suggestions.append("Consider using write_file/edit_file for file operations")

        return PreflightResult(passed=True, warnings=warnings, suggestions=suggestions)

    def _record_check(self, tool_name: str, result: PreflightResult) -> None:
        """记录检查结果"""
        self._check_history.append({
            "tool_name": tool_name,
            "passed": result.passed,
            "warning_count": len(result.warnings),
            "error_count": len(result.errors),
        })

    def get_check_stats(self) -> dict[str, Any]:
        """获取检查统计"""
        total = len(self._check_history)
        passed = sum(1 for c in self._check_history if c["passed"])
        return {
            "total_checks": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total > 0 else 1.0,
        }

    def clear_history(self) -> None:
        """清除检查历史"""
        self._check_history = []
