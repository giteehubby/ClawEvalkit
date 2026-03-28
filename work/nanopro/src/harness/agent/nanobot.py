"""
NanoBot Agent 适配器。

直接 import nanobot 代码来执行任务。
"""

import asyncio
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加 nanobot 源码路径 (nanobot/ 与 src/ 平级，nanobot/ 包含 nanobot Python 模块)
NANOBOT_PATH = Path(__file__).parent.parent.parent.parent / "nanobot"
sys.path.insert(0, str(NANOBOT_PATH))

import litellm
from litellm import acompletion
from .base import AgentResult, BaseAgent
from .memory import MemoryConfig, EpisodicMemoryStore
from .control import ControlConfig, PlanFirst, ReplanTrigger, FailureReflection, PreflightCheck, RetryPolicy
from .collaboration import CollabConfig, HandoffManager, PlannerRole, ExecutorRole, VerifierRole, get_collab_summary
from .procedure import ProceduralConfig, ProceduralStore, ProceduralTrigger, ProceduralExpander, get_procedure_summary
from nanobot.bus.queue import MessageBus
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, ListDirTool, EditFileTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.message import MessageTool


class NanoBotAgent(BaseAgent):
    """NanoBot Agent 实现 - 使用 litellm 直接调用"""
    _logger = logging.getLogger("agent.nanobot")

    def __init__(
        self,
        model: str,
        api_url: str,
        api_key: str,
        workspace: Path,
        timeout: int = 300,
        memory_config: MemoryConfig | None = None,
        control_config: ControlConfig | None = None,
        collab_config: CollabConfig | None = None,
        procedural_config: ProceduralConfig | None = None,
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

        # 初始化 memory store
        self._memory_config = memory_config or MemoryConfig(enabled=False)
        self._memory_store = EpisodicMemoryStore(self._memory_config)

        # 初始化 control 模块
        self._control_config = control_config or ControlConfig(enabled=False)
        self._init_control_modules()

        # 初始化 collaboration 模块 (T3)
        self._collab_config = collab_config or CollabConfig(enabled=False)
        self._init_collab_modules()

        # 初始化 procedural 模块 (T4)
        self._procedural_config = procedural_config or ProceduralConfig(enabled=False)
        self._init_procedural_modules()

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
        self._thread_local = threading.local()
        self._conversation_history: List[Dict] = []

        # Skills loading (T1 baseline skills)
        self._skills_summary: Optional[str] = None
        self._load_workspace_skills(workspace)

    @property
    def _transcript(self) -> List[Dict]:
        """Thread-local transcript storage."""
        if not hasattr(self._thread_local, 'transcript'):
            self._thread_local.transcript = []
        return self._thread_local.transcript

    @_transcript.setter
    def _transcript(self, value: List[Dict]) -> None:
        """Thread-local transcript storage setter for reset operations."""
        self._thread_local.transcript = value

    def _session_file(self, session_id: str) -> Path:
        safe_name = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in session_id)
        return self.session_store_dir / f"{safe_name}.json"

    def _load_session_messages(self, session_id: str | None) -> List[Dict[str, Any]]:
        if not session_id:
            return []

        session_file = self._session_file(session_id)
        if not session_file.exists():
            base_messages: List[Dict[str, Any]] = []
            # 注入 skills summary 到 system prompt 之前
            if self._skills_summary:
                base_messages.append({"role": "system", "content": self._skills_summary})
            if self.system_prompt:
                base_messages.append({"role": "system", "content": self.system_prompt})
            return base_messages

        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                # 如果 session 已有内容但没有 skills summary，注入它
                if self._skills_summary and not any(
                    "skills" in msg.get("content", "").lower()[:100] for msg in data if msg.get("role") == "system"
                ):
                    # 在第一个 system message 前插入 skills
                    has_system = any(msg.get("role") == "system" for msg in data)
                    if has_system:
                        # 找到第一个 system message 的位置
                        for i, msg in enumerate(data):
                            if msg.get("role") == "system":
                                data.insert(i, {"role": "system", "content": self._skills_summary})
                                break
                    else:
                        data.insert(0, {"role": "system", "content": self._skills_summary})
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
            workspace=self.workspace,
        ))

        # 注册 web 工具
        self._tools.register(WebSearchTool())
        self._tools.register(WebFetchTool())

        # 不注册消息工具（不需要发送到其他 channel）

    def _load_workspace_skills(self, workspace: Path) -> None:
        """从 workspace 加载 skills 并构建 summary

        Args:
            workspace: 工作空间目录
        """
        try:
            from nanobot.agent.skills import SkillsLoader

            skills_loader = SkillsLoader(workspace)
            all_skills = skills_loader.list_skills(filter_unavailable=False)

            if all_skills:
                self._skills_summary = skills_loader.build_skills_summary()
                self._logger.info(f"Loaded {len(all_skills)} skills from workspace")
            else:
                self._skills_summary = None
                self._logger.debug("No skills found in workspace")
        except Exception as e:
            self._skills_summary = None
            self._logger.debug(f"Failed to load workspace skills: {e}")

    def _init_control_modules(self) -> None:
        """初始化 control 模块"""
        config = self._control_config

        # PlanFirst
        self._plan_first = PlanFirst(config.plan_first, self)

        # ReplanTrigger
        self._replan_trigger = ReplanTrigger(config.replan)

        # FailureReflection
        self._failure_reflection = FailureReflection(config.reflection, self)

        # PreflightCheck
        self._preflight_check = PreflightCheck(
            enabled=config.preflight_enabled,
            check_params=config.preflight_check_params,
            check_suitability=config.preflight_check_suitability,
        )

        # RetryPolicy
        self._retry_policy = RetryPolicy(config.retry)

        self._logger.info(f"Control modules initialized: enabled={config.enabled}")

    def _init_collab_modules(self) -> None:
        """初始化 collaboration 模块 (T3)"""
        config = self._collab_config
        if not config.enabled:
            self._handoff_manager = None
            return

        # Create async LLM caller wrapper
        async def llm_call_fn(messages, tools=None, max_tokens=4096):
            return await self._call_llm(messages, tools=tools, max_tokens=max_tokens)

        # Create roles
        planner_model = config.planner_model or self.model
        verifier_model = config.verifier_model or self.model

        self._planner_role = PlannerRole(
            config=config,
            llm_call_fn=llm_call_fn,
            model=planner_model,
        )

        self._executor_role = ExecutorRole(
            config=config,
            llm_call_fn=llm_call_fn,
            execute_tool_fn=self._execute_tool,
            model=self.model,
        )

        if config.mode == "executor_verifier":
            self._verifier_role = VerifierRole(
                config=config,
                llm_call_fn=llm_call_fn,
                model=verifier_model,
            )
        else:
            self._verifier_role = None

        # Create handoff manager
        self._handoff_manager = HandoffManager(
            config=config,
            planner=self._planner_role,
            executor=self._executor_role,
            verifier=self._verifier_role,
        )

        self._logger.info(f"Collaboration modules initialized: mode={config.mode}, max_handoffs={config.max_handoffs}")

    def _init_procedural_modules(self) -> None:
        """初始化 procedural 模块 (T4)"""
        config = self._procedural_config
        if not config.enabled:
            self._procedural_store = None
            self._procedural_trigger = None
            self._procedural_expander = None
            return

        self._procedural_store = ProceduralStore(config)
        self._procedural_trigger = ProceduralTrigger(config, self._procedural_store)
        self._procedural_expander = ProceduralExpander()

        self._logger.info(f"Procedural modules initialized: cards_dir={config.cards_dir}, card_count={self._procedural_store.get_card_count()}")

    async def _call_llm(
        self,
        messages: List[Dict],
        tools: List[Dict] | None = None,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """调用 LLM"""
        try:
            # 确定使用的 model（添加 openrouter/ 前缀如果使用 OpenRouter）
            model = self.model
            if self.api_url and "openrouter" in self.api_url.lower():
                # 需要添加 openrouter/ 前缀
                if not model.startswith("openrouter/"):
                    model = f"openrouter/{model}"

            # 准备参数
            kwargs = {
                "model": model,
                "messages": messages,
                "api_key": self.api_key,
                "api_base": self.api_url,
                "max_tokens": max_tokens,
                "temperature": 0.1,
            }

            if tools:
                kwargs["tools"] = tools

            response = await acompletion(**kwargs)
            self._logger.debug(f"[_call_llm] response received, choices: {len(response.choices) if hasattr(response, 'choices') else 0}")

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
        current_task = ""
        # 从 messages 中提取 task description（用于 control 模块）
        for msg in messages:
            if msg.get("role") == "user":
                current_task = msg.get("content", "")[:500] if len(msg.get("content", "")) > 500 else msg.get("content", "")
                break

        # Control: Plan-first - 在第一次迭代前生成计划
        if self._control_config.enabled and self._plan_first.config.enabled:
            if self._plan_first.should_generate_plan("task_start"):
                plan = await self._plan_first.generate_plan(current_task)
                plan_context = plan.to_context()
                if plan_context:
                    self._transcript.append({
                        "type": "control_event",
                        "event": "plan_first",
                        "plan": plan_context,
                    })

        while iteration < max_iterations:
            iteration += 1
            self._memory_store.increment_iteration()

            # Control: 检查是否需要重规划
            if self._control_config.enabled and self._replan_trigger.config.enabled:
                replan_decision = self._replan_trigger.should_replan(iteration)
                if replan_decision.should_replan:
                    self._logger.info(f"Replan triggered at iteration {iteration}: {replan_decision.reason}")
                    self._transcript.append({
                        "type": "control_event",
                        "event": "replan_triggered",
                        "reason": replan_decision.reason,
                        "signals": [{"type": s.signal_type, "desc": s.description} for s in replan_decision.signals],
                    })
                    # 生成新计划
                    if self._plan_first.config.enabled:
                        new_plan = await self._plan_first.generate_plan(current_task, context="Previous plan failed. ")
                        plan_context = new_plan.to_context()
                        if plan_context:
                            self._transcript.append({
                                "type": "control_event",
                                "event": "new_plan",
                                "plan": plan_context,
                            })
                    self._replan_trigger.confirm_replan()

            # 检索 memory 并注入到 messages
            if self._memory_store.is_enabled:
                memory_context = self._memory_store.format_for_prompt()
                if memory_context:
                    # 在 system message 后插入 memory context
                    memory_msg = {
                        "role": "system",
                        "content": f"\n\n{memory_context}"
                    }
                    # 找到 system 消息的位置并插入
                    system_idx = None
                    for i, msg in enumerate(messages):
                        if msg.get("role") == "system":
                            system_idx = i
                    if system_idx is not None:
                        messages.insert(system_idx + 1, memory_msg)
                    else:
                        messages.insert(0, memory_msg)

            # T4: Procedural - 检查触发并注入 procedure context
            if self._procedural_config.enabled and self._procedural_trigger:
                self._procedural_trigger.increment_iteration()
                # Build context from recent messages
                context_for_trigger = ""
                for msg in messages[-5:]:  # Last 5 messages as context
                    if msg.get("role") == "user":
                        context_for_trigger = msg.get("content", "")[:200]
                        break

                triggered = self._procedural_trigger.check(current_task, context=context_for_trigger)
                if triggered:
                    cards = [card for card, _ in triggered]
                    # Update executor role tool defs for T3
                    if self._executor_role:
                        self._executor_role.set_tool_definitions(tool_defs)
                    # Format and inject
                    procedure_context = self._procedural_expander.format_multiple(cards)
                    # Insert after memory context if present, else after system
                    procedure_msg = {"role": "system", "content": procedure_context}
                    # Find insertion point (after memory msg if exists)
                    insert_idx = 1  # Default after system
                    for i, msg in enumerate(messages):
                        if msg.get("role") == "system" and "memory" in msg.get("content", "").lower():
                            insert_idx = i + 1
                            break
                    messages.insert(insert_idx, procedure_msg)

            # T3: Collaboration - 在第一次迭代前使用 Planner 生成计划
            if self._collab_config.enabled and self._handoff_manager and iteration == 1:
                self._executor_role.set_tool_definitions(tool_defs)
                # Build context from memory and previous messages
                collab_context = ""
                if self._memory_store.is_enabled:
                    collab_context = self._memory_store.format_for_prompt() or ""

                plan_result = await self._planner_role.generate_plan(
                    current_task,
                    context=collab_context,
                    iteration=0,
                )
                plan_events = self._planner_role.get_events()
                for event in plan_events:
                    self._transcript.append({
                        "type": "collab_event",
                        **event.to_dict(),
                    })
                if plan_result.get("plan"):
                    plan_context = f"\n## Collaborative Plan\n"
                    for step in plan_result["plan"]:
                        plan_context += f"- Step {step['step']}: {step['description']}\n"
                    # Insert plan after procedure context if present
                    plan_msg = {"role": "system", "content": plan_context}
                    messages.insert(len([m for m in messages if m.get("role") == "system"]) - 1 if any(m.get("role") == "system" for m in messages) else 0, plan_msg)

            # 调用 LLM
            try:
                response = await self._call_llm(messages, tools=tool_defs)
            except Exception as e:
                self._logger.error(f"[_run_loop] _call_llm exception: {type(e).__name__}: {e}")
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
                tool_name = tool_call.get("function", {}).get("name", "")

                # 解析参数
                args_str = tool_call["function"]["arguments"]
                if isinstance(args_str, str):
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {"raw": args_str}
                else:
                    args = args_str

                # Control: Preflight check
                if self._control_config.enabled and self._preflight_check.enabled:
                    preflight_result = self._preflight_check.check_tool_call(tool_name, args, current_task)
                    if not preflight_result.passed:
                        self._logger.warning(f"Preflight check failed for {tool_name}: {preflight_result.errors}")
                        self._transcript.append({
                            "type": "control_event",
                            "event": "preflight_failed",
                            "tool": tool_name,
                            "errors": preflight_result.errors,
                            "warnings": preflight_result.warnings,
                        })
                    elif preflight_result.warnings:
                        self._transcript.append({
                            "type": "control_event",
                            "event": "preflight_warning",
                            "tool": tool_name,
                            "warnings": preflight_result.warnings,
                        })

                # Control: Retry policy
                tool_result = ""
                if self._control_config.enabled and self._retry_policy.config.enabled:
                    success, result = await self._retry_policy.execute_with_retry(
                        tool_name,
                        self._execute_tool,
                        tool_call,
                    )
                    tool_result = result if success else result
                else:
                    tool_result = await self._execute_tool(tool_call)

                is_error = tool_result.startswith("Error:")

                # Control: 记录错误和重试信号
                if is_error:
                    error_msg = tool_result
                    self._replan_trigger.record_error(error_msg, iteration, tool_name)
                    self._replan_trigger.record_action(f"{tool_name}({args.get('path', args.get('command', ''))})")

                    if self._failure_reflection.config.enabled:
                        self._failure_reflection.record_failure(
                            iteration=iteration,
                            tool_name=tool_name,
                            error_message=error_msg,
                            error_type="execution_error",
                            context=current_task,
                        )

                # Control: 成功后重置失败计数
                if not is_error and self._failure_reflection.config.enabled:
                    self._failure_reflection.record_success()

                # Control: Failure reflection
                if self._control_config.enabled and self._failure_reflection.config.enabled:
                    if self._failure_reflection.should_reflect():
                        reflection = await self._failure_reflection.reflect()
                        self._transcript.append({
                            "type": "control_event",
                            "event": "failure_reflection",
                            "reflection": reflection.reflection_text,
                            "root_cause": reflection.root_cause,
                            "suggested_correction": reflection.suggested_correction,
                        })

                # 写入 memory (根据 write policy)
                event_type = "error" if is_error else "tool_result"
                if self._memory_store.should_write_event(event_type, tool_result):
                    self._memory_store.write(
                        content=tool_result,
                        source=event_type,
                        source_detail=tool_name,
                        memory_type="error" if is_error else "result",
                    )
                    self._logger.debug(f"[_run_loop] Wrote {event_type} to memory: {tool_name}")

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

        # 重置 memory store
        self._memory_store.reset()

        # 重置 control 模块状态
        if self._control_config.enabled:
            self._replan_trigger.reset()
            self._failure_reflection.clear()
            self._retry_policy.reset()
            self._preflight_check.clear_history()
            self._plan_first.clear()

        # 重置 collaboration 模块状态 (T3)
        if self._collab_config.enabled and self._handoff_manager:
            self._handoff_manager._handoff_count = 0

        # 重置 procedural 模块状态 (T4)
        if self._procedural_config.enabled and self._procedural_trigger:
            self._procedural_trigger.reset()

        self._logger.debug(f"[execute] prompt length: {len(prompt)}, session_id: {session_id}, workspace: {workspace}")

        # 使用传入的 workspace 或默认的
        if workspace is not None:
            workspace.mkdir(parents=True, exist_ok=True)
            current_workspace = workspace
        else:
            current_workspace = self.workspace

        # 如果 workspace 发生变化，重新加载 skills
        if current_workspace != self.workspace:
            self._load_workspace_skills(current_workspace)

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
            self._logger.debug(f"[execute] _run_loop returned, content length: {len(content) if content else 0}, transcript entries: {len(self._transcript)}")
            self._save_session_messages(session_id, messages)

        except Exception as e:
            self._logger.error(f"[execute] Exception caught: {type(e).__name__}: {e}")
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

        # 记录 memory summary 到 transcript
        if self._memory_store.is_enabled and self._transcript:
            memory_summary = self._memory_store.get_summary()
            self._transcript.append({
                "type": "memory_event",
                "event": "memory_summary",
                "summary": memory_summary,
            })
            self._logger.debug(f"[execute] Memory summary: {memory_summary}")

        # 记录 control summary 到 transcript
        if self._control_config.enabled and self._transcript:
            control_summary = {
                "replan_stats": self._replan_trigger.get_replan_stats(),
                "failure_stats": self._failure_reflection.get_failure_stats(),
                "retry_stats": self._retry_policy.get_retry_stats(),
                "preflight_stats": self._preflight_check.get_check_stats(),
            }
            self._transcript.append({
                "type": "control_event",
                "event": "control_summary",
                "summary": control_summary,
            })
            self._logger.debug(f"[execute] Control summary: {control_summary}")

        # 记录 collaboration summary 到 transcript (T3)
        if self._collab_config.enabled and self._transcript:
            collab_summary = None
            if self._handoff_manager:
                collab_summary = self._handoff_manager.get_summary()
            if collab_summary is None:
                collab_summary = {"enabled": True, "mode": self._collab_config.mode}
            self._transcript.append({
                "type": "collab_event",
                "event": "collab_summary",
                "summary": collab_summary,
            })
            self._logger.debug(f"[execute] Collaboration summary: {collab_summary}")

        # 记录 procedural summary 到 transcript (T4)
        if self._procedural_config.enabled and self._transcript:
            proc_summary = None
            if self._procedural_trigger and self._procedural_expander:
                proc_summary = get_procedure_summary(
                    self._procedural_trigger.get_events(),
                    self._procedural_expander.get_events(),
                )
            if proc_summary is None:
                proc_summary = {"enabled": True, "cards_dir": self._procedural_config.cards_dir}
            self._transcript.append({
                "type": "procedural_event",
                "event": "procedural_summary",
                "summary": proc_summary,
            })
            self._logger.debug(f"[execute] Procedural summary: {proc_summary}")

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
