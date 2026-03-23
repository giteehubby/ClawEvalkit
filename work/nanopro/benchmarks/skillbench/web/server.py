#!/usr/bin/env python3
"""
SkillBench Upload Server (v1)

Upload → job → profile flow with database persistence and rate limiting.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from functools import wraps

# Ensure harness module is importable
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, request, jsonify, send_from_directory, redirect, url_for
from harness.database import (
    create_job as db_create_job,
    get_job as db_get_job,
    update_job as db_update_job,
    check_rate_limit,
    Job,
)

app = Flask(__name__, static_folder="static")

# Configuration
# Use RAILWAY_VOLUME_MOUNT_PATH for persistent storage if available
PERSISTENT_ROOT = pathlib.Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", str(REPO_ROOT / "web")))
OUTPUTS_DIR = PERSISTENT_ROOT / "outputs"
UPLOADS_DIR = PERSISTENT_ROOT / "uploads"
TRACES_DIR = PERSISTENT_ROOT / "traces"

# Rate limiting config
RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("SKILLBENCH_RATE_LIMIT", "10"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("SKILLBENCH_RATE_WINDOW", "3600"))

# Hosted execution config
HOSTED_MODE = os.environ.get("SKILLBENCH_HOSTED_MODE", "true").lower() == "true"
MAX_COST_PER_JOB_USD = float(os.environ.get("SKILLBENCH_MAX_COST_PER_JOB", "1.0"))

# Cost estimation (Claude Sonnet pricing as of 2024)
COST_PER_INPUT_TOKEN = 3.0 / 1_000_000   # $3 per 1M input tokens
COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000  # $15 per 1M output tokens

# Ensure directories exist
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
TRACES_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Rate Limiting Decorator
# =============================================================================

def rate_limited(f):
    """Decorator to apply rate limiting to upload endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get client IP (handle proxies)
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if ip:
            ip = ip.split(",")[0].strip()

        status = check_rate_limit(
            ip,
            max_requests=RATE_LIMIT_MAX_REQUESTS,
            window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        )

        if not status.allowed:
            response = jsonify({
                "error": "Rate limit exceeded",
                "retry_after_seconds": status.retry_after_seconds,
                "reset_at": status.reset_at,
            })
            response.status_code = 429
            response.headers["Retry-After"] = str(status.retry_after_seconds)
            response.headers["X-RateLimit-Remaining"] = "0"
            response.headers["X-RateLimit-Reset"] = status.reset_at
            return response

        # Add rate limit headers to all responses
        result = f(*args, **kwargs)

        # Handle both Response objects and (response, status_code) tuples
        if isinstance(result, tuple):
            response = app.make_response(result)
        elif hasattr(result, "headers"):
            response = result
        else:
            response = app.make_response(result)

        response.headers["X-RateLimit-Remaining"] = str(status.remaining)
        response.headers["X-RateLimit-Reset"] = status.reset_at
        return response

    return decorated_function


# =============================================================================
# Job Helpers (wrapping database layer)
# =============================================================================

def compute_skill_digest(skill_path: pathlib.Path) -> str:
    """Compute SHA256 digest of skill content."""
    if skill_path.is_file():
        content = skill_path.read_bytes()
    elif skill_path.is_dir():
        # Hash all files in directory
        parts = []
        for f in sorted(skill_path.rglob("*")):
            if f.is_file():
                parts.append(f"{f.relative_to(skill_path)}:{hashlib.sha256(f.read_bytes()).hexdigest()}")
        content = "\n".join(parts).encode()
    else:
        content = b""
    return hashlib.sha256(content).hexdigest()


def create_job(skill_path: pathlib.Path) -> str:
    """Create a new job with skill digest."""
    job_id = str(uuid.uuid4())[:8]
    skill_digest = compute_skill_digest(skill_path)
    suite_seed = random.randint(100000, 999999)

    db_create_job(
        job_id=job_id,
        skill_path=str(skill_path),
        skill_digest=skill_digest,
        suite_id="core-bugfix",
        suite_version="1.0.0",
        suite_seed=suite_seed,
    )
    return job_id


def update_job(job_id: str, **kwargs) -> None:
    """Update job fields."""
    db_update_job(job_id, **kwargs)


def get_job(job_id: str) -> dict | None:
    """Get job as dictionary for API responses."""
    job = db_get_job(job_id)
    if job:
        return job.to_dict()
    return None


def _aggregate_traces(report_data: dict) -> dict:
    """Aggregate execution traces from task results."""
    from harness.suite_integrity import detect_shortcutting

    traces = {
        "schema_version": "1.0.0",
        "tasks": [],
        "integrity": {
            "shortcut_warnings": [],
        },
        "usage": {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "estimated_cost_usd": 0.0,
        },
    }

    total_input_tokens = 0
    total_output_tokens = 0

    for section in ["baseline", "augmented"]:
        section_data = report_data.get(section, {})
        tasks = section_data.get("tasks", [])
        for task in tasks:
            result = task.get("result", {})
            trace_path = result.get("trace_path")

            task_trace = {
                "task_id": task.get("task_id"),
                "mode": section,
                "status": result.get("status"),
                "runtime_s": result.get("runtime_s"),
                "tool_calls": [],
            }

            # If there's a trace file, read it
            if trace_path:
                try:
                    trace_file = pathlib.Path(trace_path)
                    if trace_file.exists():
                        trace_data = json.loads(trace_file.read_text())
                        task_trace["tool_calls"] = trace_data.get("traces", [])
                        task_trace["steps"] = trace_data.get("steps")
                        task_trace["total_tool_calls"] = trace_data.get("tool_calls")
                        task_trace["files_modified"] = trace_data.get("files_modified")
                        task_trace["done_summary"] = trace_data.get("done_summary")

                        # Collect token usage
                        task_trace["input_tokens"] = trace_data.get("input_tokens", 0)
                        task_trace["output_tokens"] = trace_data.get("output_tokens", 0)
                        total_input_tokens += task_trace["input_tokens"]
                        total_output_tokens += task_trace["output_tokens"]

                        # Run shortcut detection on augmented mode traces
                        if section == "augmented":
                            issues = detect_shortcutting(trace_data.get("traces", []))
                            if issues:
                                task_trace["integrity_issues"] = issues
                                traces["integrity"]["shortcut_warnings"].extend([
                                    {
                                        "task_id": task.get("task_id"),
                                        **issue,
                                    }
                                    for issue in issues
                                ])
                except Exception:
                    pass

            traces["tasks"].append(task_trace)

    # Calculate total usage and cost
    traces["usage"]["total_input_tokens"] = total_input_tokens
    traces["usage"]["total_output_tokens"] = total_output_tokens
    traces["usage"]["estimated_cost_usd"] = round(
        total_input_tokens * COST_PER_INPUT_TOKEN +
        total_output_tokens * COST_PER_OUTPUT_TOKEN,
        4
    )

    return traces


# Background job runner
def run_evaluation(job_id: str):
    """Run the evaluation pipeline in background."""
    job = get_job(job_id)
    if not job:
        return

    update_job(job_id, status="running", stage="loading", progress=5)
    skill_path = pathlib.Path(job["skill_path"])

    try:
        # Stage 1: Loading skill
        time.sleep(0.3)  # Brief pause for UX
        update_job(job_id, stage="loading", progress=10)

        # Create temp directory for report
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = pathlib.Path(tmpdir) / "report.json"

            # Stage 2: Running tasks
            update_job(job_id, stage="running", progress=20)

            # Run the benchmark
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT)
            env["SKILLBENCH_AGENT_MODEL"] = "claude-sonnet-4-20250514"

            # Use agentic adapter if API key available, otherwise mock
            has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
            agent_type = "agentic" if has_api_key else "mock"

            # Agentic adapter settings (reduced limits for hosted mode)
            if has_api_key:
                env["SKILLBENCH_AGENT_MAX_STEPS"] = "10"
                env["SKILLBENCH_AGENT_MAX_TOOL_CALLS"] = "30"
                env["SKILLBENCH_AGENT_MAX_WALL_TIME"] = "60"  # 1 minute per task
                env["SKILLBENCH_AGENT_TEMPERATURE"] = "0.0"

            cmd = [
                "python3", "-m", "harness.cli",
                "run",
                "--pack", "coding/swe-lite",
                "--runner", "local",
                "--agent", agent_type,
                "--mode", "both",
                "--skill", str(skill_path),
                "--output", str(report_path),
                "--include-skill-body",
            ]

            result = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minutes for full benchmark
            )

            update_job(job_id, progress=70)

            if result.returncode != 0:
                raise RuntimeError(f"Benchmark failed: {result.stderr[:500]}")

            if not report_path.exists():
                raise RuntimeError("Report not generated")

            # Stage 3: Generating profile
            update_job(job_id, stage="generating", progress=80)

            slug = f"{job_id}"
            output_dir = OUTPUTS_DIR / slug
            output_dir.mkdir(parents=True, exist_ok=True)

            # Aggregate traces from task results
            report_data = json.loads(report_path.read_text())
            traces = _aggregate_traces(report_data)
            trace_file = output_dir / "traces.json"
            trace_file.write_text(json.dumps(traces, indent=2), encoding="utf-8")

            # Extract usage for cost tracking
            usage = traces.get("usage", {})
            input_tokens = usage.get("total_input_tokens", 0)
            output_tokens = usage.get("total_output_tokens", 0)
            estimated_cost = usage.get("estimated_cost_usd", 0.0)

            # Pass skill digest for artifact signing
            skill_digest = job.get("skill_digest")
            if skill_digest:
                env["SKILLBENCH_SKILL_DIGEST"] = skill_digest

            gen_cmd = [
                "python3", "-m", "harness.generate_profile",
                str(report_path),
                "--output-dir", str(output_dir),
                "--scorecard-url", f"/s/{slug}",
                "--traces-url", f"/t/{slug}",
            ]

            gen_result = subprocess.run(
                gen_cmd,
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if gen_result.returncode != 0:
                raise RuntimeError(f"Profile generation failed: {gen_result.stderr[:500]}")

            # Find the generated files
            html_files = list(output_dir.glob("*-profile.html"))
            json_files = list(output_dir.glob("*-scorecard.json"))

            if not html_files:
                raise RuntimeError("Profile HTML not generated")

            update_job(
                job_id,
                status="complete",
                stage="complete",
                progress=100,
                output_slug=slug,
                trace_path=str(trace_file),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost,
            )

    except Exception as e:
        update_job(
            job_id,
            status="failed",
            stage="failed",
            error_message=str(e)[:500],
        )


# Routes

@app.route("/")
def landing():
    """Landing page with upload drop zone."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SkillBench</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #fafafa;
      color: #1a1a1a;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }
    .container {
      max-width: 480px;
      width: 100%;
      text-align: center;
    }
    h1 {
      font-size: 1.5rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
    }
    .subtitle {
      color: #666;
      margin-bottom: 2rem;
    }
    .dropzone {
      border: 2px dashed #d0d0d0;
      border-radius: 12px;
      padding: 3rem 2rem;
      background: white;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .dropzone:hover, .dropzone.dragover {
      border-color: #666;
      background: #f5f5f5;
    }
    .dropzone-icon {
      font-size: 2.5rem;
      margin-bottom: 1rem;
    }
    .dropzone-text {
      font-size: 1rem;
      color: #333;
      margin-bottom: 0.5rem;
    }
    .dropzone-hint {
      font-size: 0.75rem;
      color: #999;
    }
    input[type="file"] {
      display: none;
    }
    .example-link {
      margin-top: 1.5rem;
      font-size: 0.875rem;
    }
    .example-link a {
      color: #666;
      text-decoration: none;
    }
    .example-link a:hover {
      color: #333;
      text-decoration: underline;
    }
    .error {
      margin-top: 1rem;
      padding: 0.75rem 1rem;
      background: #fee2e2;
      border-radius: 6px;
      color: #991b1b;
      font-size: 0.875rem;
      display: none;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Upload your skill to see how it behaves</h1>
    <p class="subtitle">We'll run it through a few scenarios and show you what it does.</p>

    <div class="dropzone" id="dropzone" onclick="document.getElementById('fileInput').click()">
      <div class="dropzone-icon">📦</div>
      <div class="dropzone-text">Drop your skill here</div>
      <div class="dropzone-hint">SKILL.md or .zip directory</div>
    </div>

    <input type="file" id="fileInput" accept=".md,.zip" />

    <div class="error" id="error"></div>

    <div class="example-link">
      <a href="/example">Or try an example →</a>
    </div>
  </div>

  <script>
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const errorDiv = document.getElementById('error');

    function showError(msg) {
      errorDiv.textContent = msg;
      errorDiv.style.display = 'block';
    }

    function hideError() {
      errorDiv.style.display = 'none';
    }

    async function uploadFile(file) {
      hideError();
      const formData = new FormData();
      formData.append('skill', file);

      try {
        const response = await fetch('/upload', {
          method: 'POST',
          body: formData
        });

        const data = await response.json();

        if (data.error) {
          showError(data.error);
          return;
        }

        if (data.job_id) {
          window.location.href = '/job/' + data.job_id;
        }
      } catch (e) {
        showError('Upload failed. Please try again.');
      }
    }

    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
      dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      const file = e.dataTransfer.files[0];
      if (file) uploadFile(file);
    });

    fileInput.addEventListener('change', () => {
      const file = fileInput.files[0];
      if (file) uploadFile(file);
    });
  </script>
</body>
</html>"""


@app.route("/upload", methods=["POST"])
@rate_limited
def upload():
    """Handle skill upload."""
    if "skill" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["skill"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    # Validate file type
    filename = file.filename.lower()
    if not (filename.endswith(".md") or filename.endswith(".zip")):
        return jsonify({"error": "Please upload a SKILL.md or .zip file"}), 400

    # Save to uploads directory
    upload_id = str(uuid.uuid4())[:8]
    upload_dir = UPLOADS_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    if filename.endswith(".zip"):
        # Extract zip
        zip_path = upload_dir / "skill.zip"
        file.save(zip_path)
        shutil.unpack_archive(zip_path, upload_dir / "skill")
        skill_path = upload_dir / "skill"
        # Find SKILL.md in extracted directory
        skill_md = list(skill_path.rglob("SKILL.md"))
        if skill_md:
            skill_path = skill_md[0].parent
    else:
        # Single SKILL.md file
        skill_dir = upload_dir / "skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        file.save(skill_dir / "SKILL.md")
        skill_path = skill_dir

    # Create job
    job_id = create_job(skill_path)

    # Start background evaluation
    thread = threading.Thread(target=run_evaluation, args=(job_id,))
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/example")
@rate_limited
def example():
    """Run with example skill."""
    example_skill = REPO_ROOT / "packs" / "coding" / "swe-lite" / "skills" / "calc-fixer"
    if not example_skill.exists():
        return jsonify({"error": "Example skill not found"}), 500

    job_id = create_job(example_skill)
    thread = threading.Thread(target=run_evaluation, args=(job_id,))
    thread.start()

    return redirect(url_for("job_status", job_id=job_id))


@app.route("/job/<job_id>")
def job_status(job_id: str):
    """Job status / running page."""
    job = get_job(job_id)
    if not job:
        return "Job not found", 404

    if job["status"] == "complete":
        # Redirect to profile
        return redirect(url_for("profile", slug=job["output_slug"]))

    if job["status"] == "failed":
        debug_info = f"""Job ID: {job_id}
Suite: {job.get('suite_id', 'core-bugfix')} v{job.get('suite_version', '1.0.0')}
Runner: v{job.get('runner_version', '0.1.0')}
Stage: {job.get('stage', 'unknown')}
Error: {job.get('error_message', 'Unknown error')}"""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Evaluation Failed</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #fafafa;
      color: #1a1a1a;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }}
    .container {{
      max-width: 480px;
      width: 100%;
      text-align: center;
    }}
    h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
    .subtitle {{ color: #666; margin-bottom: 1.5rem; font-size: 0.875rem; }}
    .error-box {{
      background: #fee2e2;
      border-radius: 8px;
      padding: 1rem;
      margin-bottom: 1.5rem;
      text-align: left;
    }}
    .error-label {{
      font-size: 0.75rem;
      color: #991b1b;
      text-transform: uppercase;
      margin-bottom: 0.5rem;
    }}
    .error-message {{
      font-size: 0.875rem;
      color: #7f1d1d;
      font-family: monospace;
      word-break: break-all;
    }}
    .actions {{
      display: flex;
      gap: 0.75rem;
      justify-content: center;
      margin-bottom: 1.5rem;
    }}
    .btn {{
      display: inline-block;
      padding: 0.75rem 1.5rem;
      border-radius: 6px;
      font-size: 0.875rem;
      text-decoration: none;
      cursor: pointer;
      border: none;
    }}
    .btn-primary {{
      background: #1a1a1a;
      color: white;
    }}
    .btn-primary:hover {{ background: #333; }}
    .btn-secondary {{
      background: white;
      color: #333;
      border: 1px solid #ddd;
    }}
    .btn-secondary:hover {{ background: #f5f5f5; }}
    .debug-info {{
      margin-top: 1rem;
      text-align: left;
    }}
    .debug-toggle {{
      font-size: 0.75rem;
      color: #666;
      cursor: pointer;
    }}
    .debug-content {{
      display: none;
      margin-top: 0.5rem;
      padding: 0.75rem;
      background: #f5f5f5;
      border-radius: 6px;
      font-family: monospace;
      font-size: 0.7rem;
      white-space: pre-wrap;
      color: #555;
    }}
    .debug-content.open {{ display: block; }}
    .copied {{ color: #16a34a !important; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Something went wrong</h1>
    <p class="subtitle">The evaluation couldn't complete.</p>
    <div class="error-box">
      <div class="error-label">Error</div>
      <div class="error-message">{job.get('error_message', 'Unknown error')}</div>
    </div>
    <div class="actions">
      <a href="/" class="btn btn-primary">Try again</a>
      <button class="btn btn-secondary" onclick="copyDebug()">Copy debug info</button>
    </div>
    <div class="debug-info">
      <span class="debug-toggle" onclick="toggleDebug()">Show debug details &#9662;</span>
      <div id="debug-content" class="debug-content">{debug_info}</div>
    </div>
  </div>
  <script>
    const debugInfo = `{debug_info}`;
    function toggleDebug() {{
      document.getElementById('debug-content').classList.toggle('open');
    }}
    function copyDebug() {{
      navigator.clipboard.writeText(debugInfo);
      const btn = document.querySelector('.btn-secondary');
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {{
        btn.textContent = 'Copy debug info';
        btn.classList.remove('copied');
      }}, 2000);
    }}
  </script>
</body>
</html>"""

    # Running state - show stages
    stage = job.get('stage', 'loading')
    progress = job.get('progress', 0)
    stage_labels = {
        'loading': 'Loading skill...',
        'running': 'Running tasks...',
        'generating': 'Generating profile...',
    }
    stage_label = stage_labels.get(stage, 'Processing...')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Running evaluation...</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #fafafa;
      color: #1a1a1a;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }}
    .container {{
      max-width: 480px;
      width: 100%;
      text-align: center;
    }}
    .progress-ring {{
      width: 64px;
      height: 64px;
      margin: 0 auto 1.5rem;
      position: relative;
    }}
    .progress-ring svg {{
      transform: rotate(-90deg);
    }}
    .progress-ring circle {{
      fill: none;
      stroke-width: 4;
    }}
    .progress-ring .bg {{
      stroke: #e5e5e5;
    }}
    .progress-ring .fg {{
      stroke: #1a1a1a;
      stroke-linecap: round;
      transition: stroke-dashoffset 0.5s ease;
    }}
    .progress-text {{
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      font-size: 0.75rem;
      font-weight: 600;
      color: #333;
    }}
    h1 {{ font-size: 1rem; margin-bottom: 0.25rem; color: #333; }}
    .stage {{ color: #666; font-size: 0.875rem; margin-bottom: 1.5rem; }}
    .suite-info {{
      font-size: 0.75rem;
      color: #999;
      margin-bottom: 2rem;
    }}
    .stages {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      text-align: left;
      background: white;
      border: 1px solid #e5e5e5;
      border-radius: 8px;
      padding: 1rem;
    }}
    .stage-item {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-size: 0.8rem;
      color: #999;
    }}
    .stage-item.active {{
      color: #1a1a1a;
      font-weight: 500;
    }}
    .stage-item.done {{
      color: #16a34a;
    }}
    .stage-dot {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #ddd;
      flex-shrink: 0;
    }}
    .stage-item.active .stage-dot {{
      background: #1a1a1a;
      animation: pulse 1.5s ease infinite;
    }}
    .stage-item.done .stage-dot {{
      background: #16a34a;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.5; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="progress-ring">
      <svg width="64" height="64">
        <circle class="bg" cx="32" cy="32" r="28"></circle>
        <circle class="fg" cx="32" cy="32" r="28"
          stroke-dasharray="176"
          stroke-dashoffset="{176 - (176 * progress / 100)}"></circle>
      </svg>
      <span class="progress-text" id="progress">{progress}%</span>
    </div>
    <h1>Running your skill against Core Bugfix Suite v1</h1>
    <p class="suite-info">10 tasks across arithmetic, string, and validation bugs</p>

    <div class="stages">
      <div class="stage-item {'done' if stage in ['running', 'generating'] else 'active' if stage == 'loading' else ''}">
        <span class="stage-dot"></span>
        <span>Loading skill</span>
      </div>
      <div class="stage-item {'done' if stage == 'generating' else 'active' if stage == 'running' else ''}">
        <span class="stage-dot"></span>
        <span>Running tasks</span>
      </div>
      <div class="stage-item {'active' if stage == 'generating' else ''}">
        <span class="stage-dot"></span>
        <span>Generating profile</span>
      </div>
    </div>
  </div>

  <script>
    // Poll for updates
    setInterval(async () => {{
      const response = await fetch('/api/job/{job_id}');
      const data = await response.json();

      if (data.status === 'complete') {{
        window.location.href = '/p/' + data.output_slug;
      }} else if (data.status === 'failed') {{
        window.location.reload();
      }} else {{
        // Update progress
        document.getElementById('progress').textContent = data.progress + '%';
        const circle = document.querySelector('.progress-ring .fg');
        circle.style.strokeDashoffset = 176 - (176 * data.progress / 100);

        // Update stages
        const stages = document.querySelectorAll('.stage-item');
        stages[0].className = 'stage-item ' + (
          ['running', 'generating'].includes(data.stage) ? 'done' :
          data.stage === 'loading' ? 'active' : ''
        );
        stages[1].className = 'stage-item ' + (
          data.stage === 'generating' ? 'done' :
          data.stage === 'running' ? 'active' : ''
        );
        stages[2].className = 'stage-item ' + (
          data.stage === 'generating' ? 'active' : ''
        );
      }}
    }}, 1000);
  </script>
</body>
</html>"""


@app.route("/api/job/<job_id>")
def api_job_status(job_id: str):
    """API endpoint for job status polling."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/p/<slug>")
def profile(slug: str):
    """Serve profile HTML with cache headers."""
    output_dir = OUTPUTS_DIR / slug
    if not output_dir.exists():
        return "Profile not found", 404

    html_files = list(output_dir.glob("*-profile.html"))
    if not html_files:
        return "Profile not found", 404

    # Read file for ETag
    content = html_files[0].read_bytes()
    etag = hashlib.sha256(content).hexdigest()[:16]

    response = send_from_directory(output_dir, html_files[0].name)
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    response.headers['ETag'] = f'"{etag}"'
    return response


@app.route("/s/<slug>")
def scorecard(slug: str):
    """Serve scorecard JSON with cache headers."""
    output_dir = OUTPUTS_DIR / slug
    if not output_dir.exists():
        return jsonify({"error": "Scorecard not found"}), 404

    json_files = list(output_dir.glob("*-scorecard.json"))
    if not json_files:
        return jsonify({"error": "Scorecard not found"}), 404

    # Read file for ETag
    content = json_files[0].read_bytes()
    etag = hashlib.sha256(content).hexdigest()[:16]

    response = send_from_directory(output_dir, json_files[0].name)
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    response.headers['ETag'] = f'"{etag}"'
    response.headers['Content-Type'] = 'application/json'
    return response


@app.route("/t/<slug>")
def traces(slug: str):
    """Serve execution traces JSON with cache headers."""
    output_dir = OUTPUTS_DIR / slug
    if not output_dir.exists():
        return jsonify({"error": "Traces not found"}), 404

    trace_file = output_dir / "traces.json"
    if not trace_file.exists():
        return jsonify({"error": "Traces not found"}), 404

    # Read file for ETag
    content = trace_file.read_bytes()
    etag = hashlib.sha256(content).hexdigest()[:16]

    response = send_from_directory(output_dir, "traces.json")
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    response.headers['ETag'] = f'"{etag}"'
    response.headers['Content-Type'] = 'application/json'
    return response


@app.route("/.well-known/keys.json")
def well_known_keys():
    """Public keys for scorecard signature verification."""
    from harness.signing import get_well_known_keys
    return jsonify(get_well_known_keys())


@app.route("/verify/<slug>")
def verify_scorecard(slug: str):
    """Verify scorecard signature and return verification summary."""
    output_dir = OUTPUTS_DIR / slug
    if not output_dir.exists():
        return jsonify({"error": "Scorecard not found", "valid": False}), 404

    json_files = list(output_dir.glob("*-scorecard.json"))
    if not json_files:
        return jsonify({"error": "Scorecard not found", "valid": False}), 404

    scorecard_data = json.loads(json_files[0].read_text())

    # Verify signature
    from harness.signing import verify_signature, compute_payload_digest

    signature = scorecard_data.get("signature")
    if not signature:
        return jsonify({
            "valid": False,
            "error": "No signature present",
            "scorecard_url": f"/s/{slug}",
        })

    is_valid, message = verify_signature(scorecard_data)

    return jsonify({
        "valid": is_valid,
        "message": message,
        "key_id": signature.get("key_id"),
        "algorithm": signature.get("algorithm"),
        "signed_at": signature.get("signed_at"),
        "payload_digest": signature.get("payload_digest"),
        "suite": {
            "id": scorecard_data.get("suite", {}).get("id"),
            "version": scorecard_data.get("suite", {}).get("version"),
            "seed": scorecard_data.get("suite", {}).get("seed"),
        },
        "run": {
            "runner_version": scorecard_data.get("run", {}).get("runner_version"),
            "adapter": scorecard_data.get("run", {}).get("adapter"),
            "agent_model_id": scorecard_data.get("run", {}).get("agent_model_id"),
            "config_digest": scorecard_data.get("run", {}).get("config_digest"),
        },
        "scorecard_url": f"/s/{slug}",
        "keys_url": "/.well-known/keys.json",
    })


@app.route("/embed/<slug>")
def embed_widget(slug: str):
    """Embeddable widget for marketplaces."""
    output_dir = OUTPUTS_DIR / slug
    if not output_dir.exists():
        return "Not found", 404

    json_files = list(output_dir.glob("*-scorecard.json"))
    if not json_files:
        return "Not found", 404

    scorecard_data = json.loads(json_files[0].read_text())

    # Extract display data
    skill_name = scorecard_data.get("skill", {}).get("name", "Unknown Skill")
    headline = scorecard_data.get("summary", {}).get("headline", "")
    metrics = scorecard_data.get("metrics", {})
    signature = scorecard_data.get("signature")

    reliability = metrics.get("reliability", {})
    efficiency = metrics.get("efficiency", {})

    rel_delta = reliability.get("delta", 0) or 0
    rel_str = f"+{int(rel_delta * 100)}%" if rel_delta > 0 else ("no change" if rel_delta == 0 else f"{int(rel_delta * 100)}%")
    rel_class = "positive" if rel_delta > 0 else ("negative" if rel_delta < 0 else "neutral")

    eff_delta = efficiency.get("delta_ms", 0) or 0
    eff_str = "no change" if abs(eff_delta) < 1 else (f"{int(eff_delta)}ms faster" if eff_delta < 0 else f"+{int(eff_delta)}ms")
    eff_class = "positive" if eff_delta < 0 else ("negative" if eff_delta > 0 else "neutral")

    suite_info = scorecard_data.get("suite", {})
    run_info = scorecard_data.get("run", {})

    verified_badge = '<span class="verified">Verified by SkillBench</span>' if signature else ''

    # Build micro-line for legitimacy
    micro_line_parts = []
    if signature:
        micro_line_parts.append("Signed")
    micro_line_parts.append(f"Suite: {suite_info.get('id', 'unknown')} v{suite_info.get('version', '?')}")
    micro_line_parts.append(f"Runner: {run_info.get('runner_version', '?')}")
    micro_line = " · ".join(micro_line_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{skill_name} - SkillBench</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: transparent;
      color: #1a1a1a;
      line-height: 1.5;
    }}
    .card {{
      background: white;
      border: 1px solid #e5e5e5;
      border-radius: 12px;
      padding: 1.25rem;
      max-width: 320px;
    }}
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.75rem;
    }}
    .skill-name {{
      font-size: 1rem;
      font-weight: 600;
    }}
    .verified {{
      font-size: 0.625rem;
      background: #dcfce7;
      color: #166534;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      font-weight: 600;
      text-transform: uppercase;
    }}
    .headline {{
      font-size: 0.8rem;
      color: #666;
      margin-bottom: 1rem;
      line-height: 1.4;
    }}
    .metrics {{
      display: flex;
      flex-direction: column;
      gap: 0.625rem;
      margin-bottom: 1rem;
    }}
    .metric {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}
    .metric-label {{
      font-size: 0.75rem;
      color: #666;
      width: 70px;
    }}
    .metric-bar {{
      flex: 1;
      height: 6px;
      background: #e5e5e5;
      border-radius: 3px;
      overflow: hidden;
    }}
    .metric-fill {{
      height: 100%;
      border-radius: 3px;
    }}
    .metric-fill.positive {{ background: #22c55e; }}
    .metric-fill.neutral {{ background: #a3a3a3; }}
    .metric-fill.negative {{ background: #ef4444; }}
    .metric-value {{
      font-size: 0.7rem;
      font-weight: 600;
      width: 65px;
      text-align: right;
    }}
    .metric-value.positive {{ color: #16a34a; }}
    .metric-value.neutral {{ color: #666; }}
    .metric-value.negative {{ color: #dc2626; }}
    .footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 0.75rem;
      border-top: 1px solid #f0f0f0;
    }}
    .suite {{
      font-size: 0.65rem;
      color: #999;
    }}
    .view-link {{
      font-size: 0.7rem;
      color: #666;
      text-decoration: none;
    }}
    .view-link:hover {{
      color: #1a1a1a;
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <span class="skill-name">{skill_name}</span>
      {verified_badge}
    </div>
    <p class="headline">{headline[:120]}{'...' if len(headline) > 120 else ''}</p>
    <div class="metrics">
      <div class="metric">
        <span class="metric-label">Reliability</span>
        <div class="metric-bar">
          <div class="metric-fill {rel_class}" style="width: {min(100, max(10, 50 + rel_delta * 100))}%"></div>
        </div>
        <span class="metric-value {rel_class}">{rel_str}</span>
      </div>
      <div class="metric">
        <span class="metric-label">Efficiency</span>
        <div class="metric-bar">
          <div class="metric-fill {eff_class}" style="width: 50%"></div>
        </div>
        <span class="metric-value {eff_class}">{eff_str}</span>
      </div>
    </div>
    <div class="footer">
      <span class="suite">{micro_line}</span>
      <a href="/p/{slug}" class="view-link" target="_blank">View full profile &rarr;</a>
    </div>
  </div>
</body>
</html>"""


@app.route("/embed/<slug>.js")
def embed_script(slug: str):
    """JavaScript embed snippet for marketplaces."""
    script = f'''(function() {{
  var iframe = document.createElement('iframe');
  iframe.src = '{request.host_url}embed/{slug}';
  iframe.style.border = 'none';
  iframe.style.width = '340px';
  iframe.style.height = '220px';
  iframe.style.borderRadius = '12px';
  iframe.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
  var container = document.currentScript.parentElement;
  container.appendChild(iframe);
}})();'''
    response = app.response_class(script, mimetype='application/javascript')
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


@app.route("/api/status")
def api_status():
    """API status and health check endpoint."""
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    return jsonify({
        "status": "ok",
        "hosted_mode": HOSTED_MODE,
        "api_available": has_api_key,
        "agent_type": "agentic" if has_api_key else "mock",
        "rate_limit": {
            "max_requests": RATE_LIMIT_MAX_REQUESTS,
            "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
        },
        "cost_limits": {
            "max_per_job_usd": MAX_COST_PER_JOB_USD,
            "input_token_cost": COST_PER_INPUT_TOKEN,
            "output_token_cost": COST_PER_OUTPUT_TOKEN,
        },
        "version": "0.2.0",
    })


@app.route("/api/usage/<job_id>")
def api_job_usage(job_id: str):
    """Get usage/cost details for a job."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": job_id,
        "status": job.get("status"),
        "input_tokens": job.get("input_tokens", 0),
        "output_tokens": job.get("output_tokens", 0),
        "estimated_cost_usd": job.get("estimated_cost_usd", 0.0),
        "execution_mode": job.get("execution_mode", "hosted"),
    })


if __name__ == "__main__":
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"

    print("Starting SkillBench server...")
    print(f"  Landing:   http://localhost:{port}/")
    print(f"  Outputs:   {OUTPUTS_DIR}")
    print(f"  Hosted:    {'Yes (API key available)' if has_api_key else 'No (using mock agent)'}")
    print(f"  Rate limit: {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS}s")
    app.run(host="0.0.0.0", port=port, debug=debug)
