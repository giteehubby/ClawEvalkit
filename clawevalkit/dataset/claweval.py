"""ClawEval — 300 task benchmark integrated from benchmarks/claw-eval.

Uses NanoBotAgent (litellm) + Docker sandbox mode.
Reuses claw-eval's task loading, mock services, Docker sandbox, grader scoring.

Workflow per task:
  1. TaskDefinition.from_yaml()         ← claw-eval
  2. ServiceManager(task.services)      ← claw-eval (start mock services)
  3. SandboxRunner.start_container()    ← claw-eval (Docker sandbox)
  4. Inject fixture files               ← claw-eval
  5. NanoBotAgent.execute(prompt)       ← ClawEvalKit's agent
  6. Collect audit data from mock services
  7. Convert NanoBotAgent transcript → claw-eval TraceMessage[] + ToolDispatch[]
  8. grader.grade(messages, dispatches, task, audit_data, ...) ← claw-eval
  9. Compute score → save to ClawEvalKit output format
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ..utils.nanobot import import_nanobot_agent
from ..utils.log import log
from .base import BaseBenchmark

# ---------------------------------------------------------------------------
# claw-eval imports (add to sys.path first)
# ---------------------------------------------------------------------------
_CLAW_EVAL_SRC = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "claw-eval" / "src"
if str(_CLAW_EVAL_SRC) not in sys.path:
    sys.path.insert(0, str(_CLAW_EVAL_SRC))

# Ensure localhost traffic bypasses proxy for mock services
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")


class ClawEval(BaseBenchmark):
    DISPLAY_NAME = "ClawEval"
    TASK_COUNT = 300
    SCORE_RANGE = "0-1"

    # Path to claw-eval benchmark data
    CLAW_EVAL_ROOT = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "claw-eval"
    TASKS_DIR = CLAW_EVAL_ROOT / "tasks"

    def __init__(self, **kwargs):
        super().__init__()
        self._docker_image = "claw-eval-agent:latest"

    # ------------------------------------------------------------------
    # Docker image management
    # ------------------------------------------------------------------

    def _ensure_docker_image(self) -> None:
        """Check if claw-eval-agent:latest exists; build if not."""
        try:
            import docker
            client = docker.from_env()
            try:
                client.images.get(self._docker_image)
                log(f"[claweval] Docker image '{self._docker_image}' found")
            except docker.errors.ImageNotFound:
                log(f"[claweval] Building Docker image '{self._docker_image}'...")
                dockerfile_dir = self.CLAW_EVAL_ROOT
                client.images.build(
                    path=str(dockerfile_dir),
                    dockerfile="Dockerfile.agent",
                    tag=self._docker_image,
                    rm=True,
                )
                log(f"[claweval] Image built: {self._docker_image}")
            finally:
                client.close()
        except ImportError:
            raise ImportError("Docker package required. Install with: pip install docker")

    # ------------------------------------------------------------------
    # Transcript saving (consistent with other benches)
    # ------------------------------------------------------------------

    def _save_transcript(self, model_key: str, task_id: str, transcript: list):
        """保存 agent 轨迹到文件（统一结构）。

        保存到: outputs/claweval/transcripts/{model}/{task}/transcript.json
        保存 _convert_transcript() 之前的原始格式（normalize 后）。
        """
        try:
            trans_path = self.results_dir / "claweval" / "transcripts" / model_key / task_id
            trans_path.mkdir(parents=True, exist_ok=True)
            normalized = [
                e["message"] if isinstance(e, dict) and "message" in e else e
                for e in transcript
            ]
            (trans_path / "transcript.json").write_text(
                json.dumps(normalized, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass  # transcript 保存失败不影响主流程

    # ------------------------------------------------------------------
    # Transcript conversion: NanoBotAgent → claw-eval format
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_transcript(
        transcript: list[dict],
        trace_id: str,
        task,
        sandbox_url: str | None = None,
    ) -> tuple[list, list]:
        """Convert NanoBotAgent transcript to claw-eval TraceMessage[] + ToolDispatch[].

        NanoBotAgent transcript format (actual):
          - {type: "message", message: {role: "user", content: [text_str]}}
          - {type: "message", message: {role: "assistant", content: [{type: "text", text: ...}, {type: "toolCall", name: ..., params: ...}]}}
          - {type: "message", message: {role: "tool", tool_call_id: ..., content: result_str}}
          - {type: "control_event", ...} (ignored for grading)
          - {type: "collab_event", ...} (ignored)

        Returns (messages: list[TraceMessage], dispatches: list[ToolDispatch])
        """
        from claw_eval.models.trace import TraceMessage, ToolDispatch, TokenUsage
        from claw_eval.models.message import Message
        from claw_eval.models.content import TextBlock, ToolUseBlock, ToolResultBlock

        endpoint_map = task.get_endpoint_map() if hasattr(task, "get_endpoint_map") else {}
        messages = []
        dispatches = []
        # Map tool_call_id → pending dispatch info for matching with tool results
        pending_tool_calls: dict[str, dict] = {}

        for entry in transcript:
            entry_type = entry.get("type", "")

            if entry_type != "message":
                # Skip control_event, collab_event, procedural_event, memory_event, etc.
                continue

            msg_data = entry.get("message", {})
            role = msg_data.get("role", "user")
            content_raw = msg_data.get("content", "")

            if role == "user":
                # User message: content is [text_str]
                if isinstance(content_raw, list):
                    text = "\n".join(str(c) for c in content_raw)
                else:
                    text = str(content_raw) if content_raw else ""
                msg = Message(role="user", content=[TextBlock(text=text)])
                messages.append(TraceMessage(trace_id=trace_id, message=msg))

            elif role == "assistant":
                # Assistant message: content = [{type: "text", text: ...}, {type: "toolCall", name, params}]
                blocks = []
                if isinstance(content_raw, list):
                    for block in content_raw:
                        if isinstance(block, str):
                            blocks.append(TextBlock(text=block))
                        elif isinstance(block, dict):
                            btype = block.get("type", "")
                            if btype == "text":
                                blocks.append(TextBlock(text=block.get("text", "")))
                            elif btype == "toolCall":
                                tool_name = block.get("name", "")
                                params = block.get("params", {})
                                tool_use_id = f"toolu_{uuid.uuid4().hex[:24]}"

                                blocks.append(ToolUseBlock(
                                    id=tool_use_id,
                                    name=tool_name,
                                    input=params if isinstance(params, dict) else {},
                                ))

                                # Create a ToolDispatch for this tool call
                                ep = endpoint_map.get(tool_name)
                                endpoint_url = ep.url if ep else (sandbox_url or "http://localhost")
                                dispatches.append(ToolDispatch(
                                    trace_id=trace_id,
                                    tool_use_id=tool_use_id,
                                    tool_name=tool_name,
                                    endpoint_url=endpoint_url,
                                    request_body=params if isinstance(params, dict) else {},
                                    response_status=200,
                                    response_body=None,
                                    latency_ms=0.0,
                                ))
                                # Track for matching with tool result
                                pending_tool_calls[tool_use_id] = {
                                    "dispatch_idx": len(dispatches) - 1,
                                    "tool_name": tool_name,
                                }
                elif isinstance(content_raw, str):
                    blocks.append(TextBlock(text=content_raw))

                msg = Message(role="assistant", content=blocks)
                messages.append(TraceMessage(trace_id=trace_id, message=msg))

            elif role == "tool":
                # Tool result: {tool_call_id, content: result_str}
                tool_call_id = msg_data.get("tool_call_id", "")
                result_text = content_raw if isinstance(content_raw, str) else str(content_raw)

                # Try to match with a pending dispatch
                response_status = 200
                response_body = result_text

                # Parse result to extract status/body
                try:
                    parsed = json.loads(result_text)
                    if isinstance(parsed, dict):
                        response_status = parsed.get("status_code", parsed.get("status", 200))
                        if isinstance(response_status, int) and response_status >= 400:
                            pass  # keep the error status
                        else:
                            response_status = 200
                        response_body = parsed.get("body", parsed.get("content", parsed))
                except (json.JSONDecodeError, TypeError):
                    pass

                # Find matching dispatch and update response
                if tool_call_id in pending_tool_calls:
                    info = pending_tool_calls.pop(tool_call_id)
                    idx = info["dispatch_idx"]
                    d = dispatches[idx]
                    dispatches[idx] = ToolDispatch(
                        trace_id=d.trace_id,
                        tool_use_id=d.tool_use_id,
                        tool_name=d.tool_name,
                        endpoint_url=d.endpoint_url,
                        request_body=d.request_body,
                        response_status=response_status,
                        response_body=response_body,
                        latency_ms=d.latency_ms,
                    )
                else:
                    # No matching dispatch — this might be from the initial user content
                    # or a tool result without a prior call in transcript
                    pass

                # Also add as a message with ToolResultBlock
                result_blocks = [TextBlock(text=result_text)]
                msg = Message(role="user", content=[
                    ToolResultBlock(
                        tool_use_id=tool_call_id,
                        content=result_blocks,
                        is_error=response_status >= 400 if isinstance(response_status, int) else False,
                    )
                ])
                messages.append(TraceMessage(trace_id=trace_id, message=msg))

        return messages, dispatches

    # ------------------------------------------------------------------
    # Collect audit data from mock services
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_audit_data(task) -> dict[str, dict]:
        """Collect audit data from all mock services' /audit endpoints."""
        import httpx

        audit_data = {}
        if not hasattr(task, "services") or not task.services:
            return audit_data

        client = httpx.Client(timeout=10.0, trust_env=False)
        try:
            for svc in task.services:
                audit_url = f"http://localhost:{svc.port}/audit"
                try:
                    resp = client.get(audit_url)
                    if resp.status_code == 200:
                        audit_data[svc.name] = resp.json()
                except Exception as exc:
                    log(f"[claweval] audit collection failed for {svc.name}: {exc}")
        finally:
            client.close()

        return audit_data

    # ------------------------------------------------------------------
    # Collect env snapshot from sandbox container
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_env_snapshot(sandbox_url: str, task) -> dict:
        """Collect environment data from container after agent loop."""
        import httpx

        timeout = getattr(task.environment, "env_snapshot_timeout", 10) if hasattr(task, "environment") else 10
        client = httpx.Client(timeout=max(timeout + 5, 15.0))
        snapshot: dict = {}

        try:
            # Run commands first
            for cmd in getattr(task, "env_snapshot_commands", []):
                try:
                    resp = client.post(
                        f"{sandbox_url}/exec",
                        json={"command": cmd, "timeout_seconds": timeout},
                    )
                    snapshot[f"cmd:{cmd}"] = resp.json()
                except Exception as exc:
                    snapshot[f"cmd:{cmd}"] = {"error": str(exc)}

            # Collect files after commands
            for pattern in getattr(task, "env_snapshot_files", []):
                try:
                    if "*" in pattern or "?" in pattern:
                        resp = client.post(
                            f"{sandbox_url}/glob",
                            json={"pattern": pattern, "max_files": 50},
                        )
                        file_list = resp.json().get("files", [])
                        for f in file_list:
                            try:
                                resp2 = client.post(
                                    f"{sandbox_url}/read",
                                    json={"path": f["path"]},
                                )
                                snapshot[f"file:{f['path']}"] = resp2.json()
                            except Exception as exc:
                                snapshot[f"file:{f['path']}"] = {"error": str(exc)}
                    else:
                        resp = client.post(
                            f"{sandbox_url}/read",
                            json={"path": pattern},
                        )
                        snapshot[f"file:{pattern}"] = resp.json()
                except Exception as exc:
                    snapshot[f"file:{pattern}"] = {"error": str(exc)}
        finally:
            client.close()

        return snapshot

    # ------------------------------------------------------------------
    # Make LLM Judge
    # ------------------------------------------------------------------

    @staticmethod
    def _make_judge(judge_model: str | None = None):
        """Create an LLMJudge instance if possible.

        Credential search order:
          1. JUDGE_API_KEY / JUDGE_BASE_URL (explicit judge config)
          2. GLM_API_KEY / GLM_BASE_URL (fast, cheap, always available)
          3. OPENROUTER_API_KEY / OPENROUTER_BASE_URL (fallback)
        """
        from claw_eval.graders.llm_judge import LLMJudge

        # 1) Explicit judge config
        api_key = os.environ.get("JUDGE_API_KEY")
        base_url = os.environ.get("JUDGE_BASE_URL")
        model_id = judge_model or os.environ.get("JUDGE_MODEL")

        # 2) GLM (fast & cheap)
        if not api_key:
            api_key = os.environ.get("GLM_API_KEY")
            base_url = os.environ.get("GLM_BASE_URL")
            if not model_id:
                model_id = "glm-4-flash"

        # 3) OpenRouter fallback
        if not api_key:
            api_key = os.environ.get("OPENROUTER_API_KEY")
            base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
            if not model_id:
                model_id = "google/gemini-2.0-flash-001"

        if not api_key:
            log("[claweval] No judge API key found, skipping LLM judge")
            return None

        try:
            return LLMJudge(model_id=model_id, api_key=api_key, base_url=base_url)
        except Exception as exc:
            log(f"[claweval] Judge init failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Grade with optional params
    # ------------------------------------------------------------------

    @staticmethod
    def _grade_with_optional_params(grader, messages, dispatches, task, *, audit_data, judge, media_events=None, env_snapshot=None):
        """Call grader.grade, passing optional params only when accepted."""
        if hasattr(judge, "reset_call_log"):
            judge.reset_call_log()

        params = inspect.signature(grader.grade).parameters
        kwargs = {"audit_data": audit_data, "judge": judge}
        if "media_events" in params and media_events is not None:
            kwargs["media_events"] = media_events
        if "env_snapshot" in params and env_snapshot is not None:
            kwargs["env_snapshot"] = env_snapshot
        scores = grader.grade(messages, dispatches, task, **kwargs)

        judge_calls = judge.get_call_log() if hasattr(judge, "get_call_log") else []
        return scores, judge_calls

    # ------------------------------------------------------------------
    # Build system prompt for NanoBotAgent
    # ------------------------------------------------------------------

    @staticmethod
    def _build_agent_system_prompt(task, sandbox_url: str | None = None) -> str:
        """Build a system prompt that includes task tool descriptions and sandbox info.

        The agent has built-in tools (ExecTool, ReadFileTool, WriteFileTool, etc.)
        from NanoBotAgent. We describe the task's mock service tools as HTTP endpoints
        that the agent should call using shell commands (curl).
        """
        parts = [
            "You are a helpful personal assistant.",
            "You have access to shell commands via the exec tool.",
        ]

        # Tool descriptions
        if task.tools:
            parts.append("\n## Available API Tools")
            parts.append("Call these tools via curl. Each tool has a specific HTTP endpoint.")
            for tool in task.tools:
                schema_str = json.dumps(tool.input_schema, ensure_ascii=False, indent=2)
                parts.append(f"\n### {tool.name}")
                parts.append(f"{tool.description}")
                parts.append(f"Input schema:\n```json\n{schema_str}\n```")

            # Tool endpoint mapping — critical for the agent to know where to send requests
            if task.tool_endpoints:
                parts.append("\n## Tool Endpoint URLs")
                for ep in task.tool_endpoints:
                    method = ep.method.upper()
                    parts.append(f"- `{ep.tool_name}` → {method} {ep.url}")
                parts.append("\nExample: To call a tool, use curl:")
                parts.append('  curl -X POST <endpoint_url> -H "Content-Type: application/json" -d \'{"param": "value"}\'')

        # Sandbox info
        if sandbox_url:
            parts.append(f"\n## Sandbox Environment")
            parts.append(f"You are running inside a sandbox. Use curl to interact with it:")
            parts.append(f"- Write file: curl -X POST {sandbox_url}/write -H 'Content-Type: application/json' -d '{{\"path\": \"/workspace/<path>\", \"content\": \"<text>\"}}'")
            parts.append(f"- Execute command: curl -X POST {sandbox_url}/exec -H 'Content-Type: application/json' -d '{{\"command\": \"<cmd>\"}}'")
            parts.append(f"- Read file: curl -X POST {sandbox_url}/read -H 'Content-Type: application/json' -d '{{\"path\": \"/workspace/<path>\"}}'")

        # Fixtures hint
        fixtures = getattr(task.environment, "fixtures", [])
        sandbox_files = getattr(task, "sandbox_files", [])
        files_list = sandbox_files if sandbox_files else fixtures
        if files_list:
            parts.append(f"\n## Pre-loaded Files")
            parts.append("The following files are available in the sandbox /workspace/:")
            for f in files_list:
                parts.append(f"  - /workspace/{f}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Run a single task
    # ------------------------------------------------------------------

    def _run_single_task(
        self,
        task_dir: Path,
        model_key: str,
        config: dict,
        judge_model: str | None,
        *,
        port_offset: int = 0,
        max_turns: int | None = None,
        transcripts_dir: str | None = None,
    ) -> dict:
        """Execute a single claw-eval task and return result dict."""
        from claw_eval.models.task import TaskDefinition
        from claw_eval.models.scoring import compute_task_score, is_pass
        from claw_eval.runner.services import ServiceManager
        from claw_eval.runner.sandbox_runner import SandboxRunner
        from claw_eval.config import SandboxConfig
        from claw_eval.graders.registry import get_grader

        NanoBotAgent = import_nanobot_agent()
        # Create a fresh judge per task (thread-safe)
        judge = self._make_judge(judge_model)

        task_yaml = task_dir / "task.yaml"
        if not task_yaml.exists():
            return {"task_id": task_dir.name, "error": "no task.yaml", "score": 0.0}

        task = TaskDefinition.from_yaml(task_yaml)

        # Apply port offset for parallel execution
        if port_offset:
            task.apply_port_offset(port_offset)

        # Override max_turns if specified
        if max_turns:
            task.environment.max_turns = max_turns

        trace_id = f"{task.task_id}-{uuid.uuid4().hex[:8]}"
        task_timeout = task.environment.timeout_seconds

        # Setup sandbox config
        sandbox_config = SandboxConfig(image=self._docker_image)

        result = {
            "task_id": task.task_id,
            "task_name": task.task_name,
            "category": task.category,
            "difficulty": task.difficulty,
        }

        try:
            # Start services (cwd=CLAW_EVAL_ROOT so mock_services/ paths resolve)
            with ServiceManager(task.services, cwd=self.CLAW_EVAL_ROOT) as svc:
                # Start sandbox container
                runner = SandboxRunner(sandbox_config)
                run_id = f"{task.task_id}-{uuid.uuid4().hex[:6]}"
                handle = runner.start_container(run_id=run_id)

                try:
                    # Inject fixture files into container
                    runner.inject_files(handle, task, task_dir=str(task_dir))

                    # Build system prompt
                    system_prompt = self._build_agent_system_prompt(task, handle.sandbox_url)

                    # Create temp workspace for NanoBotAgent
                    with tempfile.TemporaryDirectory(prefix=f"claweval_{task.task_id}_") as tmp_ws:
                        workspace = Path(tmp_ws)

                        # Setup NanoBotAgent
                        agent = NanoBotAgent(
                            model=config.get("model_id", config.get("model", model_key)),
                            api_url=config.get("api_url", config.get("base_url", "")),
                            api_key=config.get("api_key", ""),
                            workspace=workspace,
                            timeout=task_timeout,
                            system_prompt=system_prompt,
                        )

                        # Execute agent (pass max_iterations from task config)
                        start_time = time.monotonic()
                        agent_result = agent.execute(
                            task.prompt.text,
                            max_iterations=task.environment.max_turns or 100,
                        )
                        wall_time = time.monotonic() - start_time

                    # Inject grader-only files AFTER agent loop
                    runner.inject_grader_files(handle, task, task_dir=str(task_dir))

                    # Collect env snapshot
                    env_snapshot = self._collect_env_snapshot(handle.sandbox_url, task)

                    # Add local grader files
                    if task.local_grader_files:
                        import base64 as _b64
                        task_root = task_dir
                        for rel_path in task.local_grader_files:
                            local_path = task_root / rel_path
                            if local_path.exists():
                                content = _b64.b64encode(local_path.read_bytes()).decode()
                                env_snapshot[f"local_file:{rel_path}"] = {
                                    "encoding": "base64",
                                    "content": content,
                                }

                finally:
                    runner.stop_container(handle)

                # Collect audit data from mock services
                audit_data = self._collect_audit_data(task)

                # Save raw transcript (before _convert_transcript, consistent with other benches)
                raw_transcript = agent_result.transcript or []
                if transcripts_dir and raw_transcript:
                    self._save_transcript(model_key, task.task_id, raw_transcript)

                # Convert transcript
                messages, dispatches = self._convert_transcript(
                    agent_result.transcript or [],
                    trace_id,
                    task,
                    sandbox_url=handle.sandbox_url if handle else None,
                )

                # Grade
                grader = get_grader(task.task_id, tasks_dir=str(self.TASKS_DIR), task_dir=str(task_dir))
                scores, judge_calls = self._grade_with_optional_params(
                    grader, messages, dispatches, task,
                    audit_data=audit_data,
                    judge=judge,
                    media_events=None,
                    env_snapshot=env_snapshot,
                )
                task_score = compute_task_score(scores)
                passed = is_pass(task_score)

                result.update({
                    "score": task_score,
                    "passed": passed,
                    "completion": scores.completion,
                    "robustness": scores.robustness,
                    "communication": scores.communication,
                    "safety": scores.safety,
                    "wall_time_s": wall_time,
                    "status": agent_result.status,
                    "judge_calls": len(judge_calls),
                    "turns": len([m for m in messages if m.message.role == "assistant"]),
                    "dispatches": len(dispatches),
                })

        except Exception as exc:
            import traceback
            result.update({
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "score": 0.0,
                "passed": False,
            })
            log(f"[claweval] Task {task.task_id} failed: {exc}")

        return result

    # ------------------------------------------------------------------
    # Main evaluate entry point
    # ------------------------------------------------------------------

    def evaluate(self, model_key: str, config: dict, sample: int = 0, **kwargs) -> dict:
        """Run ClawEval evaluation.

        Args:
            model_key: Model identifier (e.g., "minimax-m2.7")
            config: Model config dict with api_url, api_key, model_id
            sample: Number of tasks to sample (0 = all 300)
            **kwargs: parallel, max_turns, judge_model, task_ids, category

        Returns:
            {"score": float, "scored": int, "total": int, ...}
        """
        from claw_eval.models.scoring import compute_pass_at_k, compute_pass_hat_k

        # Ensure Docker image is available
        self._ensure_docker_image()

        # Collect all task directories
        task_dirs = sorted([
            d for d in self.TASKS_DIR.iterdir()
            if d.is_dir() and (d / "task.yaml").exists()
        ])

        if not task_dirs:
            return {"score": 0, "total": 0, "error": "No tasks found"}

        # Filter by task_ids or category
        task_ids = kwargs.get("task_ids")
        category = kwargs.get("category")
        if task_ids:
            task_dirs = [d for d in task_dirs if d.name in task_ids]
        if category:
            filtered = []
            for d in task_dirs:
                from claw_eval.models.task import TaskDefinition
                try:
                    task = TaskDefinition.from_yaml(d / "task.yaml")
                    if task.category == category:
                        filtered.append(d)
                except Exception:
                    pass
            task_dirs = filtered

        # Sample tasks if requested
        if sample and sample < len(task_dirs):
            import random
            random.seed(42)
            task_dirs = random.sample(task_dirs, sample)

        total = len(task_dirs)
        parallel = kwargs.get("parallel", 1)
        max_turns = kwargs.get("max_turns")
        judge_model = kwargs.get("judge_model") or os.environ.get("JUDGE_MODEL")
        transcripts_dir = kwargs.get("transcripts_dir")

        log(f"[claweval] Evaluating {total} tasks with model={model_key}, parallel={parallel}")

        # Load cached results
        all_results = []
        new_task_dirs = []
        for td in task_dirs:
            cached_file = self.results_dir / "claweval" / model_key / td.name / "result.json"
            if cached_file.exists() and not kwargs.get("force"):
                try:
                    cached = json.loads(cached_file.read_text())
                    cached["_from_cache"] = True
                    all_results.append(cached)
                    continue
                except Exception:
                    pass
            new_task_dirs.append(td)

        # Execute new tasks
        if new_task_dirs:
            if parallel > 1:
                # Slot-based port offsets for parallel execution
                port_stride = 50

                def _worker(idx_td):
                    idx, td = idx_td
                    offset = (idx % parallel) * port_stride
                    return self._run_single_task(
                        td, model_key, config, judge_model,
                        port_offset=offset,
                        max_turns=max_turns,
                        transcripts_dir=transcripts_dir,
                    )

                with ThreadPoolExecutor(max_workers=parallel) as pool:
                    futures = {
                        pool.submit(_worker, (i, td)): td
                        for i, td in enumerate(new_task_dirs)
                    }
                    for future in as_completed(futures):
                        td = futures[future]
                        try:
                            task_result = future.result()
                        except Exception as exc:
                            task_result = {
                                "task_id": td.name,
                                "error": str(exc),
                                "score": 0.0,
                                "passed": False,
                            }
                        all_results.append(task_result)
                        self._save_task_result("claweval", model_key, task_result.get("task_id", td.name), task_result)
                        done = len([r for r in all_results if not r.get("_from_cache")])
                        log(f"[claweval] {done}/{len(new_task_dirs)} new tasks done (total: {len(all_results)}/{total})")
            else:
                for i, td in enumerate(new_task_dirs):
                    task_result = self._run_single_task(
                        td, model_key, config, judge_model,
                        max_turns=max_turns,
                        transcripts_dir=transcripts_dir,
                    )
                    all_results.append(task_result)
                    self._save_task_result("claweval", model_key, task_result.get("task_id", td.name), task_result)
                    log(f"[claweval] {i+1}/{len(new_task_dirs)} new tasks done (total: {len(all_results)}/{total})")

        # Compute summary
        def compute_summary(results):
            scored = [r for r in results if "score" in r and "error" not in r]
            scores = [r["score"] for r in scored]
            passed = [r for r in scored if r.get("passed")]

            avg_score = sum(scores) / len(scores) if scores else 0.0
            pass_at_1 = compute_pass_at_k(scores, k=1) if scores else 0.0
            pass_hat_3 = compute_pass_hat_k(scores, k=3) if scores else 0.0

            # Category breakdown
            cat_scores = {}
            for r in scored:
                cat = r.get("category", "unknown")
                if cat not in cat_scores:
                    cat_scores[cat] = []
                cat_scores[cat].append(r["score"])

            category_avg = {cat: sum(v) / len(v) for cat, v in cat_scores.items()}

            return {
                "model": model_key,
                "score": round(avg_score, 4),
                "scored": len(scored),
                "total": total,
                "passed": len(passed),
                "pass_rate": round(len(passed) / len(scored), 4) if scored else 0.0,
                "pass_at_1": round(pass_at_1, 4),
                "pass_hat_3": round(pass_hat_3, 4),
                "category_scores": category_avg,
                "details": results,
            }

        all_task_ids = [d.name for d in task_dirs]
        summary = self._build_and_save_summary(
            "claweval", model_key,
            all_task_ids=all_task_ids,
            new_results=all_results,
            compute_summary_fn=compute_summary,
        )

        return summary

    # ------------------------------------------------------------------
    # Load cached results
    # ------------------------------------------------------------------

    def collect(self, model_key: str) -> dict | None:
        """Load cached evaluation results."""
        result_file = self.results_dir / "claweval" / f"{model_key}.json"
        if result_file.exists():
            try:
                return json.loads(result_file.read_text())
            except Exception:
                return None
        return None
