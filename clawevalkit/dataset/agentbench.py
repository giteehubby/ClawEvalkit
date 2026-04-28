"""AgentBench-OpenClaw — 40 tasks, L0-L3 scoring (0-100).

Scoring: NanoBotAgent execution in Docker → 4-layer scoring → composite score.

Supports two execution modes:
  - use_docker=True:  Run NanoBotAgent inside Docker container
  - use_docker=False: Run nanobot CLI on host directly
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .base import BaseBenchmark
from ._harness import build_harness_script_parts
from ..utils.log import log


DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE_NANOBOT", "clawbase-nanobot:v1")
TMP_WORKSPACE = "/tmp"


# ============================================================================
# Layer 0: Automated Structural Checks
# ============================================================================

def _check_file_exists(container_name: str, pattern: str) -> bool:
    """Check if file exists in container workspace."""
    check_proc = subprocess.run(
        ["docker", "exec", container_name, "test", "-f", f"/tmp/workspace/{pattern}"],
        capture_output=True)
    return check_proc.returncode == 0


def _find_matching_file(container_name: str, regex: str) -> str | None:
    """Find a file in container workspace matching a regex pattern. Returns filename or None."""
    import re
    proc = subprocess.run(
        ["docker", "exec", container_name, "find", "/tmp/workspace", "-maxdepth", "1", "-type", "f", "-name", "*.md"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    for line in proc.stdout.strip().split("\n"):
        fname = line.strip().rsplit("/", 1)[-1]
        if fname and re.match(regex, fname):
            return fname
    return None


def _check_directory_structure(container_name: str, expected: list[str]) -> tuple[int, int]:
    """Check if all expected paths exist. Returns (passed, total)."""
    passed = 0
    for path in expected:
        check_proc = subprocess.run(
            ["docker", "exec", container_name, "test", "-e", f"/tmp/workspace/{path}"],
            capture_output=True)
        if check_proc.returncode == 0:
            passed += 1
    return passed, len(expected)


def _check_content_contains(container_name: str, pattern: str, sections: list[str]) -> tuple[int, int]:
    """Check if file contains all required sections (case-insensitive)."""
    # Copy file from container to temp location
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as f:
        temp_path = f.name

    try:
        subprocess.run(
            ["docker", "cp", f"{container_name}:/tmp/workspace/{pattern}", temp_path],
            capture_output=True)

        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            return 0, len(sections)

        content = Path(temp_path).read_text().lower()
        passed = sum(1 for section in sections if section.lower() in content)
        return passed, len(sections)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _check_word_count_range(container_name: str, pattern: str, min_words: int, max_words: int) -> float:
    """Check if word count is within range. Returns score 0-30."""
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as f:
        temp_path = f.name

    try:
        subprocess.run(
            ["docker", "cp", f"{container_name}:/tmp/workspace/{pattern}", temp_path],
            capture_output=True)

        if not os.path.exists(temp_path):
            return 0

        content = Path(temp_path).read_text()
        word_count = len(content.split())

        if min_words <= word_count <= max_words:
            return 30
        elif min_words * 0.5 <= word_count <= max_words * 2:
            return 15
        else:
            return 0
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _check_git_log_contains(container_name: str, expected: list[str]) -> tuple[int, int]:
    """Check git log for expected strings."""
    result = subprocess.run(
        ["docker", "exec", container_name, "git", "-C", "/tmp/workspace", "log", "--oneline"],
        capture_output=True, text=True)

    if result.returncode != 0:
        return 0, len(expected)

    log_content = result.stdout.lower()
    passed = sum(1 for exp in expected if exp.lower() in log_content)
    return passed, len(expected)


def _check_command_output_contains(container_name: str, command: str, expected: list[str]) -> tuple[int, int]:
    """Run command and check output contains all expected strings."""
    result = subprocess.run(
        ["docker", "exec", container_name, "/bin/bash", "-c", f"cd /tmp/workspace && {command}"],
        capture_output=True, text=True)

    output = result.stdout + result.stderr
    passed = sum(1 for exp in expected if exp in output)
    return passed, len(expected)


def _check_link_consistency(container_name: str, files_pattern: str) -> float:
    """Check link syntax consistency in files."""
    # Get list of files
    result = subprocess.run(
        ["docker", "exec", container_name, "/bin/bash", "-c",
         f"cd /tmp/workspace && find . -path './{files_pattern}' -type f 2>/dev/null"],
        capture_output=True, text=True)

    if result.returncode != 0 or not result.stdout.strip():
        return 0

    files = result.stdout.strip().split('\n')

    # Check link styles
    link_styles = []
    for f in files:
        if not f:
            continue
        # Copy file content
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.md', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            subprocess.run(
                ["docker", "cp", f"{container_name}:/tmp/workspace/{f}", tmp_path],
                capture_output=True)
            content = Path(tmp_path).read_text()

            # Count different link styles
            wiki_links = len(re.findall(r'\[\[.*?\]\]', content))
            md_links = len(re.findall(r'\[.*?\]\(.*?\)', content))

            if wiki_links > 0 and md_links == 0:
                link_styles.append('wiki')
            elif md_links > 0 and wiki_links == 0:
                link_styles.append('md')
            else:
                link_styles.append('mixed')
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    if not link_styles:
        return 0

    # Check consistency
    unique_styles = set(link_styles)
    if len(unique_styles) == 1:
        return 30  # Fully consistent

    # Check if mostly consistent (>70% one style)
    from collections import Counter
    style_counts = Counter(link_styles)
    most_common = style_counts.most_common(1)[0][1]
    if most_common / len(link_styles) > 0.7:
        return 15

    return 0


def _compute_layer0_score(container_name: str, expected_outputs: list[dict],
                         expected_behavior: list[dict] = None, model_output: str = "") -> float:
    """Compute Layer 0 score (0-100) based on automated structural checks."""
    has_checks = expected_outputs or expected_behavior
    if not has_checks:
        return 50  # No checks, neutral score

    total_points = 0
    max_points = 0

    for output in expected_outputs:
        pattern = output.get("pattern", "")
        validators = output.get("validators", [])
        required = output.get("required", False)

        # Base points for this output
        output_max = 30 if required else 20
        output_points = 0
        # Resolve actual filename: if pattern is a regex, find matching file
        resolved_pattern = pattern if _check_file_exists(container_name, pattern) else None

        for validator in validators:
            vtype = validator.get("type", "")

            if vtype == "file-exists":
                max_points += 30
                if _check_file_exists(container_name, pattern):
                    total_points += 30
                    output_points += 30

            elif vtype == "filename-matches":
                regex = validator.get("pattern", "")
                max_points += 20
                matched = _find_matching_file(container_name, regex)
                if matched:
                    total_points += 20
                    output_points += 20
                    resolved_pattern = matched

            elif vtype == "content-contains":
                sections = validator.get("sections", [])
                max_points += 40
                check_file = resolved_pattern or pattern
                if sections and _check_file_exists(container_name, check_file):
                    passed, total = _check_content_contains(container_name, check_file, sections)
                    points = (passed / total) * 40 if total > 0 else 0
                    total_points += points
                    output_points += points

            elif vtype == "directory-structure":
                expected = validator.get("expected", [])
                max_points += 30
                if expected:
                    passed, total = _check_directory_structure(container_name, expected)
                    points = (passed / total) * 30 if total > 0 else 0
                    total_points += points
                    output_points += points

            elif vtype == "command-output-contains":
                command = validator.get("command", "")
                contains = validator.get("contains", [])
                max_points += 30
                if command and contains:
                    passed, total = _check_command_output_contains(container_name, command, contains)
                    points = (passed / total) * 30 if total > 0 else 0
                    total_points += points
                    output_points += points

            elif vtype == "link-consistency":
                max_points += 30
                points = _check_link_consistency(container_name, validator.get("files", "*.md"))
                total_points += points
                output_points += points

            elif vtype == "word-count-range":
                min_w = validator.get("min", 0)
                max_w = validator.get("max", 1000)
                max_points += 30
                points = _check_word_count_range(container_name, pattern, min_w, max_w)
                total_points += points
                output_points += points

            elif vtype == "git-log-contains":
                # 兼容两种字段名：YAML 中用 contains，也支持 expected
                expected = validator.get("expected", []) or validator.get("contains", [])
                max_points += 30
                if expected:
                    passed, total = _check_git_log_contains(container_name, expected)
                    points = (passed / total) * 30 if total > 0 else 0
                    total_points += points
                    output_points += points

        # If required output has no points, apply penalty
        if required and output_points == 0:
            total_points -= 10

    # Process expected_behavior
    if expected_behavior:
        output_lower = (model_output or "").lower()
        for behavior in expected_behavior:
            for validator in behavior.get("validators", []):
                vtype = validator.get("type", "")

                if vtype == "response-contains":
                    if not model_output:
                        continue
                    values = validator.get("values", [])
                    match_mode = validator.get("match", "any")
                    max_points += 30
                    if match_mode == "any":
                        if any(v.lower() in output_lower for v in values):
                            total_points += 30
                    elif match_mode == "all":
                        if all(v.lower() in output_lower for v in values):
                            total_points += 30

                elif vtype == "command-output-contains":
                    # 在容器内执行命令并检查输出（不依赖 model_output）
                    command = validator.get("command", "")
                    contains = validator.get("contains", [])
                    max_points += 30
                    if command and contains:
                        passed, total = _check_command_output_contains(
                            container_name, command, contains)
                        points = (passed / total) * 30 if total > 0 else 0
                        total_points += points

    # Normalize to 0-100
    if max_points == 0:
        return 50

    score = (total_points / max_points) * 100
    return max(0, min(100, score))


# ============================================================================
# Layer 1: Metrics Analysis
# ============================================================================

def _compute_layer1_score(expected_metrics: dict, transcript: list, elapsed_time: float) -> float:
    """Compute Layer 1 score (0-100) based on metrics analysis."""
    if not expected_metrics:
        return 50  # No metrics expected, neutral score

    # Normalize nested transcript format (type=message, message={role, content})
    # to flat format (role, tool_calls, content) expected by scoring logic
    # 同时检测 verify 阶段边界，只统计主任务阶段的 tool calls
    flat_transcript = []
    verify_started = False
    for entry in transcript:
        if not isinstance(entry, dict):
            continue
        # 检测 verify 阶段开始
        if entry.get("type") == "control_event" and entry.get("event") == "verify_triggered":
            verify_started = True
        if entry.get("type") == "message":
            msg = entry.get("message", {})
            flat = {"role": msg.get("role", ""), "content": msg.get("content", "")}
            if not verify_started:
                flat["pre_verify"] = True
            # Extract tool calls from nested content list
            content = msg.get("content", [])
            if isinstance(content, list):
                tc_list = [c for c in content if isinstance(c, dict) and c.get("type") == "toolCall"]
                if tc_list:
                    flat["tool_calls"] = tc_list
                # Flatten content to string for error detection
                flat["content"] = "\n".join(
                    c.get("text", "") if isinstance(c, dict) else str(c) for c in content
                )
            flat_transcript.append(flat)
        else:
            flat_transcript.append(entry)

    # 只计算 verify 前的 tool calls（主任务阶段）
    tool_calls = sum(1 for entry in flat_transcript
                     if entry.get("role") == "assistant" and entry.get("tool_calls")
                     and entry.get("pre_verify", False))

    # Estimate planning ratio (simplified: based on first tool call timing)
    planning_ratio = 0.25  # Default estimate

    # 只统计 tool 响应中的真实错误（排除 system/user 消息和控制事件）
    errors = 0
    for entry in flat_transcript:
        if entry.get("role") != "tool":
            continue
        content_str = str(entry.get("content", "")).lower()
        # 检测真实的错误信号（排除 grep 无匹配等正常退出码）
        if "error:" in content_str or "traceback" in content_str:
            errors += 1

    score = 0

    # Tool calls scoring (40 points)
    tool_range = expected_metrics.get("tool_calls", [3, 15])
    min_tools, max_tools = tool_range[0], tool_range[1]

    if min_tools <= tool_calls <= max_tools:
        score += 40
    elif min_tools * 0.5 <= tool_calls <= max_tools * 2:
        score += 20

    # Planning ratio scoring (30 points)
    ratio_range = expected_metrics.get("planning_ratio", [0.1, 0.4])
    min_ratio, max_ratio = ratio_range[0], ratio_range[1]

    if min_ratio <= planning_ratio <= max_ratio:
        score += 30
    elif min_ratio * 0.5 <= planning_ratio <= max_ratio * 2:
        score += 15

    # Error scoring (30 points)
    if errors == 0:
        score += 30
    elif errors <= 2:
        score += 15

    return score


# ============================================================================
# Docker Execution Helpers
# ============================================================================

def _start_container(container_name: str, workspace_path: str, openclawpro_dir: Path,
                     docker_image: str, env_args: list) -> None:
    """Start Docker container with selective volume mounts."""
    exec_path = os.path.join(workspace_path, "exec")
    tmp_path = os.path.join(workspace_path, "tmp")

    os.makedirs(exec_path, exist_ok=True)
    os.makedirs(tmp_path, exist_ok=True)

    volume_mounts = [
        "-v", f"{exec_path}:/tmp/exec:rw",
        "-v", f"{tmp_path}:/tmp/tmp:rw",
        "-v", f"{openclawpro_dir}:/root/OpenClawPro:ro",
    ]

    docker_run_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--network", "host",
        "--entrypoint", "/bin/bash",
        *volume_mounts,
        *env_args,
        docker_image,
        "-c", "tail -f /dev/null",
    ]
    r = subprocess.run(docker_run_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Container startup failed:\n{r.stderr}")


def _build_exec_script(model_key: str, task_id: str, user_message: str, config: dict,
                       harness_config: dict = None, turns: list = None) -> str:
    """Build NanoBotAgent execution script for running inside Docker container."""
    # Determine API key env var based on provider
    provider = config.get("provider", "openrouter")
    if provider == "minimax":
        api_key_env = "MINIMAX_API_KEY"
    elif provider == "openrouter":
        api_key_env = "OPENROUTER_API_KEY"
    elif provider == "glm":
        api_key_env = "GLM_API_KEY"
    else:
        api_key_env = "OPENROUTER_API_KEY"

    # Build harness import lines and constructor kwargs
    harness_imports, harness_kwargs_str = build_harness_script_parts(harness_config)

    # Determine if multi-turn
    is_multi_turn = turns and len(turns) > 0
    if is_multi_turn:
        # Convert turns to JSON for execute_multi (extract just the messages)
        prompts = [t.get("message", "") for t in turns]
        turns_json = json.dumps(prompts, ensure_ascii=False)
        exec_code = (
            "results = agent.execute_multi(\n"
            "    " + turns_json + ",\n"
            "    session_id=session_id,\n"
            "    workspace=workspace,\n"
            ")\n"
            "elapsed = time.time() - start_time\n"
            "# Aggregate results from all turns\n"
            "statuses = [r.status for r in results]\n"
            "contents = [r.content or '' for r in results]\n"
            "all_transcripts = []\n"
            "all_usage = {}\n"
            "for r in results:\n"
            "    all_transcripts.extend(r.transcript or [])\n"
            "    if r.usage:\n"
            "        for k, v in r.usage.items():\n"
            "            all_usage[k] = all_usage.get(k, 0) + v\n"
            "final_status = statuses[-1] if statuses else 'error'\n"
            "final_content = contents[-1] if contents else ''\n"
            "output = {\n"
            "    'status': final_status,\n"
            "    'content': final_content,\n"
            "    'transcript': all_transcripts,\n"
            "    'usage': all_usage,\n"
            "    'execution_time': elapsed,\n"
            "    'error': results[-1].error if results else 'No results',\n"
            "    'turn_count': len(results),\n"
            "}"
        )
    else:
        escaped_msg = user_message.replace("'", "\\'")
        exec_code = (
            "result = agent.execute(\n"
            "    '''" + escaped_msg + "''',\n"
            "    session_id=session_id,\n"
            "    workspace=workspace,\n"
            "    max_iterations=100,\n"
            ")\n"
            "elapsed = time.time() - start_time\n"
            "transcript_data = result.transcript or []\n"
            "transcript_file = workspace / '.sessions' / f'{session_id}.json'\n"
            "if not transcript_data and transcript_file.exists():\n"
            "    transcript_data = json.loads(transcript_file.read_text())\n"
            "output = {\n"
            "    'status': result.status,\n"
            "    'content': result.content,\n"
            "    'transcript': transcript_data,\n"
            "    'usage': result.usage or {},\n"
            "    'execution_time': elapsed,\n"
            "    'error': result.error,\n"
            "}"
        )

    # Build the full script using string concatenation
    # Indent exec_code for try block
    exec_code_indented = "\n".join("    " + line for line in exec_code.split("\n"))

    script = (
        "import sys\n"
        "import json\n"
        "import time\n"
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "sys.path.insert(0, '/root/OpenClawPro')\n"
        "from harness.agent.nanobot import NanoBotAgent\n"
        + harness_imports + "\n"
        "\n"
        "workspace = Path('/tmp/workspace')\n"
        "session_id = 'eval_" + model_key + "_" + task_id + "'\n"
        "\n"
        "# Get API key from environment variable\n"
        "api_key = os.environ.get('" + api_key_env + "', '')\n"
        "\n"
        "system_prompt = \"\"\"You are an expert agent working in a restricted environment.\n"
        "Solve the task efficiently. Run all processes in the foreground without user input.\n"
        "IMPORTANT: Your working directory is `/tmp/workspace`. Use RELATIVE paths (e.g. `.`, `logs/`) for files. Never use absolute paths like `/root/...` unless explicitly told.\n"
        "Skills are located at: /tmp/workspace/skills/\n"
        "Provide a complete, functional solution.\"\"\"\n"
        "\n"
        "agent = NanoBotAgent(\n"
        "    model='" + config["model"] + "',\n"
        "    api_url='" + config["api_url"] + "',\n"
        "    api_key=api_key,\n"
        "    workspace=workspace,\n"
        "    timeout=1200,\n"
        "    system_prompt=system_prompt,\n"
        "    disable_safety_guard=True," + harness_kwargs_str + "\n"
        ")\n"
        "\n"
        "try:\n"
        "    start_time = time.time()\n"
        + exec_code_indented + "\n"
        "except Exception as e:\n"
        "    output = {\n"
        "        'status': 'error',\n"
        "        'content': '',\n"
        "        'transcript': [],\n"
        "        'usage': {},\n"
        "        'execution_time': 0,\n"
        "        'error': str(e),\n"
        "    }\n"
        "\n"
        "(workspace / 'agent_result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))\n"
        "print('DONE')\n"
    )
    return script


def _run_agent_in_container(container_name: str, exec_script: str, timeout_seconds: int) -> tuple[subprocess.CompletedProcess, float]:
    """Execute NanoBotAgent inside container, return (process_result, elapsed_time)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(exec_script)
        script_path = f.name
    try:
        subprocess.run(["docker", "cp", script_path, f"{container_name}:/tmp/exec_nanobot.py"], check=True)
    finally:
        Path(script_path).unlink(missing_ok=True)

    start_time = time.perf_counter()
    exec_proc = subprocess.run(
        ["docker", "exec", "-w", "/tmp/workspace", container_name, "python3", "/tmp/exec_nanobot.py"],
        capture_output=True, text=True, timeout=timeout_seconds + 60)
    elapsed = time.perf_counter() - start_time
    return exec_proc, elapsed


def _copy_results_from_container(container_name: str, workspace_path: str, task_output_dir: Path) -> Path:
    """Copy agent result from container to host. Returns result_file path."""
    result_file_host = task_output_dir / "agent_result.json"
    subprocess.run(["docker", "cp", f"{container_name}:/tmp/workspace/agent_result.json", str(result_file_host)],
                   capture_output=True)
    return result_file_host


# ============================================================================
# AgentBench Benchmark
# ============================================================================

class AgentBench(BaseBenchmark):
    DISPLAY_NAME = "AgentBench"
    TASK_COUNT = 40
    SCORE_RANGE = "0-100"

    def __init__(self, base_dir: Path = None, output_dir: Path = None, use_docker: bool = False):
        super().__init__(base_dir=base_dir, output_dir=output_dir)
        self._use_docker_default = use_docker

    def evaluate(
        self,
        model_key: str,
        config: dict,
        sample: int = 0,
        use_docker: bool = None,
        parallel: int = 1,
        openclawpro_dir: Path = None,
        use_judge: bool = True,
        **kwargs,
    ) -> dict:
        """Run AgentBench evaluation.

        Args:
            model_key: Model identifier
            config: Model config (model, api_url, api_key, provider)
            sample: Number of tasks to sample (0=all)
            use_docker: Run inside Docker container (default: False)
            parallel: Parallel task execution (Docker mode only)
            openclawpro_dir: OpenClawPro source for volume mount
            use_judge: Use LLM judge for L2/L3 scoring
        """
        if use_docker is None:
            use_docker = self._use_docker_default
        force = kwargs.pop("force", False)

        # Extract task_ids and harness_config from kwargs if present
        task_ids = kwargs.pop("task_ids", None)
        harness_config = kwargs.pop("harness_config", None)

        if use_docker:
            return self._evaluate_docker(
                model_key=model_key,
                config=config,
                sample=sample,
                parallel=parallel,
                openclawpro_dir=openclawpro_dir,
                force=force,
                use_judge=use_judge,
                task_ids=task_ids,
                harness_config=harness_config,
            )
        else:
            return self._evaluate_native(
                model_key=model_key,
                config=config,
                sample=sample,
                use_judge=use_judge,
                task_ids=task_ids,
            )

    def _evaluate_native(self, model_key: str, config: dict, sample: int = 0, use_judge: bool = True) -> dict:
        """Native mode: run nanobot CLI on host."""
        import yaml

        tasks_dir = self.base_dir / "benchmarks" / "agentbench-openclaw" / "tasks"
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        tasks = self._load_tasks(tasks_dir)
        if sample and sample < len(tasks):
            # Filter out tasks that already have cached results
            uncached_tasks = [t for t in tasks if not (self.results_dir / "agentbench" / model_key / t["task_id"] / "result.json").exists()]
            sample_from = uncached_tasks if uncached_tasks else tasks
            random.seed(42)
            tasks = random.sample(sample_from, min(sample, len(sample_from)))

        out_dir = self.results_dir / "agentbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []

        for task in tasks:
            tid = task["task_id"]
            result_file = out_dir / f"{tid}.json"
            if result_file.exists():
                try:
                    ex = json.loads(result_file.read_text())
                    if ex.get("status") == "success":
                        results.append(ex)
                        continue
                except Exception:
                    pass

            cfg = yaml.safe_load(Path(task["yaml_path"]).read_text())
            workspace = Path(tempfile.mkdtemp(prefix=f"agentbench_{tid}_"))
            try:
                # Prepare input files
                task_dir = Path(task["yaml_path"]).parent
                for inp in cfg.get("input_files", []):
                    fname = inp["name"] if isinstance(inp, dict) else inp
                    src = task_dir / fname
                    if src.exists():
                        dst = workspace / fname
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)

                config_path = self._write_config(model_key, config, workspace)
                user_msg = cfg.get("user_message", "")
                cmd = ["nanobot", "agent", "-c", str(config_path), "-w", str(workspace),
                       "-s", f"eval_{model_key}_{tid}", "-m", user_msg]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(workspace))

                # Simple L0 scoring for native mode
                expected = cfg.get("expected_outputs", [])
                if expected:
                    passed = sum(1 for e in expected if e.get("pattern") and (workspace / e["pattern"]).exists())
                    l0 = (passed / len(expected)) * 100
                else:
                    l0 = 0

                r = {
                    "task_id": tid,
                    "model_key": model_key,
                    "status": "success",
                    "scores": {
                        "l0_score": round(l0, 1),
                        "l1_score": 50,  # Neutral for native mode
                        "l2_score": 50,
                        "l3_score": 50,
                        "overall_score": round(l0 * 0.15 + 50 * 0.25 + 50 * 0.20 + 50 * 0.25, 1)
                    }
                }
            except Exception as e:
                r = {"task_id": tid, "model_key": model_key, "status": "error", "error": str(e)[:300], "scores": {}}

            result_file.write_text(json.dumps(r, indent=2, ensure_ascii=False))
            shutil.rmtree(workspace, ignore_errors=True)
            results.append(r)

        scores = [r["scores"]["overall_score"] for r in results if r.get("status") == "success" and r.get("scores")]
        avg = round(sum(scores) / len(scores), 1) if scores else 0
        return {"score": avg, "passed": len(scores), "total": len(tasks), "details": results}

    def _evaluate_docker(
        self,
        model_key: str,
        config: dict,
        sample: int = 0,
        parallel: int = 1,
        openclawpro_dir: Path = None,
        force: bool = False,
        use_judge: bool = True,
        task_ids: list = None,
        harness_config: dict = None,
    ) -> dict:
        """Docker mode: run NanoBotAgent inside Docker container with full 4-layer scoring."""
        import yaml

        if openclawpro_dir is None:
            openclawpro_dir = Path(os.getenv("OPENCLAWPRO_DIR",
                str(Path(__file__).parent.parent.parent / "OpenClawPro")))
        if not openclawpro_dir.exists():
            raise FileNotFoundError(f"OpenClawPro directory not found: {openclawpro_dir}")

        # Check if OpenClawPro is empty (submodule not initialized)
        if not any(openclawpro_dir.iterdir()):
            raise FileNotFoundError(
                f"OpenClawPro directory is empty. Please run:\n"
                f"  git submodule update --init --recursive\n"
                f"in the project root directory."
            )

        tasks_dir = self.base_dir / "benchmarks" / "agentbench-openclaw" / "tasks"
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        tasks = self._load_tasks(tasks_dir)

        # Filter by task_ids if specified
        if task_ids:
            tasks = [t for t in tasks if t["task_id"] in task_ids]
            if not tasks:
                return {"score": 0, "total": 0, "error": f"No tasks found matching task_ids: {task_ids}"}

        if sample and sample < len(tasks):
            # Filter out tasks that already have cached results
            uncached_tasks = [t for t in tasks if not (self.results_dir / "agentbench" / model_key / t["task_id"] / "result.json").exists()]
            sample_from = uncached_tasks if uncached_tasks else tasks
            random.seed(42)
            tasks = random.sample(sample_from, min(sample, len(sample_from)))

        out_dir = self.results_dir / "agentbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        judge_model_env = os.getenv("JUDGE_MODEL", "glm-4.7")

        # Resolve judge API config based on model name
        from ..config import get_judge_config
        judge_api_key, judge_base, judge_model = get_judge_config(judge_model_env)

        def run_single_task_docker(task: dict, model: str, force: bool = False) -> dict:
            """Execute a single task inside Docker container with full scoring."""
            tid = task["task_id"]
            yaml_path = task["yaml_path"]

            # Check cache
            task_output_dir = out_dir / tid
            task_output_dir.mkdir(parents=True, exist_ok=True)
            result_file = task_output_dir / "result.json"
            if not force and result_file.exists():
                try:
                    cached = json.loads(result_file.read_text())
                    if cached.get("status") == "success" and "scores" in cached:
                        log(f"[{tid}] Found cached result, skipping")
                        return {**cached, "_from_cache": True}
                except Exception:
                    pass

            # Generate container name
            timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
            short_model = re.sub(r"[^a-zA-Z0-9.\-_]", "_", model.rsplit("/", 1)[-1])
            container_name = f"agent_{tid}_{short_model}_{timestamp}"

            result = {
                "task_id": tid,
                "model_key": model_key,
                "status": "error",
                "scores": {},
                "error": None
            }

            try:
                # Prepare workspace on host
                workspace_path = tempfile.mkdtemp(prefix=f"agentbench_docker_{tid}_")
                # Use 'workspace' subdir which gets mounted to container
                host_workspace = Path(workspace_path) / "workspace"
                host_workspace.mkdir(parents=True, exist_ok=True)

                # Copy input files to workspace
                cfg = yaml.safe_load(Path(yaml_path).read_text())
                task_dir = Path(yaml_path).parent
                inputs_dir = task_dir / "inputs"
                for inp in cfg.get("input_files", []):
                    fname = inp["name"] if isinstance(inp, dict) else inp
                    # Try inputs/ subdirectory first, then task root
                    src = inputs_dir / fname if inputs_dir.exists() else task_dir / fname
                    if src.exists():
                        dst = host_workspace / fname
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)

                # Run setup.sh if exists (for tasks that need environment setup)
                setup_script = task_dir / "setup.sh"
                if setup_script.exists():
                    log(f"[{container_name}] Running setup.sh for task {tid}")
                    setup_proc = subprocess.run(
                        ["bash", str(setup_script), str(host_workspace)],
                        capture_output=True,
                        text=True,
                        timeout=120
                    )
                    if setup_proc.returncode != 0:
                        log(f"[{container_name}] setup.sh failed: {setup_proc.stderr[:500]}")
                    else:
                        log(f"[{container_name}] setup.sh completed successfully")

                # Build env args
                proxy_http = os.environ.get('HTTP_PROXY_INNER', '')
                proxy_https = os.environ.get('HTTPS_PROXY_INNER', '')
                env_args = [
                    "-e", f"http_proxy={proxy_http}",
                    "-e", f"https_proxy={proxy_https}",
                    "-e", f"HTTPS_PROXY={proxy_https}",
                ]

                # Pass correct API key based on provider
                provider = config.get("provider", "openrouter")
                if provider == "minimax":
                    minimax_api_key = os.getenv("MINIMAX_API_KEY", "")
                    env_args.extend(["-e", f"MINIMAX_API_KEY={minimax_api_key}"])
                elif provider == "glm":
                    glm_api_key = os.getenv("GLM_API_KEY", "")
                    env_args.extend(["-e", f"GLM_API_KEY={glm_api_key}"])
                else:
                    env_args.extend(["-e", f"OPENROUTER_API_KEY={openrouter_api_key}"])

                # Start container (OpenClawPro readonly, exec/tmp mounted)
                _start_container(container_name, workspace_path, openclawpro_dir, DOCKER_IMAGE, env_args)
                log(f"[{container_name}] Container started")

                # Copy workspace to container (instead of volume mount)
                host_workspace = Path(workspace_path) / "workspace"
                subprocess.run(
                    ["docker", "cp", f"{host_workspace}/.", f"{container_name}:/tmp/workspace/"],
                    check=True
                )
                # Verify workspace was copied (not empty)
                check_result = subprocess.run(
                    ["docker", "exec", container_name, "ls", "-la", "/tmp/workspace/"],
                    capture_output=True, text=True
                )
                if not check_result.stdout.strip() or "total 0" in check_result.stdout:
                    log(f"[{container_name}] WARNING: /tmp/workspace appears empty! Files: {check_result.stdout}")
                else:
                    log(f"[{container_name}] Workspace copied to /tmp/workspace/:\n{check_result.stdout[:500]}")

                # Build and run agent
                user_msg = cfg.get("user_message", "")
                turns = cfg.get("turns", None)
                exec_script = _build_exec_script(model_key, tid, user_msg, config, harness_config=harness_config, turns=turns)
                exec_proc, elapsed_time = _run_agent_in_container(container_name, exec_script, 1200)
                log(f"[{container_name}] Agent finished in {elapsed_time:.2f}s, returncode={exec_proc.returncode}")

                # Log stdout/stderr for debugging
                if exec_proc.stdout:
                    log(f"[{container_name}] Agent stdout: {exec_proc.stdout[:500]}")
                if exec_proc.stderr:
                    log(f"[{container_name}] Agent stderr: {exec_proc.stderr[:500]}")

                # Copy results back
                result_file_host = _copy_results_from_container(container_name, workspace_path, task_output_dir)

                # Load agent result
                transcript = []
                model_output = ""
                if result_file_host.exists():
                    try:
                        agent_result = json.loads(result_file_host.read_text())
                        result["status"] = agent_result.get("status", "error")
                        result["error"] = agent_result.get("error", "")
                        result["usage"] = {**agent_result.get("usage", {}), "elapsed_time": round(elapsed_time, 2)}
                        transcript = agent_result.get("transcript", [])
                        model_output = agent_result.get("content", "")
                        log(f"[{container_name}] Agent result loaded: status={result['status']}, transcript_len={len(transcript)}")
                    except Exception as e:
                        log(f"[{container_name}] Failed to load agent result: {e}")
                        result["error"] = f"Failed to load agent result: {e}"
                else:
                    log(f"[{container_name}] agent_result.json not found at {result_file_host}")
                    result["error"] = "agent_result.json not found"

                # ==================== 4-Layer Scoring ====================

                # L0: Automated Structural Checks
                expected_outputs = cfg.get("expected_outputs", [])
                expected_behavior = cfg.get("expected_behavior", [])
                # Fallback: extract validators from turns if top-level keys are absent
                if not expected_outputs and not expected_behavior:
                    turns = cfg.get("turns", [])
                    for turn in turns:
                        validators = turn.get("validators", [])
                        if not validators:
                            continue
                        if turn.get("expect") == "file-output":
                            expected_outputs.append({
                                "pattern": validators[0].get("pattern", "*.md"),
                                "validators": validators,
                            })
                        elif turn.get("expect") == "response":
                            expected_behavior.append({"validators": validators})
                l0_score = _compute_layer0_score(container_name, expected_outputs, expected_behavior, model_output)

                # L1: Metrics Analysis
                expected_metrics = cfg.get("expected_metrics", {})
                l1_score = _compute_layer1_score(expected_metrics, transcript, elapsed_time)

                # L2 & L3: LLM Judge Evaluation (reuse grading.run_judge_eval)
                l2_score = 50  # Default neutral
                l3_score = 50

                if use_judge and transcript:
                    from ..grading import run_judge_eval as _run_judge
                    judge_score_obj = _run_judge(
                        trajectory=transcript,
                        task_id=tid,
                        category=task.get("category", ""),
                        task_prompt=user_msg,
                        judge_model=judge_model,
                        api_key=judge_api_key,
                        base_url=judge_base,
                        model_name=config.get("model", model_key),
                    )
                    if judge_score_obj and judge_score_obj.overall_score > 0:
                        # Map JudgeScore to L2/L3: task_completion+tool_usage → L2, reasoning+answer_quality → L3
                        l2_score = (judge_score_obj.task_completion + judge_score_obj.tool_usage) / 2 * 100
                        l3_score = (judge_score_obj.reasoning + judge_score_obj.answer_quality) / 2 * 100
                        result["judge_breakdown"] = {
                            "l2": {"task_completion": judge_score_obj.task_completion, "tool_usage": judge_score_obj.tool_usage},
                            "l3": {"reasoning": judge_score_obj.reasoning, "answer_quality": judge_score_obj.answer_quality},
                            "overall": judge_score_obj.overall_score,
                            "reasoning": judge_score_obj.justification,
                        }

                # Get scoring weights from task config
                scoring = cfg.get("scoring", {})
                l0_weight = scoring.get("layer0_weight", 0.15)
                l1_weight = scoring.get("layer1_weight", 0.25)
                l2_weight = scoring.get("layer2_weight", 0.20)
                l3_weight = scoring.get("layer3_weight", 0.35)

                # Compute composite score
                composite = (l0_score * l0_weight +
                           l1_score * l1_weight +
                           l2_score * l2_weight +
                           l3_score * l3_weight)

                result["scores"] = {
                    "l0_score": round(l0_score, 1),
                    "l1_score": round(l1_score, 1),
                    "l2_score": round(l2_score, 1),
                    "l3_score": round(l3_score, 1),
                    "overall_score": round(composite, 1)
                }

                log(f"[{container_name}] Scores: L0={l0_score:.1f} L1={l1_score:.1f} L2={l2_score:.1f} L3={l3_score:.1f} | Overall={composite:.1f}")

            except subprocess.TimeoutExpired:
                result["error"] = "Timeout after 300 seconds"
            except Exception as exc:
                log(f"[{container_name}] Execution error: {exc}")
                result["error"] = str(exc)
            finally:
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
                shutil.rmtree(workspace_path, ignore_errors=True)

            # Save cache (always save, not just on success)
            try:
                result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
                log(f"[{container_name}] Result saved to {result_file}")
            except Exception as e:
                log(f"[{container_name}] Failed to save result: {e}")

            return result

        # Execute tasks
        results = []
        if parallel <= 1:
            for task in tasks:
                results.append(run_single_task_docker(task, config["model"], force=force))
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {
                    pool.submit(run_single_task_docker, task, config["model"], force): task["task_id"]
                    for task in tasks
                }
                for future in as_completed(futures):
                    tid = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        log(f"[{tid}] Thread exception: {exc}")
                        results.append({"task_id": tid, "scores": {}, "error": str(exc)})

        # Compute average
        scores = [r["scores"]["overall_score"] for r in results
                  if r.get("status") == "success" and r.get("scores")]
        avg = round(sum(scores) / len(scores), 1) if scores else 0

        # Domain breakdown
        domain_scores = {}
        for r in results:
            if r.get("status") == "success" and r.get("scores"):
                cat = next((t["category"] for t in tasks if t["task_id"] == r["task_id"]), "unknown")
                if cat not in domain_scores:
                    domain_scores[cat] = []
                domain_scores[cat].append(r["scores"]["overall_score"])

        domain_avgs = {cat: round(sum(scores)/len(scores), 1) for cat, scores in domain_scores.items() if scores}

        return {
            "score": avg,
            "passed": len(scores),
            "total": len(tasks),
            "domain_scores": domain_avgs,
            "details": results
        }


    def _compute_summary(self, model_key: str, all_task_ids: list, results: list) -> dict:
        """Compute summary for agentbench."""
        # AgentBench has composite scoring (L0-L3)
        l0_pass = sum(1 for r in results if r.get("scores", {}).get("L0") == 1)
        l1_pass = sum(1 for r in results if r.get("scores", {}).get("L1") == 1)
        l2_pass = sum(1 for r in results if r.get("scores", {}).get("L2") == 1)
        l3_pass = sum(1 for r in results if r.get("scores", {}).get("L3") == 1)
        passed = l0_pass
        score = round((l0_pass * 0.25 + l1_pass * 0.25 + l2_pass * 0.25 + l3_pass * 0.25) / len(all_task_ids) * 100, 1) if all_task_ids else 0
        total = len(all_task_ids)
        scored = len(results)
        return {
            "model": model_key,
            "score": score,
            "passed": passed,
            "failed": scored - passed,
            "pending": total - scored,
            "total": total,
            "details": results
        }

    def _load_summary(self, bench_key: str, model_key: str) -> dict:
        """Load saved summary file."""
        result_f = self.results_dir / bench_key / f"{model_key}.json"
        if result_f.exists():
            try:
                data = json.loads(result_f.read_text())
                return {"score": data["score"], "passed": data.get("passed", 0), "total": data["total"]}
            except Exception:
                pass
        return {"score": 0, "passed": 0, "total": 0}

    def collect(self, model_key: str) -> dict | None:
        """Collect results for a model."""
        result_dir = self._find_result_dir("agentbench")
        if not result_dir:
            return None

        for key_variant in [model_key, self._legacy_key(model_key)]:
            d = result_dir / key_variant
            if not d.exists():
                continue

            # Check for results.json first
            full = d / "results.json"
            if full.exists():
                try:
                    data = json.loads(full.read_text())
                    if "overall_score" in data:
                        return {"score": round(float(data["overall_score"]), 1), "total": 40}
                except Exception:
                    pass

            # Collect per-task scores
            scores = []
            for f in d.glob("*.json"):
                if f.name == "results.json":
                    continue
                try:
                    r = json.loads(f.read_text())
                    if r.get("status") == "success" and r.get("scores", {}).get("overall_score") is not None:
                        scores.append(float(r["scores"]["overall_score"]))
                except Exception:
                    pass

            # Also check subdirectories for new format
            for subdir in d.iterdir():
                if subdir.is_dir():
                    result_file = subdir / "result.json"
                    if result_file.exists():
                        try:
                            r = json.loads(result_file.read_text())
                            if r.get("status") == "success" and r.get("scores", {}).get("overall_score") is not None:
                                scores.append(float(r["scores"]["overall_score"]))
                        except Exception:
                            pass

            if scores and len(scores) == self.TASK_COUNT:
                return {"score": round(sum(scores) / len(scores), 1), "total": len(scores)}

        return None

    def _legacy_key(self, key):
        m = {"claude-sonnet": "claude-sonnet-4.6",
             "claude-opus": "claude-opus-4.6", "gemini-3.1-pro": "gemini-3-pro-preview-new"}
        return m.get(key, key)

    def _load_tasks(self, tasks_dir):
        import yaml
        tasks = []
        for cat_dir in sorted(tasks_dir.iterdir()):
            if not cat_dir.is_dir():
                continue
            for task_dir in sorted(cat_dir.iterdir()):
                yaml_f = task_dir / "task.yaml"
                if yaml_f.exists():
                    tasks.append({"task_id": task_dir.name, "category": cat_dir.name, "yaml_path": str(yaml_f)})
        return tasks

    def _write_config(self, model_key, config, workspace):
        ark_key = os.getenv("OPENROUTER_API_KEY", "")
        or_key = os.getenv("OPENROUTER_API_KEY", "")
        if config["provider"] == "openrouter":
            cfg = {"providers": {"openrouter": {"apiKey": or_key}},
                   "agents": {"defaults": {"model": config["model"], "workspace": str(workspace), "maxToolIterations": 25}}}
        elif config["provider"] == "ark":
            cfg = {"providers": {"custom": {"apiKey": ark_key, "apiBase": config["api_url"]}},
                   "agents": {"defaults": {"model": config["model"], "workspace": str(workspace), "maxToolIterations": 25}}}
        else:
            cfg = {"providers": {"custom": {"apiKey": config["api_key"], "apiBase": config["api_url"]}},
                   "agents": {"defaults": {"model": config["model"], "workspace": str(workspace), "maxToolIterations": 25}}}
        p = workspace / ".nanobot_config.json"
        p.write_text(json.dumps(cfg, indent=2))
        return p
