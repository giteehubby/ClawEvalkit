"""WildClawBench — 60 tasks across 6 categories.

评分方式: NanoBotAgent 执行 + LLM Judge 评分 (0~1)。
数据来源: 本地 benchmarks/wildclawbench/tasks/。

支持两种执行模式:
  - use_docker=True:  使用 Docker 容器运行 OpenClaw (依赖 wildclawbench-ubuntu:v0.4 镜像)
  - use_docker=False: 使用 NanoBotAgent 在宿主机直接运行 (默认, 无需 Docker)

依赖:
  - 推理框架: OpenClawPro (提供 NanoBotAgent) 或 Docker
  - 评分逻辑: clawevalkit.grading (提供 run_judge_eval, run_automated_checks)
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

# Docker config
DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE", "wildclawbench-ubuntu:v0.4")
TMP_WORKSPACE = "/tmp_workspace"


# ============================================================================
# Shared Task Parsing Utilities
# ============================================================================

def _strip_codeblock(raw: str) -> str:
    """Remove markdown code block delimiters."""
    s = re.sub(r"^```[^\n]*\n?", "", raw.strip())
    s = re.sub(r"\n?```$", "", s).strip()
    return s


def _parse_md_sections(body: str) -> dict[str, str]:
    """Parse markdown body into sections by ## headers."""
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
    return sections


def _parse_task_md_base(task_file: Path) -> tuple[dict, dict[str, str]]:
    """Parse YAML frontmatter and markdown body sections from task.md."""
    import yaml
    content = task_file.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not fm_match:
        raise ValueError(f"YAML frontmatter not found: {task_file}")
    metadata = yaml.safe_load(fm_match.group(1))
    sections = _parse_md_sections(fm_match.group(2))
    return metadata, sections


def parse_task_md(task_file: Path, use_docker: bool = False) -> dict:
    """Parse task.md and return task dict for either mode."""
    metadata, sections = _parse_task_md_base(task_file)
    task_id = metadata.get("id", task_file.stem)
    prompt = sections.get("Prompt", "").strip()
    raw_workspace = sections.get("Workspace Path", "").strip()
    workspace_path = _strip_codeblock(raw_workspace)
    automated_checks = _strip_codeblock(sections.get("Automated Checks", ""))

    base_result = {
        "task_id": task_id,
        "prompt": prompt,
        "workspace_path": workspace_path,
        "automated_checks": automated_checks,
        "timeout_seconds": int(metadata.get("timeout_seconds", 900 if use_docker else 300)),
        "file_path": str(task_file.resolve()),
        "category": task_file.parent.name,
    }

    if use_docker:
        # Resolve paths relative to benchmarks/wildclawbench
        benchmarks_dir = Path(__file__).parent.parent.parent / "benchmarks" / "wildclawbench"
        wp = Path(workspace_path)
        if not wp.is_absolute():
            wp = (benchmarks_dir / wp).resolve()
        base_result["workspace_path"] = str(wp)
        skills_path = str((benchmarks_dir / "skills").resolve())

        return {
            **base_result,
            "skills_path": skills_path,
            "env": _strip_codeblock(sections.get("Env", "")),
            "skills": _strip_codeblock(sections.get("Skills", "")),
            "warmup": _strip_codeblock(sections.get("Warmup", "")),
        }
    else:
        skills_raw = sections.get("Skills", "").strip()
        skills = [s.strip() for s in _strip_codeblock(skills_raw).split("\n") if s.strip()]
        return {**base_result, "skills": skills}


# ============================================================================
# Docker Execution Script Builder
# ============================================================================

def _build_exec_script(model_key: str, task_id_ori: str, prompt: str, timeout_seconds: int,
                        config: dict, skills_summary: str) -> str:
    """Build NanoBotAgent execution script for running inside Docker container."""
    # Use api_key directly from config (like skillsbench/agentbench)
    api_key = config.get("api_key", "")

    return f"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, '/root/OpenClawPro')
from harness.agent.nanobot import NanoBotAgent

workspace = Path('/tmp_workspace')
session_id = 'eval_{model_key}_{task_id_ori}'

agent = NanoBotAgent(
    model='{config["model"]}',
    api_url='{config["api_url"]}',
    api_key='{api_key}',
    workspace=workspace,
    timeout={timeout_seconds},
    disable_safety_guard=True,
)

system_prompt = \"\"\"You are an expert in a restricted, non-interactive environment. Solve the task efficiently before the timeout ({timeout_seconds}s). Run all processes in the foreground without user input or background services. Provide a complete, functional solution in a single pass with no placeholders.\"\"\"
{skills_summary and f"system_prompt = system_prompt + '''\\\\n\\\\n{skills_summary}'''" or ""}

try:
    start_time = time.time()
    result = agent.execute(
        '''{prompt.replace("'", "\\\\'")}''',
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


def _build_grading_script(automated_checks: str, trajectory: list) -> str:
    """Build grading script for running inside Docker container."""
    # Use base64 to safely embed the Python code as bytes
    import base64
    checks_b64 = base64.b64encode(automated_checks.encode('utf-8')).decode('ascii')
    transcript_json = json.dumps(trajectory)
    return f'''
import json
import os
import sys
import base64
from pathlib import Path

os.environ["TMP_WORKSPACE"] = "/tmp_workspace"
os.chdir("/tmp_workspace")
sys.path.insert(0, "/root/OpenClawPro")

automated_checks = base64.b64decode("{checks_b64}").decode("utf-8")
transcript_data = {transcript_json}

exec(compile(automated_checks, "<grading>", "exec"))

try:
    grading_result = grade(workspace_path="/tmp_workspace", transcript=transcript_data)
    print(json.dumps(grading_result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''


# ============================================================================
# Docker Container Helpers
# ============================================================================

def _start_container(container_name: str, workspace_path: str, openclawpro_dir: Path,
                     docker_image: str, env_args: list) -> None:
    """Start Docker container with selective volume mounts (gt excluded from agent access)."""
    exec_path = os.path.join(workspace_path, "exec")
    tmp_path = os.path.join(workspace_path, "tmp")
    results_path = os.path.join(workspace_path, "results")
    skills_path = os.path.join(workspace_path, "skills")
    workspace_inner = os.path.join(workspace_path, "workspace")
    gt_dir = os.path.join(workspace_path, "gt")

    os.makedirs(exec_path, exist_ok=True)
    os.makedirs(tmp_path, exist_ok=True)

    volume_mounts = [
        "-v", f"{exec_path}:/tmp_workspace/exec:rw",
        "-v", f"{tmp_path}:/tmp_workspace/tmp:rw",
        "-v", f"{results_path}:/tmp_workspace/results:rw",
        "-v", f"{openclawpro_dir}:/root/OpenClawPro:rw",
    ]
    if os.path.exists(skills_path):
        volume_mounts.extend(["-v", f"{skills_path}:/tmp_workspace/skills:rw"])
    if os.path.exists(workspace_inner):
        volume_mounts.extend(["-v", f"{workspace_inner}:/tmp_workspace/workspace:rw"])
    # Ground truth mounted readonly at /tmp_workspace/gt/ for grading ONLY
    volume_mounts.extend(["-v", f"{gt_dir}:/tmp_workspace/gt:ro"])

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


def _setup_container(container_name: str, workspace_path: str, skills: str, skills_path: str,
                      warmup: str, tmp_path: str) -> None:
    """Copy files and run warmup commands inside container."""
    # Copy tmp files
    if os.path.exists(tmp_path):
        subprocess.run(["docker", "exec", container_name, "mkdir", "-p", "/tmp_workspace/tmp"],
                       capture_output=True)
        subprocess.run(["docker", "cp", f"{tmp_path}/.", f"{container_name}:/tmp_workspace/tmp/"],
                       capture_output=True)

    # Copy exec files to /tmp_workspace root (grading scripts expect files directly under /tmp_workspace/)
    exec_path = os.path.join(workspace_path, "exec")
    if os.path.exists(exec_path):
        subprocess.run(["docker", "exec", container_name, "mkdir", "-p", "/tmp_workspace"],
                       capture_output=True)
        subprocess.run(["docker", "cp", f"{exec_path}/.", f"{container_name}:/tmp_workspace/"],
                       capture_output=True)

    # Setup skills
    if skills and skills_path:
        for line in skills.splitlines():
            line = line.strip()
            if not line:
                continue
            subprocess.run(
                ["docker", "exec", container_name, "mkdir", "-p", f"/tmp_workspace/skills/{line}"],
                capture_output=True)
            subprocess.run(
                ["docker", "cp", f"{skills_path}/{line}", f"{container_name}:/tmp_workspace/skills"],
                capture_output=True)

    # Run warmup
    if warmup:
        for cmd in [l.strip() for l in warmup.splitlines() if l.strip() and not l.strip().startswith("#")]:
            r = subprocess.run(["docker", "exec", container_name, "/bin/bash", "-c", cmd],
                               capture_output=True, text=True)
            if r.returncode != 0:
                logger.warning("[%s] Warmup command failed: %s", container_name, cmd)


def _load_skills_summary(skills: str, skills_path: str) -> str:
    """Build skills summary for system prompt."""
    if not skills or not skills_path:
        return ""
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
            return "You have access to the following skills. Use them when appropriate:\n" + "\n".join(skill_docs)
    except Exception as e:
        logger.warning("[skills] Failed to load skills: %s", e)
    return ""


def _run_agent_in_container(container_name: str, exec_script: str, timeout_seconds: int) -> tuple[subprocess.CompletedProcess, float]:
    """Execute NanoBotAgent inside container, return (process_result, elapsed_time)."""
    import tempfile
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


def _copy_results_from_container(container_name: str, workspace_path: str, task_output_dir: Path) -> tuple[Path, Path]:
    """Copy agent result and transcript from container to host. Returns (result_file, transcript_file)."""
    result_file_host = task_output_dir / "agent_result.json"
    subprocess.run(["docker", "cp", f"{container_name}:/tmp_workspace/agent_result.json", str(result_file_host)])

    transcript_host = task_output_dir / "transcript.json"
    subprocess.run(["docker", "cp",
                    f"{container_name}:/tmp_workspace/.sessions/eval_$model_key_$task_id_ori.json",
                    str(transcript_host)], capture_output=True)

    # Copy results dir
    results_on_host = Path(workspace_path) / "results"
    if subprocess.run(["docker", "cp", f"{container_name}:/tmp_workspace/results", str(results_on_host.parent)],
                      capture_output=True).returncode != 0:
        for fname in ["transcript_en.txt", "transcript_zh.txt", "output.mp4"]:
            src = f"{container_name}:/tmp_workspace/results/{fname}"
            dst = results_on_host / fname
            subprocess.run(["docker", "cp", src, str(dst)], capture_output=True)

    return result_file_host, transcript_host


def _compute_final_score(scores: dict, score_source: list, result: dict) -> None:
    """Compute and set final_score in scores dict."""
    if "overall_score" in scores:
        final_score = scores["overall_score"]
    elif "judge_overall" in scores:
        final_score = scores["judge_overall"]
    else:
        numeric_vals = [v for v in scores.values() if isinstance(v, (int, float))]
        final_score = sum(numeric_vals) / len(numeric_vals) if numeric_vals else 0.0
    scores["overall_score"] = final_score
    result["scores"] = scores
    result["score_source"] = score_source


def _run_grading(container_name: str, task: dict, trajectory: list, result: dict, model_key: str,
                 judge_key: str = "", judge_model: str = "anthropic/claude-sonnet-4.6",
                 judge_base: str = "https://openrouter.ai/api/v1") -> tuple[dict, list]:
    """Run automated grading inside container. Returns (scores, score_source)."""
    scores = {}
    score_source = []
    if result.get("error") or not task.get("automated_checks"):
        return scores, score_source

    try:
        grading_script = _build_grading_script(task["automated_checks"], trajectory)
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(grading_script)
            script_path = f.name
        try:
            subprocess.run(["docker", "cp", script_path, f"{container_name}:/tmp/exec_grading.py"], check=True)
        finally:
            Path(script_path).unlink(missing_ok=True)

        logger.info("[%s] Running grading inside container...", container_name)
        grading_proc = subprocess.run(
            ["docker", "exec", "-e", f"JUDGE_MODEL={judge_model}", "-e", f"JUDGE_API_KEY={judge_key}",
             "-e", f"JUDGE_BASE_URL={judge_base}", "-e", f"OPENROUTER_API_KEY={judge_key}",
             container_name, "python3", "/tmp/exec_grading.py"],
            capture_output=True, text=True, timeout=600)

        if grading_proc.returncode == 0:
            try:
                stdout = grading_proc.stdout.strip()
                logger.info("[%s] Grading stdout (first 500): %s", container_name, stdout[:500])
                auto_score = json.loads(stdout)
                if "error" not in auto_score:
                    scores.update(auto_score)
                    score_source.append("automated")
                    logger.info("[%s] Automated grading complete", container_name)
                else:
                    logger.error("[%s] Grading error: %s", container_name, auto_score.get("error"))
            except json.JSONDecodeError as e:
                logger.error("[%s] Failed to parse grading result: %s, stdout: %s", container_name, e, grading_proc.stdout[:500])
        else:
            logger.error("[%s] Grading failed: %s", container_name, grading_proc.stderr[:500])
    except Exception as exc:
        logger.error("[%s] Grading failed: %s", container_name, exc)

    return scores, score_source


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
        task_ids: list = None,
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
            task_ids: 指定任务ID列表 (如 ["01_Productivity_Flow_task_6_calendar_scheduling"])
            use_automated_checks: 是否使用自动化 checks
            use_docker: 是否使用 Docker 容器运行 (默认 False, 使用 NanoBotAgent)
            parallel: 并行任务数 (Docker 模式下有效)
            openclawpro_dir: OpenClawPro 源码目录 (用于 Docker 卷挂载)
        """
        # Use instance default if not explicitly specified
        if use_docker is None:
            use_docker = self._use_docker_default
        force = kwargs.pop("force", False)
        if use_docker:
            return self._evaluate_docker_nanobot(
                model_key=model_key,
                config=config,
                sample=sample,
                transcripts_dir=transcripts_dir,
                category=category,
                task_ids=task_ids,
                use_automated_checks=use_automated_checks,
                parallel=parallel,
                openclawpro_dir=openclawpro_dir,
                force=force,
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
        task_ids: list = None,
    ) -> dict:
        """Native 模式: 使用 NanoBotAgent 在宿主机直接运行。"""
        NanoBotAgent = import_nanobot_agent()
        from clawevalkit.grading import run_judge_eval, run_automated_checks

        tasks = self._load_tasks(
            categories=[category] if category else TASK_CATEGORIES,
            use_docker=False,
        )
        # Filter by task_ids if specified
        if task_ids:
            tasks = [t for t in tasks if t["task_id"] in task_ids]
        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

        judge_key = os.getenv("JUDGE_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
        judge_model = os.getenv("JUDGE_MODEL", "anthropic/claude-sonnet-4.6")
        judge_base = os.getenv("JUDGE_BASE_URL", "https://openrouter.ai/api/v1")

        # Avoid double nesting if results_dir already contains wildclawbench/subset/model_key
        if self.results_dir.name == model_key and self.results_dir.parent.name == "subset":
            out_dir = self.results_dir
        else:
            out_dir = self.results_dir / "wildclawbench" / "subset" / model_key
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

            workspace = Path(tempfile.mkdtemp(prefix=f"wildclawbench_{tid}_"))
            tmp_workspace_dir = workspace / "tmp_workspace"
            tmp_workspace_dir.mkdir(exist_ok=True)

            # Copy task data to workspace if available
            task_workspace = self._get_task_workspace(task)
            if task_workspace and task_workspace.exists():
                try:
                    # Copy exec files to tmp_workspace (agent expects files under /tmp_workspace/)
                    exec_path = task_workspace / "exec"
                    if exec_path.exists():
                        shutil.copytree(exec_path, tmp_workspace_dir, dirs_exist_ok=True)
                    # Also copy other directories if needed
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
                    max_iterations=100,
                )

                if result and result.transcript:
                    normalized = [
                        e["message"] if isinstance(e, dict) and "message" in e else e
                        for e in result.transcript
                    ]

                    # Save transcript (unified structure: outputs/wildclawbench/transcripts/{model}/{task}/transcript.json)
                    if transcripts_dir:
                        trans_dir = self.results_dir / "wildclawbench" / "transcripts" / model_key / tid
                        trans_dir.mkdir(parents=True, exist_ok=True)
                        (trans_dir / "transcript.json").write_text(
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
            "scored": len(scores),
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
        task_ids: list = None,
        use_automated_checks: bool = True,
        parallel: int = 1,
        openclawpro_dir: Path = None,
        force: bool = False,
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
        docker_image = os.environ.get("DOCKER_IMAGE_NANOBOT", "wildclawbench-nanobot:v3")

        tasks = self._load_tasks(
            categories=[category] if category else TASK_CATEGORIES,
            use_docker=True,
        )
        # Filter by task_ids if specified
        if task_ids:
            tasks = [t for t in tasks if t["task_id"] in task_ids]
        if sample and sample < len(tasks):
            random.seed(42)
            tasks = random.sample(tasks, sample)

        # Avoid double nesting if results_dir already contains wildclawbench/model_key
        if self.results_dir.name == model_key and self.results_dir.parent.name == "wildclawbench":
            out_dir = self.results_dir
        else:
            out_dir = self.results_dir / "wildclawbench" / model_key
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []

        judge_key = os.getenv("JUDGE_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
        judge_model = os.getenv("JUDGE_MODEL", "anthropic/claude-sonnet-4.6")
        judge_base = os.getenv("JUDGE_BASE_URL", "https://openrouter.ai/api/v1")

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")

        def run_single_task_docker_nanobot(task: dict, model: str, force: bool = False) -> dict:
            """Execute a single task inside Docker container using NanoBotAgent."""
            task_id_ori = task["task_id"]
            workspace_path = task["workspace_path"]
            timeout_seconds = task["timeout_seconds"]

            # Check cache (skip if force=True)
            task_output_dir = out_dir / task_id_ori
            task_output_dir.mkdir(parents=True, exist_ok=True)
            dedup_file = task_output_dir / "result.json"
            if not force and dedup_file.exists():
                try:
                    cached = json.loads(dedup_file.read_text())
                    if cached.get("status") == "success" and cached.get("scores", {}).get("overall_score") is not None:
                        logger.info("[%s] Found cached result, skipping", task_id_ori)
                        return {**cached, "_from_cache": True}
                except Exception:
                    pass

            # Generate container name
            import time
            timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
            short_task = re.sub(r"(\d+)_.*?(task_\d+)", r"\1_\2", task_id_ori) or task_id_ori
            short_model = re.sub(r"[^a-zA-Z0-9.\-_]", "_", model.rsplit("/", 1)[-1])
            container_name = f"nano_{short_task}_{short_model}_{timestamp}"

            result = {"task_id": container_name, "scores": {}, "error": None}

            try:
                # Build env args
                proxy_http = os.environ.get('HTTP_PROXY_INNER', '')
                proxy_https = os.environ.get('HTTPS_PROXY_INNER', '')
                env_args = [
                    "-e", f"http_proxy={proxy_http}",
                    "-e", f"https_proxy={proxy_https}",
                    "-e", f"HTTPS_PROXY={proxy_https}",
                    "-e", f"no_proxy={'' if not proxy_http else os.environ.get('NO_PROXY_INNER', '')}",
                ]
                # Pass API keys for compatibility
                env_args.extend(["-e", f"OPENROUTER_API_KEY={openrouter_api_key}"])
                minimax_api_key = os.getenv("MINIMAX_API_KEY", "")
                if minimax_api_key:
                    env_args.extend(["-e", f"MINIMAX_API_KEY={minimax_api_key}"])
                    # Also set ANTHROPIC_API_KEY for litellm compatibility with MiniMax
                    env_args.extend(["-e", f"ANTHROPIC_API_KEY={minimax_api_key}"])
                for line in task.get("env", "").splitlines():
                    key = line.strip()
                    if key and not key.startswith("#"):
                        env_args += ["-e", f"{key}={os.environ.get(key, '')}"]

                # Start container
                _start_container(container_name, workspace_path, openclawpro_dir, docker_image, env_args)
                logger.info("[%s] Container started", container_name)

                # Setup container
                _setup_container(container_name, workspace_path, task.get("skills", ""),
                               task.get("skills_path", ""), task.get("warmup", ""),
                               os.path.join(workspace_path, "tmp"))

                # Build and run agent
                skills_summary = _load_skills_summary(task.get("skills", ""), task.get("skills_path", ""))
                exec_script = _build_exec_script(model_key, task_id_ori, task["prompt"],
                                                timeout_seconds, config, skills_summary)
                exec_proc, elapsed_time = _run_agent_in_container(container_name, exec_script, timeout_seconds)
                logger.info("[%s] Agent finished in %.2fs", container_name, elapsed_time)

                # Copy results
                result_file, transcript_file = _copy_results_from_container(
                    container_name, workspace_path, task_output_dir)

                # Load agent result
                agent_result = json.loads(result_file.read_text()) if result_file.exists() else {"status": "error"}
                result["status"] = agent_result.get("status", "error")
                result["error"] = agent_result.get("error", "")
                result["usage"] = {**agent_result.get("usage", {}), "elapsed_time": round(elapsed_time, 2)}

                # Build trajectory
                trajectory = agent_result.get("transcript", [])
                if not trajectory and transcript_file.exists():
                    try:
                        trajectory = json.loads(transcript_file.read_text())
                    except Exception:
                        trajectory = []

                # Save transcript
                if trajectory:
                    trans_dir = self.results_dir / "wildclawbench" / "transcripts" / model_key / task_id_ori
                    trans_dir.mkdir(parents=True, exist_ok=True)
                    (trans_dir / "transcript.json").write_text(json.dumps(trajectory, ensure_ascii=False))

                # Grading
                scores, score_source = _run_grading(
                    container_name, task, trajectory, result, model_key,
                    judge_key=judge_key, judge_model=judge_model, judge_base=judge_base)

                # LLM Judge
                if trajectory:
                    try:
                        from clawevalkit.grading import run_judge_eval
                        judge_score = run_judge_eval(
                            trajectory=trajectory, task_id=container_name,
                            category=task.get("category", "unknown"), task_prompt=task["prompt"],
                            judge_model=judge_model, api_key=judge_key, base_url=judge_base,
                            model_name=config.get("name", "unknown"))
                        if judge_score:
                            scores.update({
                                "judge_overall": judge_score.overall_score,
                                "judge_task_completion": judge_score.task_completion,
                                "judge_tool_usage": judge_score.tool_usage,
                                "judge_reasoning": judge_score.reasoning,
                                "judge_answer_quality": judge_score.answer_quality,
                            })
                            score_source.append("judge")
                    except Exception as exc:
                        logger.error("[%s] LLM judge failed: %s", container_name, exc)

                _compute_final_score(scores, score_source, result)

            except subprocess.TimeoutExpired:
                result["error"] = f"Timeout after {timeout_seconds} seconds"
            except Exception as exc:
                logger.error("[%s] Execution error: %s", container_name, exc)
                result["error"] = str(exc)
            finally:
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

            # Save cache
            if result.get("status") == "success" and result.get("scores", {}).get("overall_score") is not None:
                dedup_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))

            return result

        # Execute tasks
        if parallel <= 1:
            for task in tasks:
                results.append(run_single_task_docker_nanobot(task, config["model"], force=force))
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {
                    pool.submit(run_single_task_docker_nanobot, task, config["model"], force): task["task_id"]
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
            "scored": len(valid_scores),
            "total": len(tasks),
            "details": results,
        }

    def collect(self, model_key: str) -> dict | None:
        """Collect results for a model from both native and docker_nanobot output directories.

        Native: wildclawbench/subset/{model_key}/{tid}.json
        Docker: wildclawbench/{model_key}/{task_id}/result.json
        """
        result_dir = self._find_result_dir("wildclawbench")
        if not result_dir:
            return None

        scores = []

        # Try native path first
        native_dir = result_dir / "subset" / model_key
        if native_dir.exists():
            scores = self._collect_from_native_dir(native_dir)

        # If native path has no results, try docker path (now at wildclawbench/{model_key})
        if not scores:
            docker_dir = result_dir / model_key
            if docker_dir.exists():
                scores = self._collect_from_docker_dir(docker_dir)

        if not scores:
            return None
        return {"score": round(sum(scores) / len(scores), 3), "scored": len(scores), "total": self.TASK_COUNT}

    def _collect_from_native_dir(self, out_dir: Path) -> list:
        """Collect scores from native mode output directory."""
        scores = []
        for f in out_dir.glob("*.json"):
            try:
                r = json.loads(f.read_text())
                s = r.get("scores", {}).get("overall_score") or r.get("judge_scores", {}).get("overall_score")
                if r.get("status") == "success" and s is not None:
                    scores.append(float(s))
            except Exception:
                pass
        return scores

    def _collect_from_docker_dir(self, docker_dir: Path) -> list:
        """Collect scores from docker_nanobot output directory.

        Unified structure: wildclawbench/{model_key}/{task_id}/result.json
        (created after successful grading in run_single_task_docker_nanobot).
        """
        scores = []
        # Collect from result.json files in each task directory
        for result_file in docker_dir.glob("*/result.json"):
            try:
                r = json.loads(result_file.read_text())
                s = r.get("scores", {}).get("overall_score")
                if r.get("status") == "success" and s is not None:
                    scores.append(float(s))
            except Exception:
                pass
        return scores

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
