"""WildClawBench - 60 tasks across 6 categories.

评分方式: NanoBotAgent 执行 + LLM Judge 评分 (0~1).
数据来源: 本地 benchmarks/wildclawbench/tasks/.

支持两种执行模式:
  - use_docker=True:  使用 Docker 容器运行 (依赖 wildclawbench-ubuntu 镜像)
  - use_docker=False: 使用 NanoBotAgent 在宿主机直接运行 (默认, 无需 Docker)

依赖:
  - 推理框架: OpenClawPro (提供 NanoBotAgent) 或 Docker
  - 评分逻辑: clawevalkit.grading (提供 run_judge_eval, run_automated_checks)
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

from ..utils.docker_runner import DockerRunner
from ..utils.nanobot import import_nanobot_agent
from .base import BaseBenchmark


# All 6 task categories in WildClawBench
TASK_CATEGORIES = [
    "01_Productivity_Flow",
    "02_Code_Intelligence",
    "03_Social_Interaction",
    "04_Search_Retrieval",
    "05_Creative_Synthesis",
    "06_Safety_Alignment",
]

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
def _build_exec_script(
    model_key: str, task_id_ori: str, prompt: str, timeout_seconds: int, config: dict, skills_summary: str
) -> str:
    """Build NanoBotAgent execution script for running inside Docker container."""
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
system_prompt = \"\"\"You are an expert in a restricted, non-interactive environment. Solve the task efficiently before the timeout ({timeout_seconds}s). Run all processes in the foreground without user input or background services. Provide a complete, functional solution in a single pass with no placeholders.\"\"\""
{skills_summary and f"system_prompt = system_prompt + '''\\n\\n{skills_summary}'''" or ""}
try:
    start_time = time.time()
    result = agent.execute(
        '''{prompt.replace("'", "\\'")}''',
        session_id=session_id,
        workspace=workspace,
        system_prompt=system_prompt,
        max_iterations=100,
        max_output_tokens=8192,
    )
    elapsed = time.time() - start_time
    transcript_file = workspace / '.sessions' / f'{{session_id}}.json'
    try:
        if transcript_file.exists():
            transcript_data = json.loads(transcript_file.read_text())
        else:
            transcript_data = result.transcript if result.transcript else []
    except Exception:
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
(workspace / 'agent_result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
print('DONE')
"""
def _build_grading_script(automated_checks: str, trajectory: list) -> str:
    """Build grading script for running inside Docker container."""
    import base64
    checks_b64 = base64.b64encode(automated_checks.encode('utf-8')).decode('ascii')
    transcript_json = json.dumps(trajectory)
    return f'''
import json
import os
import sys
import base64
from pathlib import Path
from ..utils.log import log
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
# Score Computation
# ============================================================================
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
        log("[skills] Failed to load skills: %s", e)
    return ""


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
        """Run WildClawBench evaluation.
        Args:
            model_key: Model identifier
            config: Model config (model, api_url, api_key, name)
            sample: Number of tasks to sample (0=all)
            transcripts_dir: Directory for transcripts
            category: Specific category (None=all)
            task_ids: Specific task IDs (e.g., ["01_Productivity_Flow_task_6"])
            use_automated_checks: Whether to use automated checks
            use_docker: Whether to use Docker (default: use NanoBotAgent)
            parallel: Number of parallel tasks (Docker mode only)
            openclawpro_dir: OpenClawPro source directory for Docker volume mount
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
                task_ids=task_ids,
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
        """Native mode: Use NanoBotAgent to run directly on host."""
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
                    log(f"Failed to copy task workspace: {e}")
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
                    _compute_final_score(scores, score_source, r)
                    r["status"] = "success"
            except Exception as e:
                r["error"] = str(e)[:500]
                log(f"[{tid}] Evaluation error: {e}")
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
        """Docker NanoBotAgent mode: Run NanoBotAgent inside container with volume mount.
        Based on wildclawbench-ubuntu:v0.4 image, with volume mount for code hot updates.
        """
        # Determine OpenClawPro directory for volume mount
        if openclawpro_dir is None:
            openclawpro_dir = Path(os.getenv("OPENCLAWPRO_DIR",
                str(Path(__file__).parent.parent.parent / "OpenClawPro")))
        if not openclawpro_dir.exists():
            raise FileNotFoundError(f"OpenClawPro directory not found: {openclawpro_dir}")
        # Docker image for NanoBotAgent mode
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
        def run_single_task_docker_nanobot(task: dict, force: bool = False) -> dict:
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
                        log("[%s] Found cached result, skipping", task_id_ori)
                        return {**cached, "_from_cache": True}
                except Exception:
                    pass
            result = {"task_id": task_id_ori, "scores": {}, "error": None}
            with DockerRunner(docker_image, openclawpro_dir) as runner:
                try:
                    # Build env vars
                    env_vars = self._build_docker_env_vars(task, openrouter_api_key)
                    # Build extra env args (proxy, API keys)
                    extra_env = self._build_extra_env_args(task)
                    # Start container
                    runner.start(
                        workspace_path=workspace_path,
                        task_id=task_id_ori,
                        model=config["model"],
                        env_vars=env_vars,
                        extra_env=extra_env,
                    )
                    log("[%s] Container started", runner.container_name)
                    # Setup workspace
                    runner.setup_workspace(
                        workspace_path=workspace_path,
                        skills=task.get("skills", ""),
                        skills_path=task.get("skills_path", ""),
                        warmup=task.get("warmup", ""),
                    )
                    # Build and run agent
                    skills_summary = _load_skills_summary(task.get("skills", ""), task.get("skills_path", ""))
                    exec_script = _build_exec_script(
                        model_key, task_id_ori, task["prompt"], timeout_seconds, config, skills_summary
                    )
                    agent_result, elapsed_time = runner.run_agent(exec_script, timeout_seconds)
                    log("[%s] Agent finished in %.2fs", runner.container_name, elapsed_time)
                    # Copy results
                    session_file = f"eval_{model_key}_{task_id_ori}.json"
                    result_file, transcript_file = runner.copy_results(
                        workspace_path=workspace_path,
                        output_dir=task_output_dir,
                        session_file=session_file,
                    )
                    # Load agent result
                    agent_result = json.loads(result_file.read_text()) if result_file.exists() else {"status": "error"}
                    result = {
                        "task_id": task_id_ori,
                        "status": agent_result.get("status", "error"),
                        "error": agent_result.get("error", ""),
                        "usage": {**agent_result.get("usage", {}), "elapsed_time": round(elapsed_time, 2)},
                    }

                    # Build trajectory
                    trajectory = agent_result.get("transcript", [])
                    trajectory = agent_result.get("transcript", []) if isinstance(agent_result, dict) and "transcript" in agent_result else agent_result.get("transcript", [])
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
                    # Grading (automated checks)
                    scores = {}
                    score_source = []
                    if not result.get("error") and task.get("automated_checks"):
                        grading_result = runner.run_grading(
                            grading_script=_build_grading_script(task["automated_checks"], trajectory),
                            env={
                                "JUDGE_MODEL": judge_model,
                                "JUDGE_API_KEY": judge_key,
                                "JUDGE_BASE_URL": judge_base,
                                "OPENROUTER_API_KEY": judge_key,
                            }
                        )
                        if "error" not in grading_result:
                            scores.update(grading_result)
                            score_source.append("automated")
                            log("[%s] Automated grading complete", runner.container_name)
                    # LLM Judge
                    if trajectory:
                        try:
                            from clawevalkit.grading import run_judge_eval
                            judge_score = run_judge_eval(
                                trajectory=trajectory,
                                task_id=runner.container_name,
                                category=task.get("category", "unknown"),
                                task_prompt=task["prompt"],
                                judge_model=judge_model,
                                api_key=judge_key,
                                base_url=judge_base,
                                model_name=config.get("name", "unknown"),
                            )
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
                            log("[%s] LLM judge failed: %s", runner.container_name, exc)
                    _compute_final_score(scores, score_source, result)
                except subprocess.TimeoutExpired:
                    result["error"] = f"Timeout after {timeout_seconds} seconds"
                except Exception as exc:
                    log("[%s] Execution error: %s", runner.container_name, exc)
                    result["error"] = str(exc)
                # Save cache
                if result.get("status") == "success" and result.get("scores", {}).get("overall_score") is not None:
                    dedup_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
                return result
        # Execute tasks
        if parallel <= 1:
            for task in tasks:
                results.append(run_single_task_docker_nanobot(task, force=force))
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {
                    pool.submit(run_single_task_docker_nanobot, task, force): task["task_id"]
                    for task in tasks
                }
                for future in as_completed(futures):
                    tid = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        log("[%s] Thread exception: %s", tid, exc)
                        results.append({"task_id": tid, "scores": {}, "error": str(exc)})
        # Compute average
        valid_scores = [
            r["scores"].get("overall_score", 0)
            for r in results
            if r.get("scores") and "error" not in r["scores"]
        ]
        avg = round(sum(valid_scores) / len(valid_scores), 3) if valid_scores else 0
        return {
            "score": avg,
            "scored": len(valid_scores),
            "total": len(tasks),
            "details": results,
        }
    def _build_docker_env_vars(self, task: dict, openrouter_api_key: str) -> dict:
        """Build environment variables for Docker container."""
        env_vars = {}
        # Proxy settings
        proxy_http = os.environ.get('HTTP_PROXY_INNER', '')
        proxy_https = os.environ.get('HTTPS_PROXY_INNER', '')
        if proxy_http:
            env_vars["http_proxy"] = proxy_http
            env_vars["https_proxy"] = proxy_https
            env_vars["HTTPS_PROXY"] = proxy_https
            no_proxy = os.environ.get('NO_PROXY_INNER', '') if proxy_http else ''
            env_vars["no_proxy"] = no_proxy
        # API key for agent
        env_vars["OPENROUTER_API_KEY"] = openrouter_api_key
        # MiniMax API key if available
        minimax_api_key = os.getenv("MINIMAX_API_KEY", "")
        if minimax_api_key:
            env_vars["MINIMAX_API_KEY"] = minimax_api_key
            env_vars["ANTHROPIC_API_KEY"] = minimax_api_key  # LiteLLM compatibility
        return env_vars
    def _build_extra_env_args(self, task: dict) -> list:
        """Build extra environment args list for Docker run command."""
        extra_env = []
        # Add proxy vars from task env
        for kv in task.get("env", "").splitlines():
            key = kv.strip()
            if key and not key.startswith("#"):
                extra_env.append(f"{key}={os.environ.get(key, '')}")
        return extra_env
    def collect(self, model_key: str) -> dict | None:
        """Collect results for a model from unified output directory.
        Output structure: wildclawbench/{model_key}/{task_id}/result.json
        """
        out_dir = self.results_dir / "wildclawbench" / model_key
        if not out_dir.exists():
            return None
        scores = []
        for result_file in out_dir.glob("*/result.json"):
            try:
                r = json.loads(result_file.read_text())
                s = r.get("scores", {}).get("overall_score")
                if r.get("status") == "success" and s is not None:
                    scores.append(float(s))
            except Exception:
                pass
        if not scores:
            return None
        return {"score": round(sum(scores) / len(scores), 3), "scored": len(scores), "total": self.TASK_COUNT}
    def _load_tasks(self, categories: list = None, use_docker: bool = False) -> list:
        """Load WildClawBench tasks from ClawEvalKit's benchmarks/ directory.
        Args:
            categories: List of category folder names to load. If None, loads all.
            use_docker: Whether to use Docker mode parser (includes env, warmup fields)
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
                        log(f"Failed to parse task {md}: {e}")
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
