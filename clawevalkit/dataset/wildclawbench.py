"""WildClawBench — 60 tasks across 6 categories.

评分方式: NanoBotAgent 执行 + LLM Judge 评分 (0~1)。
数据来源: 本地 benchmarks/wildclawbench/tasks/。

支持两种执行模式:
  - use_docker=True:  使用 Docker 容器运行 OpenClaw (依赖 wildclawbench-ubuntu:v0.4 镜像)
  - use_docker=False: 使用 NanoBotAgent 在宿主机直接运行 (默认, 无需 Docker)

依赖:
  - 推理框架: OpenClawPro (提供 NanoBotAgent) 或 Docker
  - 评分逻辑: clawevalkit.grading (提供 run_judge_eval, run_automated_checks)
  - 可选: agent-browser CLI (用于浏览器自动化任务, 仅 native 模式)
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
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from ..utils.nanobot import import_nanobot_agent
from .base import BaseBenchmark

logger = logging.getLogger(__name__)

# All 6 task categories in WildClawBench
TASK_CATEGORIES = [
    "01_Productivity_Flow",
    "02_Code_Intelligence",
    "03_Social_Interaction",
    "04_Search_Retrieval",
    "05_Creative_Synthesis",
    "06_Safety_Alignment",
]

# Tasks that require agent-browser CLI (native mode only)
BROWSER_TASKS = {
    "01_Productivity_Flow_task_8_real_image_category",
    "04_Search_Retrieval_task_1_google_scholar_search",
    "04_Search_Retrieval_task_6_excel_with_search",
}

# Docker config
DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE", "wildclawbench-ubuntu:v0.4")
TMP_WORKSPACE = "/tmp_workspace"


def ensure_agent_browser():
    """Check and install agent-browser if not available (native mode only)."""
    result = subprocess.run(["which", "agent-browser"], capture_output=True)
    if result.returncode == 0:
        return True

    logger.info("agent-browser not found, installing...")
    try:
        subprocess.run(["npm", "install", "-g", "agent-browser"], check=True, capture_output=True)
        subprocess.run(["agent-browser", "install"], check=True, capture_output=True)
        logger.info("agent-browser installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to install agent-browser: {e}")
        return False


def parse_task_md_native(task_file: Path) -> dict:
    """Extract task metadata, prompt, workspace path, and automated checks from task.md (native mode)."""
    import yaml

    content = task_file.read_text(encoding="utf-8")

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not fm_match:
        raise ValueError(f"YAML frontmatter not found: {task_file}")

    metadata = yaml.safe_load(fm_match.group(1))
    body = fm_match.group(2)

    sections: dict[str, str] = {}
    current_section = None
    lines = []
    for line in body.split("\n"):
        header = re.match(r"^##\s+(.+)$", line)
        if header:
            if current_section is not None:
                sections[current_section] = "\n".join(lines).strip()
            current_section = header.group(1)
            lines = []
        else:
            lines.append(line)
    if current_section is not None:
        sections[current_section] = "\n".join(lines).strip()

    def strip_codeblock(raw: str) -> str:
        s = re.sub(r"^```[^\n]*\n?", "", raw.strip())
        s = re.sub(r"\n?```$", "", s).strip()
        return s

    prompt = sections.get("Prompt", "").strip()

    raw_workspace = sections.get("Workspace Path", "").strip()
    workspace_path = strip_codeblock(raw_workspace)

    skills_raw = sections.get("Skills", "").strip()
    skills = [s.strip() for s in strip_codeblock(skills_raw).split("\n") if s.strip()]

    automated_checks = strip_codeblock(sections.get("Automated Checks", ""))

    task_id = metadata.get("id", task_file.stem)
    timeout_seconds = int(metadata.get("timeout_seconds", 300))

    return {
        "task_id": task_id,
        "prompt": prompt,
        "workspace_path": workspace_path,
        "skills": skills,
        "automated_checks": automated_checks,
        "timeout_seconds": timeout_seconds,
        "file_path": str(task_file.resolve()),
        "category": task_file.parent.name,
    }


def parse_task_md_docker(task_file: Path) -> dict:
    """Extract task metadata for Docker mode (includes env, skills, warmup)."""
    import yaml

    content = task_file.read_text(encoding="utf-8")

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not fm_match:
        raise ValueError(f"YAML frontmatter not found: {task_file}")

    metadata = yaml.safe_load(fm_match.group(1))
    body = fm_match.group(2)

    sections: dict[str, str] = {}
    current_section = None
    lines = []
    for line in body.split("\n"):
        header = re.match(r"^##\s+(.+)$", line)
        if header:
            if current_section is not None:
                sections[current_section] = "\n".join(lines).strip()
            current_section = header.group(1)
            lines = []
        else:
            lines.append(line)
    if current_section is not None:
        sections[current_section] = "\n".join(lines).strip()

    def strip_codeblock(raw: str) -> str:
        s = re.sub(r"^```[^\n]*\n?", "", raw.strip())
        s = re.sub(r"\n?```$", "", s).strip()
        return s

    prompt = sections.get("Prompt", "").strip()
    raw_workspace = sections.get("Workspace Path", "").strip()
    workspace_path = strip_codeblock(raw_workspace)

    skills_path = "skills"

    automated_checks = strip_codeblock(sections.get("Automated Checks", ""))
    env = strip_codeblock(sections.get("Env", ""))
    skills = strip_codeblock(sections.get("Skills", ""))
    warmup = strip_codeblock(sections.get("Warmup", ""))

    task_id = metadata.get("id", task_file.stem)
    timeout_seconds = int(metadata.get("timeout_seconds", 120))

    # Resolve relative paths relative to benchmarks/wildclawbench
    benchmarks_dir = Path(__file__).parent.parent.parent / "benchmarks" / "wildclawbench"
    wp = Path(workspace_path)
    if not wp.is_absolute():
        wp = (benchmarks_dir / wp).resolve()
    workspace_path = str(wp)

    sp = Path(skills_path)
    if not sp.is_absolute():
        sp = (benchmarks_dir / sp).resolve()
    skills_path = str(sp)

    return {
        "task_id": task_id,
        "prompt": prompt,
        "workspace_path": workspace_path,
        "skills_path": skills_path,
        "automated_checks": automated_checks,
        "env": env,
        "skills": skills,
        "warmup": warmup,
        "timeout_seconds": timeout_seconds,
        "file_path": str(task_file.resolve()),
        "category": task_file.parent.name,
    }


def parse_task_md(task_file: Path, use_docker: bool = False) -> dict:
    """Parse task.md with mode-appropriate parser."""
    return parse_task_md_docker(task_file) if use_docker else parse_task_md_native(task_file)


class WildClawBench(BaseBenchmark):
    DISPLAY_NAME = "WildClawBench"
    TASK_COUNT = 60
    SCORE_RANGE = "0-1"

    def __init__(self, base_dir: Path = None, output_dir: Path = None, use_docker: bool = False):
        super().__init__(base_dir=base_dir, output_dir=output_dir)
        self._use_docker_default = use_docker

    def evaluate(
        self,
        model_key: str,
        config: dict,
        sample: int = 0,
        transcripts_dir: Path = None,
        category: str = None,
        use_automated_checks: bool = True,
        use_docker: bool = None,
        parallel: int = 1,
        openclawpro_dir: Path = None,
        **kwargs,
    ) -> dict:
        """运行 WildClawBench 评测。

        Args:
            model_key: 模型标识符
            config: 模型配置 (model, api_url, api_key, name)
            sample: 采样任务数 (0=全部)
            transcripts_dir: 保存 transcript 的目录
            category: 指定类别 (None=全部)
            use_automated_checks: 是否使用自动化 checks
            use_docker: 是否使用 Docker 容器运行 (默认 False, 使用 NanoBotAgent)
            parallel: 并行任务数 (Docker 模式下有效)
            openclawpro_dir: OpenClawPro 源码目录 (用于 Docker 卷挂载)
        """
        # Use instance default if not explicitly specified
        if use_docker is None:
            use_docker = self._use_docker_default
        if use_docker:
            return self._evaluate_docker_nanobot(
                model_key=model_key,
                config=config,
                sample=sample,
                transcripts_dir=transcripts_dir,
                category=category,
                use_automated_checks=use_automated_checks,
                parallel=parallel,
                openclawpro_dir=openclawpro_dir,
            )
        else:
            return self._evaluate_native(
                model_key=model_key,
                config=config,
                sample=sample,
                transcripts_dir=transcripts_dir,
                category=category,
                use_automated_checks=use_automated_checks,
            )

    def _evaluate_native(
        self,
        model_key: str,
        config: dict,
        sample: int = 0,
        transcripts_dir: Path = None,
        category: str = None,
        use_automated_checks: bool = True,
    ) -> dict:
        """Native 模式: 使用 NanoBotAgent 在宿主机直接运行。"""
        NanoBotAgent = import_nanobot_agent()
        from clawevalkit.grading import run_judge_eval, run_automated_checks

        tasks = self._load_tasks(
            categories=[category] if category else TASK_CATEGORIES,
            use_docker=False,
        )
        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

        judge_key = os.getenv("JUDGE_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
        judge_model = os.getenv("JUDGE_MODEL", "anthropic/claude-sonnet-4.6")
        judge_base = os.getenv("JUDGE_BASE_URL", "https://openrouter.ai/api/v1")

        out_dir = self.results_dir / "wildclawbench" / "subset" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []

        # Check if any tasks need agent-browser
        needs_browser = any(t["task_id"] in BROWSER_TASKS for t in tasks)
        if needs_browser:
            ensure_agent_browser()

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

            workspace = Path(tempfile.mkdtemp(prefix=f"wildclawbench_{tid}_"))
            tmp_workspace_dir = workspace / "tmp_workspace"
            tmp_workspace_dir.mkdir(exist_ok=True)

            # Copy task data to workspace if available
            task_workspace = self._get_task_workspace(task)
            if task_workspace and task_workspace.exists():
                try:
                    shutil.copytree(task_workspace, workspace / "workspace", dirs_exist_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to copy task workspace: {e}")

            r = {"task_id": tid, "model_key": model_key, "status": "error", "scores": {}}
            try:
                # Build system prompt with skills if available
                system_prompt = self._build_system_prompt(task)

                agent = NanoBotAgent(
                    model=config["model"],
                    api_url=config["api_url"],
                    api_key=config["api_key"],
                    workspace=workspace,
                    timeout=task.get("timeout_seconds", 300),
                )
                result = agent.execute(
                    task["prompt"],
                    session_id=f"eval_wild_{model_key}_{tid}",
                    workspace=workspace,
                    system_prompt=system_prompt,
                )

                if result and result.transcript:
                    normalized = [
                        e["message"] if isinstance(e, dict) and "message" in e else e
                        for e in result.transcript
                    ]

                    # Save transcript
                    if transcripts_dir:
                        trans_dir = Path(transcripts_dir) / "wildclawbench" / model_key
                        trans_dir.mkdir(parents=True, exist_ok=True)
                        (trans_dir / f"{tid}_transcript.json").write_text(
                            json.dumps(normalized, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )

                    scores = {}
                    score_source = []

                    # Try automated checks first
                    if use_automated_checks and task.get("automated_checks"):
                        auto_score = run_automated_checks(
                            automated_checks=task["automated_checks"],
                            workspace=workspace,
                            transcript=normalized,
                        )
                        if auto_score and "error" not in auto_score:
                            scores.update(auto_score)
                            score_source.append("automated")

                    # Always run LLM judge as complement or fallback
                    judge_score = run_judge_eval(
                        trajectory=normalized,
                        task_id=tid,
                        category=task.get("category", "unknown"),
                        task_prompt=task["prompt"],
                        judge_model=judge_model,
                        api_key=judge_key,
                        base_url=judge_base,
                        model_name=config["name"],
                    )
                    if judge_score:
                        scores["judge_overall"] = judge_score.overall_score
                        scores["judge_task_completion"] = judge_score.task_completion
                        scores["judge_tool_usage"] = judge_score.tool_usage
                        scores["judge_reasoning"] = judge_score.reasoning
                        scores["judge_answer_quality"] = judge_score.answer_quality
                        score_source.append("judge")

                    # Determine overall score
                    if "overall_score" in scores:
                        final_score = scores["overall_score"]
                    elif "judge_overall" in scores:
                        final_score = scores["judge_overall"]
                    elif scores:
                        final_score = sum(v for v in scores.values() if isinstance(v, (int, float))) / len(
                            [v for v in scores.values() if isinstance(v, (int, float))]
                        )
                    else:
                        final_score = 0.0

                    r["status"] = "success"
                    r["scores"] = scores
                    r["scores"]["overall_score"] = final_score
                    r["score_source"] = score_source

            except Exception as e:
                r["error"] = str(e)[:500]
                logger.error(f"[{tid}] Evaluation error: {e}")

            result_file.write_text(json.dumps(r, indent=2, ensure_ascii=False))
            shutil.rmtree(workspace, ignore_errors=True)
            results.append(r)

        scores = [r["scores"]["overall_score"] for r in results if r.get("status") == "success"]
        avg = round(sum(scores) / len(scores), 3) if scores else 0
        return {
            "score": avg,
            "passed": len(scores),
            "total": len(tasks),
            "details": results,
        }

    def _evaluate_docker_nanobot(
        self,
        model_key: str,
        config: dict,
        sample: int = 0,
        transcripts_dir: Path = None,
        category: str = None,
        use_automated_checks: bool = True,
        parallel: int = 1,
        openclawpro_dir: Path = None,
    ) -> dict:
        """Docker NanoBotAgent 模式: 在容器内运行 NanoBotAgent，通过卷挂载实现代码热更新。

        基于 wildclawbench-ubuntu:v1.2 镜像，通过 volume mount 将宿主机 OpenClawPro/ 代码
        覆盖容器内版本，实现开发迭代（修改代码不用 rebuild 镜像）。
        """
        # Determine OpenClawPro directory for volume mount
        if openclawpro_dir is None:
            openclawpro_dir = Path(os.getenv("OPENCLAWPRO_DIR",
                str(Path(__file__).parent.parent.parent / "OpenClawPro")))
        if not openclawpro_dir.exists():
            raise FileNotFoundError(f"OpenClawPro directory not found: {openclawpro_dir}")

        # Docker image for NanoBotAgent mode (built from Dockerfile.nanobot)
        docker_image = os.environ.get("DOCKER_IMAGE_NANOBOT", "wildclawbench-nanobot:latest")

        tasks = self._load_tasks(
            categories=[category] if category else TASK_CATEGORIES,
            use_docker=True,
        )
        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

        out_dir = self.results_dir / "wildclawbench" / "docker_nanobot" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []

        judge_key = os.getenv("JUDGE_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
        judge_model = os.getenv("JUDGE_MODEL", "anthropic/claude-sonnet-4.6")
        judge_base = os.getenv("JUDGE_BASE_URL", "https://openrouter.ai/api/v1")

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")

        def run_single_task_docker_nanobot(task: dict, model: str) -> dict:
            """Execute a single task inside Docker container using NanoBotAgent."""
            task_id_ori = task["task_id"]
            workspace_path = task["workspace_path"]
            prompt = task["prompt"]
            timeout_seconds = task["timeout_seconds"]
            env = task.get("env", "")
            skills = task.get("skills", "")
            skills_path = task.get("skills_path", "")
            warmup = task.get("warmup", "")

            system_prompt = f"You are an expert in a restricted, non-interactive environment. Solve the task efficiently before the timeout ({timeout_seconds}s). Run all processes in the foreground without user input or background services. Provide a complete, functional solution in a single pass with no placeholders.\n"
            prompt = system_prompt + prompt

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_id = uuid.uuid4().hex[:6]
            short_task_id = re.sub(r"(\d+)_.*?(task_\d+)", r"\1_\2", task_id_ori)
            if not short_task_id:
                short_task_id = task_id_ori
            short_model = re.sub(r"[^a-zA-Z0-9.\-_]", "_", model.rsplit("/", 1)[-1])
            suffix = f"{short_model}_{timestamp}_{run_id}"
            container_name = f"nano_{short_task_id}_{suffix}"

            task_output_dir = out_dir / task["category"] / task_id_ori / suffix
            task_output_dir.mkdir(parents=True, exist_ok=True)

            result = {"task_id": container_name, "scores": {}, "error": None}
            elapsed_time = float(timeout_seconds)

            try:
                exec_path = os.path.join(workspace_path, "exec")
                tmp_path = os.path.join(workspace_path, "tmp")
                os.makedirs(exec_path, exist_ok=True)

                # Build env args for docker run
                proxy_http = os.environ.get('HTTP_PROXY_INNER', '')
                proxy_https = os.environ.get('HTTPS_PROXY_INNER', '')
                env_args = [
                    "-e", f"http_proxy={proxy_http}",
                    "-e", f"https_proxy={proxy_https}",
                    "-e", f"HTTP_PROXY={proxy_http}",
                    "-e", f"HTTPS_PROXY={proxy_https}",
                    "-e", f"no_proxy={'' if not proxy_http else os.environ.get('NO_PROXY_INNER', '')}",
                    "-e", f"OPENROUTER_API_KEY={openrouter_api_key}",
                ]
                # Add extra env vars from task
                for line in env.splitlines():
                    key = line.strip()
                    if not key or key.startswith("#"):
                        continue
                    value = os.environ.get(key, "")
                    env_args += ["-e", f"{key}={value}"]

                # Start container with volume mount for OpenClawPro (hot-reload)
                # Mount workspace at /tmp_workspace (read-write) so grading finds files at /tmp_workspace/workspace/gt/
                docker_run_cmd = [
                    "docker", "run", "-d",
                    "--name", container_name,
                    "-v", f"{workspace_path}:/tmp_workspace:rw",
                    "-v", f"{openclawpro_dir}:/root/OpenClawPro:rw",
                    *env_args,
                    docker_image,
                    "/bin/bash", "-c", "tail -f /dev/null",
                ]
                logger.info("[%s] Starting container with OpenClawPro volume mount", container_name)
                r = subprocess.run(docker_run_cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    raise RuntimeError(f"Container startup failed:\n{r.stderr}")
                logger.info("[%s] Container ID: %s", container_name, r.stdout.strip()[:12])

                # Workspace is mounted at /tmp_workspace directly
                # Create symlink /tmp_workspace/workspace -> /tmp_workspace (.) for grading code compatibility
                # The grading code expects TMP_WORKSPACE/workspace/gt/ but files are at TMP_WORKSPACE/gt/
                subprocess.run(
                    ["docker", "exec", container_name, "/bin/bash", "-c",
                     "cd /tmp_workspace && ln -sf . workspace 2>/dev/null || true"],
                    capture_output=True, text=True,
                )

                # Copy tmp files if exists
                if tmp_path and os.path.exists(tmp_path):
                    mkdir_cmd = ["docker", "exec", container_name, "mkdir", "-p", "/tmp_workspace/tmp"]
                    subprocess.run(mkdir_cmd, capture_output=True)
                    cp_cmd = ["docker", "cp", f"{tmp_path}/.", f"{container_name}:/tmp_workspace/tmp/"]
                    subprocess.run(cp_cmd, capture_output=True, text=True)

                # Setup skills inside container
                if skills and skills_path:
                    for line in skills.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        subprocess.run(
                            ["docker", "exec", container_name, "mkdir", "-p", f"/tmp_workspace/skills/{line}"],
                            capture_output=True, text=True,
                        )
                        subprocess.run(
                            ["docker", "cp", f"{skills_path}/{line}", f"{container_name}:/tmp_workspace/skills"],
                            capture_output=True, text=True,
                        )

                # Run warmup commands
                if warmup:
                    commands = [
                        line.strip() for line in warmup.splitlines()
                        if line.strip() and not line.strip().startswith("#")
                    ]
                    for cmd in commands:
                        r = subprocess.run(
                            ["docker", "exec", container_name, "/bin/bash", "-c", cmd],
                            capture_output=True, text=True,
                        )
                        if r.returncode != 0:
                            logger.warning("[%s] Warmup command failed: %s", container_name, cmd)

                # Prepare NanoBotAgent execution script
                # Build system prompt with skills
                skills_summary = ""
                if skills and skills_path:
                    try:
                        skill_docs = []
                        for line in skills.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            skill_file = Path(skills_path) / line / "SKILL.md"
                            if skill_file.exists():
                                skill_docs.append(f"\n\n## Skill: {line}\n\n{skill_file.read_text()}")
                        if skill_docs:
                            skills_summary = "You have access to the following skills. Use them when appropriate:\n" + "\n".join(skill_docs)
                    except Exception as e:
                        logger.warning("[%s] Failed to load skills: %s", container_name, e)

                # Write execution script to a temp file, copy into container, execute
                exec_script = f"""
import sys
import json
import time
from pathlib import Path

# Add OpenClawPro to path
sys.path.insert(0, '/root/OpenClawPro')

from harness.agent.nanobot import NanoBotAgent

workspace = Path('/tmp_workspace')
session_id = 'eval_{model_key}_{task_id_ori}'

agent = NanoBotAgent(
    model='{model}',
    api_url='{config["api_url"]}',
    api_key='{config["api_key"]}',
    workspace=workspace,
    timeout={timeout_seconds},
)

# Build system prompt
system_prompt = '''You are an expert in a restricted, non-interactive environment. Solve the task efficiently before the timeout ({timeout_seconds}s). Run all processes in the foreground without user input or background services. Provide a complete, functional solution in a single pass with no placeholders.'''
{skills_summary and f"system_prompt = system_prompt + '''\\n\\n{skills_summary}'''" or ""}

try:
    start_time = time.time()
    result = agent.execute(
        '''{prompt.replace("'", "\\'")}''',
        session_id=session_id,
        workspace=workspace,
        system_prompt=system_prompt,
    )
    elapsed = time.time() - start_time

    # Save transcript to workspace
    transcript_file = workspace / '.sessions' / f'{{session_id}}.json'
    if transcript_file.exists():
        transcript_data = json.loads(transcript_file.read_text())
    else:
        transcript_data = result.transcript if result.transcript else []

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

# Write result to file
(workspace / 'agent_result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
print('DONE')
"""

                # Copy script into container and execute
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(exec_script)
                    script_path = f.name

                try:
                    subprocess.run(["docker", "cp", script_path, f"{container_name}:/tmp/exec_nanobot.py"], check=True)
                finally:
                    Path(script_path).unlink(missing_ok=True)

                logger.info("[%s] Executing NanoBotAgent...", container_name)
                start_time = time.perf_counter()

                exec_cmd = [
                    "docker", "exec", container_name,
                    "python3", "/tmp/exec_nanobot.py"
                ]
                exec_proc = subprocess.run(exec_cmd, capture_output=True, text=True, timeout=timeout_seconds + 60)
                elapsed_time = time.perf_counter() - start_time

                if exec_proc.returncode != 0:
                    logger.warning("[%s] NanoBotAgent exec returned non-zero: %s", container_name, exec_proc.stderr)
                logger.info("[%s] NanoBotAgent finished in %.2f seconds", container_name, elapsed_time)

                # Copy results from container
                result_file_host = task_output_dir / "agent_result.json"
                subprocess.run(["docker", "cp", f"{container_name}:/tmp_workspace/agent_result.json", str(result_file_host)])

                # Copy transcript if exists
                transcript_host = task_output_dir / "transcript.json"
                subprocess.run([
                    "docker", "cp",
                    f"{container_name}:/tmp_workspace/.sessions/eval_{model_key}_{task_id_ori}.json",
                    str(transcript_host)
                ], capture_output=True)

                # Copy output files from container's /tmp_workspace/ to host workspace for grading
                # This is needed because the agent writes to /tmp_workspace/ but grading checks the host workspace
                results_in_container = f"{container_name}:/tmp_workspace/results"
                results_on_host = Path(workspace_path) / "results"
                if subprocess.run(
                    ["docker", "cp", results_in_container, str(results_on_host.parent)],
                    capture_output=True
                ).returncode == 0:
                    logger.info("[%s] Copied results from container to host", container_name)
                else:
                    # Try individual files if directory copy fails
                    for fname in ["transcript_en.txt", "transcript_zh.txt", "output.mp4"]:
                        src = f"{container_name}:/tmp_workspace/results/{fname}"
                        dst = results_on_host / fname
                        if subprocess.run(["docker", "cp", src, str(dst)], capture_output=True).returncode == 0:
                            logger.info("[%s] Copied %s from container", container_name, fname)

                # Load result
                if result_file_host.exists():
                    agent_result = json.loads(result_file_host.read_text(encoding="utf-8"))
                else:
                    agent_result = {"status": "error", "error": "No result file found"}

                result["status"] = agent_result.get("status", "error")
                result["error"] = agent_result.get("error", "")
                result["usage"] = agent_result.get("usage", {})
                result["usage"]["elapsed_time"] = round(elapsed_time, 2)

                # Build trajectory for grading
                trajectory = agent_result.get("transcript", [])
                if not trajectory and transcript_host.exists():
                    try:
                        trajectory = json.loads(transcript_host.read_text(encoding="utf-8"))
                        if isinstance(trajectory, list):
                            trajectory = trajectory
                    except Exception:
                        trajectory = []

                # Save transcript
                if transcripts_dir and trajectory:
                    trans_dir = Path(transcripts_dir) / "wildclawbench" / model_key
                    trans_dir.mkdir(parents=True, exist_ok=True)
                    (trans_dir / f"{task_id_ori}_transcript.json").write_text(
                        json.dumps(trajectory, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )

                # Grading - run inside container for path consistency
                scores = {}
                score_source = []

                if not result.get("error") and task.get("automated_checks"):
                    try:
                        # Build grading script that runs inside container
                        grading_script = f'''
import json
import os
import sys
from pathlib import Path

# Set up environment for grading
os.environ["TMP_WORKSPACE"] = "/tmp_workspace"
os.chdir("/tmp_workspace")

# Add OpenClawPro to path for any needed imports
sys.path.insert(0, "/root/OpenClawPro")

automated_checks = """{task["automated_checks"].replace('"', '\\"').replace('\\n', '\\\\n')}"""
transcript_data = {json.dumps(trajectory)}

# Execute the grading code
exec(compile(automated_checks, "<grading>", "exec"))

# Call grade function
try:
    grading_result = grade(
        workspace_path="/tmp_workspace",
        transcript=transcript_data
    )
    print(json.dumps(grading_result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''
                        # Write and copy grading script to container
                        import tempfile as tmp
                        with tmp.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                            f.write(grading_script)
                            grading_script_path = f.name

                        try:
                            subprocess.run(
                                ["docker", "cp", grading_script_path, f"{container_name}:/tmp/exec_grading.py"],
                                check=True
                            )
                        finally:
                            Path(grading_script_path).unlink(missing_ok=True)

                        # Execute grading in container
                        logger.info("[%s] Running grading inside container...", container_name)
                        grading_proc = subprocess.run(
                            ["docker", "exec", container_name, "python3", "/tmp/exec_grading.py"],
                            capture_output=True, text=True, timeout=180
                        )

                        if grading_proc.returncode == 0:
                            try:
                                auto_score = json.loads(grading_proc.stdout.strip())
                                if "error" not in auto_score:
                                    scores.update(auto_score)
                                    score_source.append("automated")
                                    logger.info("[%s] Automated grading complete", container_name)
                                else:
                                    logger.error("[%s] Grading returned error: %s", container_name, auto_score.get("error"))
                            except json.JSONDecodeError:
                                logger.error("[%s] Failed to parse grading result", container_name)
                        else:
                            logger.error("[%s] Grading failed: %s", container_name, grading_proc.stderr[:500])

                    except Exception as exc:
                        logger.error("[%s] Grading failed: %s", container_name, exc)

                # LLM Judge scoring
                if trajectory:
                    try:
                        from clawevalkit.grading import run_judge_eval
                        judge_score = run_judge_eval(
                            trajectory=trajectory,
                            task_id=container_name,
                            category=task.get("category", "unknown"),
                            task_prompt=task["prompt"],
                            judge_model=judge_model,
                            api_key=judge_key,
                            base_url=judge_base,
                            model_name=config.get("name", "unknown"),
                        )
                        if judge_score:
                            scores["judge_overall"] = judge_score.overall_score
                            scores["judge_task_completion"] = judge_score.task_completion
                            scores["judge_tool_usage"] = judge_score.tool_usage
                            scores["judge_reasoning"] = judge_score.reasoning
                            scores["judge_answer_quality"] = judge_score.answer_quality
                            score_source.append("judge")
                            logger.info("[%s] LLM judge scoring complete", container_name)
                    except Exception as exc:
                        logger.error("[%s] LLM judge failed: %s", container_name, exc)

                # Determine final score
                if scores:
                    if "overall_score" in scores:
                        final_score = scores["overall_score"]
                    elif "judge_overall" in scores:
                        final_score = scores["judge_overall"]
                    else:
                        numeric_vals = [v for v in scores.values() if isinstance(v, (int, float))]
                        final_score = sum(numeric_vals) / len(numeric_vals) if numeric_vals else 0.0
                    result["scores"] = scores
                    result["scores"]["overall_score"] = final_score
                    result["score_source"] = score_source
                elif not result.get("error"):
                    result["scores"] = {"overall_score": 0.0}

            except subprocess.TimeoutExpired:
                logger.info("[%s] Agent timed out...", container_name)
                elapsed_time = timeout_seconds
                result["error"] = f"Timeout after {timeout_seconds} seconds"
            except Exception as exc:
                logger.error("[%s] Execution error: %s", container_name, exc)
                elapsed_time = timeout_seconds
                result["error"] = str(exc)
            finally:
                # Cleanup container
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
                logger.info("[%s] Container cleaned up", container_name)

            return result

        # Execute tasks
        if parallel <= 1:
            for task in tasks:
                results.append(run_single_task_docker_nanobot(task, config["model"]))
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {
                    pool.submit(run_single_task_docker_nanobot, task, config["model"]): task["task_id"]
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
        valid_scores = [r["scores"].get("overall_score", 0) for r in results if r.get("scores") and "error" not in r["scores"]]
        avg = round(sum(valid_scores) / len(valid_scores), 3) if valid_scores else 0

        return {
            "score": avg,
            "passed": len(valid_scores),
            "total": len(tasks),
            "details": results,
        }

    def collect(self, model_key: str) -> dict | None:
        result_dir = self._find_result_dir("wildclawbench")
        if not result_dir:
            return None
        out_dir = result_dir / "subset" / model_key
        if not out_dir.exists():
            return None
        scores = []
        for f in out_dir.glob("*.json"):
            try:
                r = json.loads(f.read_text())
                s = r.get("scores", {}).get("overall_score") or r.get("judge_scores", {}).get("overall_score")
                if r.get("status") == "success" and s is not None:
                    scores.append(float(s))
            except Exception:
                pass
        if not scores:
            return None
        return {"score": round(sum(scores) / len(scores), 3), "passed": len(scores), "total": self.TASK_COUNT}

    def _load_tasks(self, categories: list = None, use_docker: bool = False) -> list:
        """加载 WildClawBench 任务（从 ClawEvalKit 的 benchmarks/ 目录）。

        Args:
            categories: List of category folder names to load. If None, loads all.
            use_docker: 是否使用 Docker 模式解析器 (包含 env, warmup 等额外字段)

        Returns:
            List of task dicts with task_id, prompt, workspace_path, skills, automated_checks, etc.
        """
        candidates = [
            self.base_dir / "benchmarks" / "wildclawbench" / "tasks",
            Path(os.getenv("OPENCLAWPRO_DIR", "")) / "benchmarks" / "wildclawbench" / "tasks",
        ]

        tasks = []
        for tasks_dir in candidates:
            if not tasks_dir.exists():
                continue

            if categories is None:
                categories = TASK_CATEGORIES

            for cat in categories:
                cat_dir = tasks_dir / cat
                if not cat_dir.exists():
                    continue

                for md in sorted(cat_dir.glob("*.md")):
                    if md.stem == "task0_template":
                        continue
                    try:
                        task_data = parse_task_md(md, use_docker=use_docker)
                        tasks.append(task_data)
                    except Exception as e:
                        logger.warning(f"Failed to parse task {md}: {e}")
            break

        return tasks

    def _get_task_workspace(self, task: dict) -> Path | None:
        """Get the workspace directory for a task if it exists."""
        workspace_path = task.get("workspace_path", "")
        if not workspace_path:
            return None

        candidates = [
            self.base_dir / "benchmarks" / "wildclawbench" / workspace_path,
            Path(os.getenv("OPENCLAWPRO_DIR", "")) / "benchmarks" / "wildclawbench" / workspace_path,
        ]

        for p in candidates:
            if p.exists():
                return p
        return None

    def _build_system_prompt(self, task: dict) -> str:
        """Build system prompt with skills documentation."""
        skills = task.get("skills", [])
        if not skills:
            return ""

        # Handle both list (native) and newline-separated string (docker) formats
        if isinstance(skills, str):
            skill_names = [s.strip() for s in skills.splitlines() if s.strip()]
        else:
            skill_names = skills

        skill_docs = []
        skills_base = [
            self.base_dir / "benchmarks" / "wildclawbench" / "skills",
            Path(os.getenv("OPENCLAWPRO_DIR", "")) / "benchmarks" / "wildclawbench" / "skills",
        ]

        for skill_name in skill_names:
            for base in skills_base:
                skill_file = base / skill_name / "SKILL.md"
                if skill_file.exists():
                    skill_docs.append(f"\n\n## Skill: {skill_name}\n\n{skill_file.read_text()}")
                    break

        if skill_docs:
            return (
                "You have access to the following skills. Use them when appropriate:\n"
                + "\n".join(skill_docs)
            )
        return ""
