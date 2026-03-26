"""
NanoBot Agent 适配器。

直接 import nanobot 代码来执行任务。
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# 添加 nanobot 源码路径 (nanobot/ 与 scripts/ 平级，nanobot/ 包含 nanobot Python 模块)
NANOBOT_PATH = Path(__file__).parent.parent.parent / "nanobot"
sys.path.insert(0, str(NANOBOT_PATH))

import litellm
from litellm import acompletion
from agent.base import AgentResult, BaseAgent
from nanobot.bus.queue import MessageBus
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, ListDirTool, EditFileTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.message import MessageTool


class NanoBotAgent(BaseAgent):
    """NanoBot Agent 实现 - 使用 litellm 直接调用"""

    def __init__(
        self,
        model: str,
        api_url: str,
        api_key: str,
        workspace: Path,
        timeout: int = 300,
        **kwargs,
    ):
        self.model = model
        self.api_url = api_url
        self.api_key = api_key
        self.workspace = workspace
        self.timeout = timeout
        self.session_store_dir = Path(kwargs.get("session_store_dir") or (self.workspace / ".sessions"))
        self.session_store_dir.mkdir(parents=True, exist_ok=True)
        self.system_prompt = kwargs.get("system_prompt", "")

        # 准备工作空间
        workspace.mkdir(parents=True, exist_ok=True)

        # 配置 litellm
        litellm.drop_params = True
        litellm.suppress_debug_info = True

        # 创建工具注册表
        self._tools = ToolRegistry()
        self._register_tools()

        # 状态跟踪
        self._usage = {}
        self._transcript: List[Dict] = []
        self._conversation_history: List[Dict] = []

    def _session_file(self, session_id: str) -> Path:
        safe_name = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in session_id)
        return self.session_store_dir / f"{safe_name}.json"

    def _load_session_messages(self, session_id: str | None) -> List[Dict[str, Any]]:
        if not session_id:
            return []

        session_file = self._session_file(session_id)
        if not session_file.exists():
            base_messages: List[Dict[str, Any]] = []
            if self.system_prompt:
                base_messages.append({"role": "system", "content": self.system_prompt})
            return base_messages

        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass

        return []

    def _save_session_messages(self, session_id: str | None, messages: List[Dict[str, Any]]) -> None:
        if not session_id:
            return

        session_file = self._session_file(session_id)
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")

    def _register_tools(self) -> None:
        """注册工具"""
        # 注册文件系统工具
        self._tools.register(ReadFileTool(workspace=self.workspace))
        self._tools.register(WriteFileTool(workspace=self.workspace))
        self._tools.register(ListDirTool(workspace=self.workspace))
        self._tools.register(EditFileTool(workspace=self.workspace))

        # 注册 shell 工具
        self._tools.register(ExecTool(
            working_dir=str(self.workspace),
            restrict_to_workspace=True,
        ))

        # 注册 web 工具
        self._tools.register(WebSearchTool())
        self._tools.register(WebFetchTool())

        # 不注册消息工具（不需要发送到其他 channel）

    async def _call_llm(
        self,
        messages: List[Dict],
        tools: List[Dict] | None = None,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """调用 LLM"""
        try:
            # 准备参数
            kwargs = {
                "model": self.model,
                "messages": messages,
                "api_key": self.api_key,
                "api_base": self.api_url,
                "max_tokens": max_tokens,
                "temperature": 0.1,
            }

            if tools:
                kwargs["tools"] = tools

            response = await acompletion(**kwargs)

            # 提取 usage
            if hasattr(response, "usage") and response.usage:
                self._usage = {
                    "input_tokens": getattr(response.usage, "prompt_tokens", 0),
                    "output_tokens": getattr(response.usage, "completion_tokens", 0),
                    "total_tokens": getattr(response.usage, "total_tokens", 0),
                }

            return response

        except Exception as e:
            raise Exception(f"LLM call failed: {e}")

    async def _execute_tool(self, tool_call: Dict) -> str:
        """执行工具调用"""
        tool_name = tool_call.get("function", {}).get("name", "")
        arguments = tool_call.get("function", {}).get("arguments", "{}")

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return f"Error: Invalid JSON arguments: {arguments}"

        # 查找工具
        tool = self._tools.get(tool_name)
        if not tool:
            return f"Error: Unknown tool: {tool_name}"

        try:
            result = await tool.execute(**arguments)
            return str(result)
        except Exception as e:
            return f"Error executing {tool_name}: {e}"

    async def _run_loop(self, messages: List[Dict], max_iterations: int = 10) -> str:
        """运行 agent loop"""
        tool_defs = self._tools.get_definitions()
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # 调用 LLM
            try:
                response = await self._call_llm(messages, tools=tool_defs)
            except Exception as e:
                return f"Error: {e}"

            # 获取响应内容
            content = ""
            tool_calls = []

            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                message = choice.message

                # 获取文本内容
                if hasattr(message, "content") and message.content:
                    content = message.content

                # 获取工具调用
                if hasattr(message, "tool_calls") and message.tool_calls:
                    tool_calls = [
                        {"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in message.tool_calls
                    ]

            # 添加 assistant 消息到历史（兼容 OpenAI 格式）
            assistant_msg = {"role": "assistant", "content": content}
            if tool_calls:
                # 格式化工具调用（添加 type 字段）
                formatted_calls = []
                for tc in tool_calls:
                    formatted_calls.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": tc["function"]
                    })
                assistant_msg["tool_calls"] = formatted_calls
            messages.append(assistant_msg)

            # 如果没有工具调用，返回
            if not tool_calls:
                # 添加 assistant 消息到 transcript（格式兼容 pinchbench grading）
                content_items = []
                if content:
                    content_items.append(content)
                self._transcript.append({
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": content_items,
                    }
                })
                return content

            # 执行工具调用
            for tool_call in tool_calls:
                tool_result = await self._execute_tool(tool_call)

                # 解析参数
                args_str = tool_call["function"]["arguments"]
                if isinstance(args_str, str):
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {"raw": args_str}
                else:
                    args = args_str

                # 添加 assistant 消息到 transcript（格式兼容 pinchbench grading）
                # grading 代码期望: content = [{"type": "toolCall", "name": "...", "params": {...}}]
                content_items = []
                if content:
                    content_items.append(content)
                content_items.append({
                    "type": "toolCall",
                    "name": tool_call["function"]["name"],
                    "params": args
                })
                self._transcript.append({
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": content_items,
                    }
                })
                # 添加 tool 结果到 transcript
                self._transcript.append({
                    "type": "message",
                    "message": {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": tool_result,
                    }
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result,
                })

        return content if content else "Max iterations reached"

    def execute(self, prompt: str, session_id: str | None = None, workspace: Path | None = None) -> AgentResult:
        """执行单个 prompt"""
        start_time = time.time()
        error_msg = ""
        self._usage = {}
        self._transcript = []

        # 使用传入的 workspace 或默认的
        if workspace is not None:
            workspace.mkdir(parents=True, exist_ok=True)
            current_workspace = workspace
        else:
            current_workspace = self.workspace

        # 更新工具的 workspace
        for tool in self._tools._tools.values():
            if hasattr(tool, 'workspace'):
                tool.workspace = current_workspace
            if hasattr(tool, '_workspace'):
                tool._workspace = current_workspace

        try:
            # 构建消息，支持基于 session_id 的跨调用上下文持久化
            messages = self._load_session_messages(session_id)
            messages.append({"role": "user", "content": prompt})

            # 使用 asyncio 运行
            content = asyncio.run(self._run_loop(messages))
            self._save_session_messages(session_id, messages)

        except Exception as e:
            content = ""
            error_msg = str(e)
            self._transcript = []  # 清空 transcript

        execution_time = time.time() - start_time

        # 确定状态
        status = "success"
        if error_msg:
            status = "error"
            if "timed out" in error_msg.lower():
                status = "timeout"

        return AgentResult(
            status=status,
            content=content,
            transcript=self._transcript,
            usage=self._usage,
            workspace=str(current_workspace),
            execution_time=execution_time,
            error=error_msg,
        )

    def execute_multi(self, prompts: List[str], session_id: str | None = None, workspace: Path | None = None) -> List[AgentResult]:
        """执行多轮对话"""
        results = []
        for prompt in prompts:
            result = self.execute(prompt, session_id, workspace=workspace)
            results.append(result)

        return results

    def cleanup(self) -> None:
        """清理资源"""
        pass
