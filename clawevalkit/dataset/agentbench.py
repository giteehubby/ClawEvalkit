"""AgentBench-OpenClaw — 40 tasks, L0-L3 scoring (0-100).

Scoring: NanoBotAgent execution in Docker → 4-layer scoring → composite score.

Supports two execution modes:
  - use_docker=True:  Run NanoBotAgent inside Docker container
  - use_docker=False: Run nanobot CLI on host directly
"""
from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)

DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE_NANOBOT", "wildclawbench-nanobot:v3")
TMP_WORKSPACE = "/tmp/agentbench_workspace"


# ============================================================================
# Layer 0: Automated Structural Checks
# ============================================================================

def _check_file_exists(container_name: str, pattern: str) -> bool:
    """Check if file exists in container workspace."""
    check_proc = subprocess.run(
        ["docker", "exec", container_name, "test", "-f", f"/tmp/agentbench_workspace/{pattern}"],
        capture_output=True)
    return check_proc.returncode == 0


def _check_directory_structure(container_name: str, expected: list[str]) -> tuple[int, int]:
    """Check if all expected paths exist. Returns (passed, total)."""
    passed = 0
    for path in expected:
        check_proc = subprocess.run(
            ["docker", "exec", container_name, "test", "-e", f"/tmp/agentbench_workspace/{path}"],
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
            ["docker", "cp", f"{container_name}:/tmp/agentbench_workspace/{pattern}", temp_path],
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
            ["docker", "cp", f"{container_name}:/tmp/agentbench_workspace/{pattern}", temp_path],
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
        ["docker", "exec", container_name, "git", "-C", "/tmp/agentbench_workspace", "log", "--oneline"],
        capture_output=True, text=True)

    if result.returncode != 0:
        return 0, len(expected)

    log_content = result.stdout.lower()
    passed = sum(1 for exp in expected if exp.lower() in log_content)
    return passed, len(expected)


def _check_command_output_contains(container_name: str, command: str, expected: list[str]) -> tuple[int, int]:
    """Run command and check output contains all expected strings."""
    result = subprocess.run(
        ["docker", "exec", container_name, "/bin/bash", "-c", f"cd /tmp/agentbench_workspace && {command}"],
        capture_output=True, text=True)

    output = result.stdout + result.stderr
    passed = sum(1 for exp in expected if exp in output)
    return passed, len(expected)


def _check_link_consistency(container_name: str, files_pattern: str) -> float:
    """Check link syntax consistency in files."""
    # Get list of files
    result = subprocess.run(
        ["docker", "exec", container_name, "/bin/bash", "-c",
         f"cd /tmp/agentbench_workspace && find . -path './{files_pattern}' -type f 2>/dev/null"],
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
                ["docker", "cp", f"{container_name}:/tmp/agentbench_workspace/{f}", tmp_path],
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


def _compute_layer0_score(container_name: str, expected_outputs: list[dict]) -> float:
    """Compute Layer 0 score (0-100) based on automated structural checks."""
    if not expected_outputs:
        return 50  # No expected outputs, neutral score

    total_points = 0
    max_points = 0

    for output in expected_outputs:
        pattern = output.get("pattern", "")
        validators = output.get("validators", [])
        required = output.get("required", False)

        # Base points for this output
        output_max = 30 if required else 20
        output_points = 0

        for validator in validators:
            vtype = validator.get("type", "")

            if vtype == "file-exists":
                max_points += 30
                if _check_file_exists(container_name, pattern):
                    total_points += 30
                    output_points += 30

            elif vtype == "content-contains":
                sections = validator.get("sections", [])
                max_points += 40
                if sections and _check_file_exists(container_name, pattern):
                    passed, total = _check_content_contains(container_name, pattern, sections)
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
                expected = validator.get("expected", [])
                max_points += 30
                if expected:
                    passed, total = _check_git_log_contains(container_name, expected)
                    points = (passed / total) * 30 if total > 0 else 0
                    total_points += points
                    output_points += points

        # If required output has no points, apply penalty
        if required and output_points == 0:
            total_points -= 10

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

    # Count tool calls from transcript
    tool_calls = sum(1 for entry in transcript if isinstance(entry, dict) and entry.get("role") == "assistant" and entry.get("tool_calls"))

    # Estimate planning ratio (simplified: based on first tool call timing)
    planning_ratio = 0.25  # Default estimate

    # Count errors from transcript
    errors = sum(1 for entry in transcript if isinstance(entry, dict) and "error" in str(entry.get("content", "")).lower())

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
# Layer 2 & 3: Behavioral Analysis & Output Quality (LLM-based)
# ============================================================================

def _run_llm_judge_eval(task_prompt: str, transcript: list, model_output: str,
                        judge_model: str, api_key: str, base_url: str) -> dict:
    """Run LLM judge evaluation for L2 and L3 scores."""
    try:
        import openai

        client = openai.OpenAI(api_key=api_key, base_url=base_url)

        # Build evaluation prompt
        eval_prompt = f"""You are an expert evaluator assessing an AI agent's performance on a task.

Task Description:
{task_prompt}

Agent's Execution Transcript:
{json.dumps(transcript, indent=2)[:3000]}

Agent's Final Output:
{model_output[:2000]}

Please evaluate the agent on two dimensions (0-100 each):

L2 - Behavioral Analysis:
- Instruction Adherence (30%): Did it follow all instructions precisely?
- Tool Appropriateness (25%): Did it use the right tools for the job?
- Approach Quality (25%): Did it read inputs before producing output?
- Error Recovery (20%): How well did it handle errors?

L3 - Output Quality:
- Completeness (25%): Were all requirements met?
- Accuracy (25%): Was the content correct?
- Formatting (25%): Was it well-structured?
- Polish (25%): Would a user be satisfied?

Respond in JSON format:
{{
  "l2_score": <0-100>,
  "l3_score": <0-100>,
  "l2_breakdown": {{"instruction_adherence": <0-30>, "tool_appropriateness": <0-25>, "approach_quality": <0-25>, "error_recovery": <0-20>}},
  "l3_breakdown": {{"completeness": <0-25>, "accuracy": <0-25>, "formatting": <0-25>, "polish": <0-25>}},
  "reasoning": "brief explanation"
}}"""

        response = client.chat.completions.create(
            model=judge_model,
            messages=[{"role": "user", "content": eval_prompt}],
            temperature=0.2,
            max_tokens=1000
        )

        content = response.choices[0].message.content
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return {
                "l2_score": result.get("l2_score", 50),
                "l3_score": result.get("l3_score", 50),
                "l2_breakdown": result.get("l2_breakdown", {}),
                "l3_breakdown": result.get("l3_breakdown", {}),
                "reasoning": result.get("reasoning", "")
            }
    except Exception as e:
        logger.warning(f"LLM judge evaluation failed: {e}")

    # Fallback to neutral scores
    return {"l2_score": 50, "l3_score": 50, "error": "judge_failed"}


# ============================================================================
# Docker Execution Helpers
# ============================================================================

def _start_container(container_name: str, workspace_path: str, openclawpro_dir: Path,
                     docker_image: str, env_args: list) -> None:
    """Start Docker container with selective volume mounts."""
    exec_path = os.path.join(workspace_path, "exec")
    tmp_path = os.path.join(workspace_path, "tmp")
    workspace_inner = os.path.join(workspace_path, "workspace")

    os.makedirs(exec_path, exist_ok=True)
    os.makedirs(tmp_path, exist_ok=True)

    volume_mounts = [
        "-v", f"{exec_path}:/tmp/agentbench_workspace/exec:rw",
        "-v", f"{tmp_path}:/tmp/agentbench_workspace/tmp:rw",
        "-v", f"{openclawpro_dir}:/root/OpenClawPro:rw",
    ]
    if os.path.exists(workspace_inner):
        volume_mounts.extend(["-v", f"{workspace_inner}:/tmp/agentbench_workspace/workspace:rw"])

    docker_run_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        *volume_mounts,
        *env_args,
        docker_image,
        "/bin/bash", "-c", "tail -f /dev/null",
    ]
    r = subprocess.run(docker_run_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Container startup failed:\n{r.stderr}")


def _build_exec_script(model_key: str, task_id: str, user_message: str, config: dict) -> str:
    """Build NanoBotAgent execution script for running inside Docker container."""
    return f"""
import sys
import json
import time
import os
from pathlib import Path

sys.path.insert(0, '/root/OpenClawPro')
from harness.agent.nanobot import NanoBotAgent

workspace = Path('/tmp/agentbench_workspace')
session_id = 'eval_{model_key}_{task_id}'

# Get API key from environment variable
api_key = os.environ.get('OPENROUTER_API_KEY', '')

agent = NanoBotAgent(
    model='{config["model"]}',
    api_url='{config["api_url"]}',
    api_key=api_key,
    workspace=workspace,
    timeout=300,
    disable_safety_guard=True,
)

system_prompt = \"\"\"You are an expert agent working in a restricted environment.
Solve the task efficiently. Run all processes in the foreground without user input.
Provide a complete, functional solution.\"\"\"

try:
    start_time = time.time()
    result = agent.execute(
        '''{user_message.replace("'", "\\'")}''',
        session_id=session_id,
        workspace=workspace,
        system_prompt=system_prompt,
        max_iterations=100,
        max_output_tokens=8192,
    )
    elapsed = time.time() - start_time

    transcript_file = workspace / '.sessions' / f'{{session_id}}.json'
    transcript_data = json.loads(transcript_file.read_text()) if transcript_file.exists() else (result.transcript or [])

    output = {{
        'status': result.status,
        'content': result.content,
        'transcript': transcript_data,
        'usage': result.usage or {{}},
        'execution_time': elapsed,
        'error': result.error,
    }}
except Exception as e:
    output = {{
        'status': 'error',
        'content': '',
        'transcript': [],
        'usage': {{}},
        'execution_time': 0,
        'error': str(e),
    }}

(workspace / 'agent_result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
print('DONE')
"""


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
        ["docker", "exec", container_name, "python3", "/tmp/exec_nanobot.py"],
        capture_output=True, text=True, timeout=timeout_seconds + 60)
    elapsed = time.perf_counter() - start_time
    return exec_proc, elapsed


def _copy_results_from_container(container_name: str, workspace_path: str, task_output_dir: Path) -> Path:
    """Copy agent result from container to host. Returns result_file path."""
    result_file_host = task_output_dir / "agent_result.json"
    subprocess.run(["docker", "cp", f"{container_name}:/tmp/agentbench_workspace/agent_result.json", str(result_file_host)],
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

        if use_docker:
            return self._evaluate_docker(
                model_key=model_key,
                config=config,
                sample=sample,
                parallel=parallel,
                openclawpro_dir=openclawpro_dir,
                force=force,
                use_judge=use_judge,
            )
        else:
            return self._evaluate_native(
                model_key=model_key,
                config=config,
                sample=sample,
                use_judge=use_judge,
            )

    def _evaluate_native(self, model_key: str, config: dict, sample: int = 0, use_judge: bool = True) -> dict:
        """Native mode: run nanobot CLI on host."""
        import yaml

        tasks_dir = self.base_dir / "benchmarks" / "agentbench-openclaw" / "tasks"
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        tasks = self._load_tasks(tasks_dir)
        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

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
    ) -> dict:
        """Docker mode: run NanoBotAgent inside Docker container with full 4-layer scoring."""
        import yaml

        if openclawpro_dir is None:
            openclawpro_dir = Path(os.getenv("OPENCLAWPRO_DIR",
                str(Path(__file__).parent.parent.parent / "OpenClawPro")))
        if not openclawpro_dir.exists():
            raise FileNotFoundError(f"OpenClawPro directory not found: {openclawpro_dir}")

        tasks_dir = self.base_dir / "benchmarks" / "agentbench-openclaw" / "tasks"
        if not tasks_dir.exists():
            return {"score": 0, "total": 0, "error": f"tasks dir not found: {tasks_dir}"}

        tasks = self._load_tasks(tasks_dir)
        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

        out_dir = self.results_dir / "agentbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        judge_model = os.getenv("JUDGE_MODEL", "anthropic/claude-sonnet-4.6")
        judge_base = os.getenv("JUDGE_BASE_URL", "https://openrouter.ai/api/v1")

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
                        logger.info("[%s] Found cached result, skipping", tid)
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
                tmp_workspace = Path(workspace_path) / "tmp_workspace"
                tmp_workspace.mkdir(parents=True, exist_ok=True)

                # Copy input files to workspace
                cfg = yaml.safe_load(Path(yaml_path).read_text())
                task_dir = Path(yaml_path).parent
                for inp in cfg.get("input_files", []):
                    fname = inp["name"] if isinstance(inp, dict) else inp
                    src = task_dir / fname
                    if src.exists():
                        dst = tmp_workspace / fname
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)

                # Build env args
                proxy_http = os.environ.get('HTTP_PROXY_INNER', '')
                proxy_https = os.environ.get('HTTPS_PROXY_INNER', '')
                env_args = [
                    "-e", f"http_proxy={proxy_http}",
                    "-e", f"https_proxy={proxy_https}",
                    "-e", f"HTTPS_PROXY={proxy_https}",
                    "-e", f"OPENROUTER_API_KEY={openrouter_api_key}",
                ]

                # Start container
                _start_container(container_name, workspace_path, openclawpro_dir, DOCKER_IMAGE, env_args)
                logger.info("[%s] Container started", container_name)

                # Copy workspace to container
                subprocess.run(["docker", "exec", container_name, "mkdir", "-p", "/tmp/agentbench_workspace"],
                             capture_output=True)
                subprocess.run(["docker", "cp", f"{tmp_workspace}/.", f"{container_name}:/tmp/agentbench_workspace/"],
                             capture_output=True)

                # Build and run agent
                user_msg = cfg.get("user_message", "")
                exec_script = _build_exec_script(model_key, tid, user_msg, config)
                exec_proc, elapsed_time = _run_agent_in_container(container_name, exec_script, 300)
                logger.info("[%s] Agent finished in %.2fs, returncode=%d", container_name, elapsed_time, exec_proc.returncode)

                # Log stdout/stderr for debugging
                if exec_proc.stdout:
                    logger.debug("[%s] Agent stdout: %s", container_name, exec_proc.stdout[:500])
                if exec_proc.stderr:
                    logger.debug("[%s] Agent stderr: %s", container_name, exec_proc.stderr[:500])

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
                        logger.info("[%s] Agent result loaded: status=%s, transcript_len=%d",
                                   container_name, result["status"], len(transcript))
                    except Exception as e:
                        logger.error("[%s] Failed to load agent result: %s", container_name, e)
                        result["error"] = f"Failed to load agent result: {e}"
                else:
                    logger.warning("[%s] agent_result.json not found at %s", container_name, result_file_host)
                    result["error"] = "agent_result.json not found"

                # ==================== 4-Layer Scoring ====================

                # L0: Automated Structural Checks
                expected_outputs = cfg.get("expected_outputs", [])
                l0_score = _compute_layer0_score(container_name, expected_outputs)

                # L1: Metrics Analysis
                expected_metrics = cfg.get("expected_metrics", {})
                l1_score = _compute_layer1_score(expected_metrics, transcript, elapsed_time)

                # L2 & L3: LLM Judge Evaluation
                l2_score = 50  # Default neutral
                l3_score = 50

                if use_judge and transcript:
                    judge_result = _run_llm_judge_eval(
                        task_prompt=user_msg,
                        transcript=transcript,
                        model_output=model_output,
                        judge_model=judge_model,
                        api_key=openrouter_api_key,
                        base_url=judge_base
                    )
                    l2_score = judge_result.get("l2_score", 50)
                    l3_score = judge_result.get("l3_score", 50)
                    result["judge_breakdown"] = {
                        "l2": judge_result.get("l2_breakdown", {}),
                        "l3": judge_result.get("l3_breakdown", {}),
                        "reasoning": judge_result.get("reasoning", "")
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

                logger.info("[%s] Scores: L0=%.1f L1=%.1f L2=%.1f L3=%.1f | Overall=%.1f",
                           container_name, l0_score, l1_score, l2_score, l3_score, composite)

            except subprocess.TimeoutExpired:
                result["error"] = "Timeout after 300 seconds"
            except Exception as exc:
                logger.error("[%s] Execution error: %s", container_name, exc)
                result["error"] = str(exc)
            finally:
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
                shutil.rmtree(workspace_path, ignore_errors=True)

            # Save cache (always save, not just on success)
            try:
                result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
                logger.info("[%s] Result saved to %s", container_name, result_file)
            except Exception as e:
                logger.error("[%s] Failed to save result: %s", container_name, e)

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
                        logger.error("[%s] Thread exception: %s", tid, exc)
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

            if scores:
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
