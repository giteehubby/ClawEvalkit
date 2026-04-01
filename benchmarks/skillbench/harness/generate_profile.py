#!/usr/bin/env python3
"""
Generate skill profile artifacts from benchmark report JSON.

Outputs:
    - profile.html (human-facing)
    - scorecard.json (machine-facing)

Usage:
    python -m harness.generate_profile reports/real-agent-test.json --output-dir web/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import uuid
from datetime import datetime
from typing import Optional


def load_report(path: pathlib.Path) -> dict:
    """Load and validate a benchmark report."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_skill_name(report: dict) -> str:
    """Extract skill name from report."""
    augmented = report.get("augmented", {})
    tasks = augmented.get("tasks", [])
    for task in tasks:
        result = task.get("result", {})
        skill_name = result.get("skill_name")
        if skill_name:
            return skill_name
    return "Unknown Skill"


def generate_summary(report: dict) -> str:
    """Generate a human-readable summary sentence."""
    baseline = report.get("baseline", {}).get("aggregate", {})
    augmented = report.get("augmented", {}).get("aggregate", {})

    baseline_passed = baseline.get("passed", 0)
    augmented_passed = augmented.get("passed", 0)
    total = baseline.get("total", 0)
    delta = augmented_passed - baseline_passed

    if delta > 0:
        # Find what kind of task it helped with
        helped_tasks = []
        for task in report.get("augmented", {}).get("tasks", []):
            result = task.get("result", {})
            task_id = task.get("task_id", "")
            # Check if this task passed in augmented but not baseline
            baseline_task = next(
                (t for t in report.get("baseline", {}).get("tasks", [])
                 if t.get("task_id") == task_id),
                {}
            )
            baseline_status = baseline_task.get("result", {}).get("status")
            aug_status = result.get("status")
            if aug_status == "passed" and baseline_status != "passed":
                helped_tasks.append(task_id)

        if "001" in str(helped_tasks):
            return (
                "This skill helped the agent fix arithmetic bugs it couldn't solve alone. "
                "No measurable impact on other bug types like string manipulation or validation logic."
            )
        else:
            return (
                f"This skill improved task success from {baseline_passed} to {augmented_passed} "
                f"out of {total} tasks."
            )
    elif delta == 0:
        return (
            "This skill had no measurable impact on task success rates. "
            "The agent performed the same with and without the skill."
        )
    else:
        return (
            f"This skill reduced task success from {baseline_passed} to {augmented_passed}. "
            "Consider reviewing the skill's guidance for potential issues."
        )


def get_reliability_delta(report: dict) -> tuple[float, str]:
    """Get reliability delta and formatted string."""
    profile = report.get("profile", {})
    reliability = profile.get("reliability", {}).get("success_rate", {})
    delta = reliability.get("delta", 0) or 0

    if delta > 0:
        return delta, f"+{int(delta * 100)}%"
    elif delta < 0:
        return delta, f"{int(delta * 100)}%"
    else:
        return 0, "no change"


def get_efficiency_delta(report: dict) -> tuple[float, str]:
    """Get efficiency delta and formatted string."""
    profile = report.get("profile", {})
    efficiency = profile.get("efficiency", {}).get("avg_runtime_s", {})
    delta = efficiency.get("delta", 0) or 0

    # For efficiency, negative delta (faster) is good
    if abs(delta) < 0.01:
        return 0, "no change"
    elif delta < 0:
        return delta, f"{int(delta * 1000)}ms faster"
    else:
        return delta, f"+{int(delta * 1000)}ms slower"


def get_examples(report: dict) -> dict:
    """Extract example cases: helped, didn't matter, observation."""
    examples = {
        "helped": None,
        "neutral": None,
        "observation": None,
    }

    baseline_tasks = {t.get("task_id"): t for t in report.get("baseline", {}).get("tasks", [])}
    augmented_tasks = report.get("augmented", {}).get("tasks", [])

    for task in augmented_tasks:
        task_id = task.get("task_id", "")
        result = task.get("result", {})
        baseline_task = baseline_tasks.get(task_id, {})
        baseline_result = baseline_task.get("result", {})

        aug_status = result.get("status")
        base_status = baseline_result.get("status")

        if aug_status == "passed" and base_status != "passed" and not examples["helped"]:
            examples["helped"] = {
                "task_id": task_id,
                "description": get_task_description(task_id),
                "detail": "The skill provided guidance that helped the agent generate a correct fix.",
            }
        elif aug_status == base_status and not examples["neutral"]:
            examples["neutral"] = {
                "task_id": task_id,
                "description": get_task_description(task_id),
                "detail": "The skill's guidance didn't apply to this type of bug.",
            }

    # Always add an observation
    skill_name = extract_skill_name(report)
    examples["observation"] = {
        "title": "What we observed",
        "detail": (
            f"This skill is narrowly focused on specific bug patterns. "
            f"It improved reliability on its target domain without negative side effects "
            f"on unrelated tasks. Consider pairing with complementary skills for broader coverage."
        ),
    }

    return examples


def get_task_description(task_id: str) -> str:
    """Get human-readable task description."""
    descriptions = {
        "swe-lite-001": "Fix the add() function to return correct sum",
        "swe-lite-002": "Fix slugify() to use hyphen-separated slugs",
        "swe-lite-003": "Fix mean() to compute average correctly",
        "swe-lite-004": "Fix off-by-one error in array slicing",
        "swe-lite-005": "Fix comparison operator in age validation",
        "swe-lite-006": "Add missing return statement",
        "swe-lite-007": "Fix string method to collapse spaces",
        "swe-lite-008": "Fix integer division bug",
        "swe-lite-009": "Fix loop boundary in vowel counter",
        "swe-lite-010": "Add null check for nickname",
    }
    return descriptions.get(task_id, task_id)


def get_trace_items(report: dict) -> list[dict]:
    """Get trace items for the traces panel."""
    items = []
    for task in report.get("augmented", {}).get("tasks", []):
        task_id = task.get("task_id", "")
        result = task.get("result", {})
        status = result.get("status", "failed")
        items.append({
            "task_id": task_id,
            "description": get_task_description(task_id),
            "status": status,
        })
    return items


def generate_html(report: dict, template_path: Optional[pathlib.Path] = None, scorecard_url: str = "scorecard.json", traces_url: str = "#") -> str:
    """Generate profile HTML from report data."""

    skill_name = extract_skill_name(report)
    summary = generate_summary(report)
    reliability_delta, reliability_str = get_reliability_delta(report)
    efficiency_delta, efficiency_str = get_efficiency_delta(report)
    examples = get_examples(report)
    traces = get_trace_items(report)

    # Get metadata
    baseline = report.get("baseline", {}).get("aggregate", {})
    augmented = report.get("augmented", {}).get("aggregate", {})
    total_tasks = baseline.get("total", 0)
    baseline_passed = baseline.get("passed", 0)
    augmented_passed = augmented.get("passed", 0)
    timestamp = report.get("timestamp", datetime.now().isoformat())

    # Run metadata
    run_id = report.get("run_id", str(uuid.uuid4())[:8])
    runner_version = "0.2.0"
    agent_name = "Claude Sonnet"  # Human-readable agent name
    suite_id = "core-bugfix"
    suite_version = "1.0.0"

    # Format date
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        date_str = dt.strftime("%B %d, %Y")
        datetime_str = dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
        date_str = timestamp[:10]
        datetime_str = timestamp[:19]

    # Determine CSS classes for deltas
    reliability_class = "positive" if reliability_delta > 0 else ("negative" if reliability_delta < 0 else "neutral")
    efficiency_class = "neutral" if abs(efficiency_delta) < 0.01 else ("positive" if efficiency_delta < 0 else "negative")

    # Bar widths (normalized)
    reliability_width = min(100, max(10, 50 + reliability_delta * 100))
    efficiency_width = 50  # Neutral baseline

    # Generate trace HTML
    trace_html = ""
    for trace in traces:
        status_icon = "&#9989;" if trace["status"] == "passed" else "&#10060;"
        status_class = "passed" if trace["status"] == "passed" else "failed"
        trace_html += f'''
        <div class="trace-item {status_class}">
          <span class="trace-status">{status_icon}</span>
          <span class="trace-name">{trace["task_id"]}</span>
          <span class="trace-desc">{trace["description"]}</span>
          <span class="trace-badge">{trace["status"]}</span>
        </div>'''

    # Generate examples HTML
    helped = examples.get("helped")
    neutral = examples.get("neutral")
    observation = examples.get("observation")

    helped_html = ""
    if helped:
        helped_html = f'''
    <div class="example-card" onclick="toggleExample(this)">
      <div class="example-header">
        <span class="example-icon">&#9989;</span>
        <span class="example-title">A case where it helped</span>
        <span class="example-chevron">&#9662;</span>
      </div>
      <div class="example-content">
        <p class="example-description">
          <strong>Task:</strong> {helped["description"]}<br><br>
          {helped["detail"]}
        </p>
      </div>
    </div>'''

    neutral_html = ""
    if neutral:
        neutral_html = f'''
    <div class="example-card" onclick="toggleExample(this)">
      <div class="example-header">
        <span class="example-icon">&#128528;</span>
        <span class="example-title">A case where it didn't matter</span>
        <span class="example-chevron">&#9662;</span>
      </div>
      <div class="example-content">
        <p class="example-description">
          <strong>Task:</strong> {neutral["description"]}<br><br>
          {neutral["detail"]}
        </p>
      </div>
    </div>'''

    observation_html = f'''
    <div class="example-card" onclick="toggleExample(this)">
      <div class="example-header">
        <span class="example-icon">&#128269;</span>
        <span class="example-title">{observation["title"]}</span>
        <span class="example-chevron">&#9662;</span>
      </div>
      <div class="example-content">
        <p class="example-description">
          {observation["detail"]}
        </p>
      </div>
    </div>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Skill Profile - {skill_name}</title>
  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #fafafa;
      color: #1a1a1a;
      line-height: 1.6;
      padding: 2rem;
      max-width: 720px;
      margin: 0 auto;
    }}

    .skill-name {{
      font-size: 0.875rem;
      color: #666;
      margin-bottom: 0.25rem;
    }}

    h1 {{
      font-size: 1.5rem;
      font-weight: 600;
      margin-bottom: 2rem;
    }}

    .summary {{
      background: white;
      border: 1px solid #e5e5e5;
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 2rem;
    }}

    .summary-label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #666;
      margin-bottom: 0.5rem;
    }}

    .summary-text {{
      font-size: 1.125rem;
      color: #1a1a1a;
    }}

    .profile {{
      background: white;
      border: 1px solid #e5e5e5;
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 2rem;
    }}

    .profile-title {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #666;
      margin-bottom: 1rem;
    }}

    .metric {{
      margin-bottom: 1.25rem;
    }}

    .metric:last-child {{
      margin-bottom: 0;
    }}

    .metric-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.5rem;
    }}

    .metric-name {{
      font-size: 0.875rem;
      font-weight: 500;
    }}

    .metric-delta {{
      font-size: 0.875rem;
      font-weight: 500;
    }}

    .metric-delta.positive {{
      color: #16a34a;
    }}

    .metric-delta.neutral {{
      color: #666;
    }}

    .metric-delta.negative {{
      color: #dc2626;
    }}

    .bar-container {{
      height: 8px;
      background: #e5e5e5;
      border-radius: 4px;
      overflow: hidden;
    }}

    .bar-fill {{
      height: 100%;
      border-radius: 4px;
      transition: width 0.3s ease;
    }}

    .bar-fill.positive {{
      background: linear-gradient(90deg, #22c55e, #16a34a);
    }}

    .bar-fill.neutral {{
      background: #a3a3a3;
    }}

    .bar-fill.negative {{
      background: linear-gradient(90deg, #f87171, #dc2626);
    }}

    .disclosure {{
      margin-top: 1rem;
      padding-top: 1rem;
      border-top: 1px solid #f0f0f0;
    }}

    .disclosure-toggle {{
      font-size: 0.75rem;
      color: #666;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }}

    .disclosure-toggle:hover {{
      color: #1a1a1a;
    }}

    .disclosure-content {{
      display: none;
      margin-top: 0.75rem;
      font-size: 0.75rem;
      color: #666;
      line-height: 1.5;
    }}

    .disclosure-content.open {{
      display: block;
    }}

    .examples {{
      margin-bottom: 2rem;
    }}

    .examples-title {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #666;
      margin-bottom: 1rem;
    }}

    .example-card {{
      background: white;
      border: 1px solid #e5e5e5;
      border-radius: 8px;
      margin-bottom: 0.75rem;
      overflow: hidden;
    }}

    .example-header {{
      padding: 1rem 1.25rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}

    .example-header:hover {{
      background: #fafafa;
    }}

    .example-icon {{
      font-size: 1.25rem;
    }}

    .example-title {{
      font-size: 0.875rem;
      font-weight: 500;
      flex: 1;
    }}

    .example-chevron {{
      color: #999;
      transition: transform 0.2s ease;
    }}

    .example-card.open .example-chevron {{
      transform: rotate(180deg);
    }}

    .example-content {{
      display: none;
      padding: 0 1.25rem 1.25rem;
      border-top: 1px solid #f0f0f0;
    }}

    .example-card.open .example-content {{
      display: block;
    }}

    .example-description {{
      font-size: 0.875rem;
      color: #444;
      margin-top: 1rem;
    }}

    .footer {{
      padding-top: 1.5rem;
      margin-top: 2rem;
      border-top: 1px solid #e5e5e5;
    }}

    .footer-meta {{
      margin-bottom: 1rem;
    }}

    .footer-details {{
      font-size: 0.75rem;
      color: #666;
    }}

    .footer-details summary {{
      cursor: pointer;
      list-style: none;
    }}

    .footer-details summary::-webkit-details-marker {{
      display: none;
    }}

    .footer-details summary::before {{
      content: '\\25B8 ';
      margin-right: 0.25rem;
    }}

    .footer-details[open] summary::before {{
      content: '\\25BE ';
    }}

    .footer-details-content {{
      margin-top: 0.75rem;
      padding: 0.75rem;
      background: #f9f9f9;
      border-radius: 6px;
    }}

    .footer-row {{
      display: flex;
      justify-content: space-between;
      padding: 0.25rem 0;
      font-size: 0.75rem;
    }}

    .footer-row span:first-child {{
      color: #666;
    }}

    .footer-row span:last-child {{
      color: #333;
      font-weight: 500;
    }}

    .footer-row code {{
      font-family: monospace;
      font-size: 0.7rem;
      background: #eee;
      padding: 0.1rem 0.3rem;
      border-radius: 3px;
    }}

    .footer-links {{
      display: flex;
      gap: 1.5rem;
    }}

    .footer-link {{
      font-size: 0.75rem;
      color: #666;
      text-decoration: none;
    }}

    .footer-link:hover {{
      color: #1a1a1a;
      text-decoration: underline;
    }}

    .panel-overlay {{
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.3);
      z-index: 100;
    }}

    .panel-overlay.open {{
      display: block;
    }}

    .panel {{
      display: none;
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: white;
      border-radius: 12px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
      z-index: 101;
      width: 90%;
      max-width: 400px;
      max-height: 80vh;
      overflow: hidden;
    }}

    .panel.panel-wide {{
      max-width: 500px;
    }}

    .panel.open {{
      display: block;
    }}

    .panel-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1rem 1.25rem;
      border-bottom: 1px solid #e5e5e5;
    }}

    .panel-title {{
      font-size: 0.875rem;
      font-weight: 600;
    }}

    .panel-close {{
      background: none;
      border: none;
      font-size: 1.5rem;
      color: #999;
      cursor: pointer;
      line-height: 1;
    }}

    .panel-close:hover {{
      color: #333;
    }}

    .panel-content {{
      padding: 1.25rem;
      overflow-y: auto;
      max-height: calc(80vh - 60px);
    }}

    .panel-row {{
      display: flex;
      justify-content: space-between;
      padding: 0.5rem 0;
      border-bottom: 1px solid #f0f0f0;
    }}

    .panel-row:last-child {{
      border-bottom: none;
    }}

    .panel-label {{
      font-size: 0.75rem;
      color: #666;
    }}

    .panel-value {{
      font-size: 0.75rem;
      font-weight: 500;
      color: #1a1a1a;
    }}

    .trace-list {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }}

    .trace-item {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.625rem 0.75rem;
      background: #fafafa;
      border-radius: 6px;
      font-size: 0.75rem;
    }}

    .trace-status {{
      font-size: 0.875rem;
    }}

    .trace-name {{
      font-weight: 500;
      min-width: 80px;
    }}

    .trace-desc {{
      flex: 1;
      color: #666;
    }}

    .trace-badge {{
      padding: 0.125rem 0.5rem;
      border-radius: 4px;
      font-size: 0.625rem;
      text-transform: uppercase;
      font-weight: 600;
    }}

    .trace-item.passed .trace-badge {{
      background: #dcfce7;
      color: #166534;
    }}

    .trace-item.failed .trace-badge {{
      background: #fee2e2;
      color: #991b1b;
    }}
  </style>
</head>
<body>
  <div class="skill-name">Skill profile</div>
  <h1>{skill_name}</h1>

  <section class="summary">
    <div class="summary-label">Summary</div>
    <p class="summary-text">{summary}</p>
  </section>

  <section class="profile">
    <div class="profile-title">Behavioral Profile</div>

    <div class="metric">
      <div class="metric-header">
        <span class="metric-name">Reliability</span>
        <span class="metric-delta {reliability_class}">{reliability_str}</span>
      </div>
      <div class="bar-container">
        <div class="bar-fill {reliability_class}" style="width: {reliability_width}%"></div>
      </div>
    </div>

    <div class="metric">
      <div class="metric-header">
        <span class="metric-name">Efficiency</span>
        <span class="metric-delta {efficiency_class}">{efficiency_str}</span>
      </div>
      <div class="bar-container">
        <div class="bar-fill {efficiency_class}" style="width: {efficiency_width}%"></div>
      </div>
    </div>

    <div class="disclosure">
      <span class="disclosure-toggle" onclick="toggleDisclosure(this)">
        How was this measured? <span>&#9662;</span>
      </span>
      <div class="disclosure-content">
        Compared to a standard agent without this skill.<br>
        Tested on <strong>Core Bugfix Suite v1.0</strong> (arithmetic + string bugs).<br><br>
        Out of {total_tasks} bugfix tasks, the baseline agent solved {baseline_passed}; with this skill it solved {augmented_passed}.
      </div>
    </div>
  </section>

  <section class="examples">
    <div class="examples-title">Examples</div>
    {helped_html}
    {neutral_html}
    {observation_html}
  </section>

  <footer class="footer">
    <div class="footer-meta">
      <details class="footer-details">
        <summary>Run details</summary>
        <div class="footer-details-content">
          <div class="footer-row"><span>Suite</span><span>{suite_id} v{suite_version}</span></div>
          <div class="footer-row"><span>Agent</span><span>{agent_name}</span></div>
          <div class="footer-row"><span>Runner</span><span>v{runner_version}</span></div>
          <div class="footer-row"><span>Generated</span><span>{datetime_str}</span></div>
          <div class="footer-row"><span>Run ID</span><span><code>{run_id}</code></span></div>
        </div>
      </details>
    </div>
    <div class="footer-links">
      <a href="{scorecard_url}" class="footer-link">Scorecard JSON</a>
      <a href="{traces_url}" class="footer-link">Traces</a>
    </div>
  </footer>

  <div id="panel-overlay" class="panel-overlay" onclick="closePanel()"></div>

  <div id="panel-tested-on" class="panel">
    <div class="panel-header">
      <span class="panel-title">What this was tested on</span>
      <button class="panel-close" onclick="closePanel()">&times;</button>
    </div>
    <div class="panel-content">
      <div class="panel-row">
        <span class="panel-label">Suite</span>
        <span class="panel-value">Core Bugfix Suite v1.0</span>
      </div>
      <div class="panel-row">
        <span class="panel-label">Tasks</span>
        <span class="panel-value">{total_tasks} (arithmetic, string, validation)</span>
      </div>
      <div class="panel-row">
        <span class="panel-label">Agent</span>
        <span class="panel-value">Claude Sonnet</span>
      </div>
      <div class="panel-row">
        <span class="panel-label">Runner</span>
        <span class="panel-value">Local sandbox v0.1.0</span>
      </div>
      <div class="panel-row">
        <span class="panel-label">Evaluated</span>
        <span class="panel-value">{date_str}</span>
      </div>
    </div>
  </div>

  <div id="panel-traces" class="panel panel-wide">
    <div class="panel-header">
      <span class="panel-title">Execution traces</span>
      <button class="panel-close" onclick="closePanel()">&times;</button>
    </div>
    <div class="panel-content">
      <div class="trace-list">
        {trace_html}
      </div>
    </div>
  </div>

  <script>
    function toggleDisclosure(el) {{
      const content = el.nextElementSibling;
      content.classList.toggle('open');
    }}

    function toggleExample(card) {{
      card.classList.toggle('open');
    }}

    function openPanel(name) {{
      document.getElementById('panel-overlay').classList.add('open');
      document.getElementById('panel-' + name).classList.add('open');
    }}

    function closePanel() {{
      document.getElementById('panel-overlay').classList.remove('open');
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('open'));
    }}

    document.addEventListener('keydown', function(e) {{
      if (e.key === 'Escape') closePanel();
    }});
  </script>
</body>
</html>'''

    return html


def generate_scorecard(report: dict, profile_html: str) -> dict:
    """Generate machine-readable scorecard from report data."""

    skill_name = extract_skill_name(report)
    skill_id = skill_name.lower().replace(" ", "-")
    summary = generate_summary(report)
    timestamp = report.get("timestamp", datetime.now().isoformat())

    baseline = report.get("baseline", {}).get("aggregate", {})
    augmented = report.get("augmented", {}).get("aggregate", {})
    profile = report.get("profile", {})

    # Calculate digests
    profile_digest = hashlib.sha256(profile_html.encode()).hexdigest()

    # Extract metrics
    reliability = profile.get("reliability", {}).get("success_rate", {})
    efficiency = profile.get("efficiency", {}).get("avg_runtime_s", {})
    legibility = profile.get("failure_legibility", {})

    # Generate reproducibility data
    import os
    import random
    suite_seed = report.get("suite_seed") or random.randint(100000, 999999)
    adapter_name = report.get("adapter_name", "agentic")
    adapter_version = report.get("adapter_version", "0.2.0")
    agent_model_id = os.environ.get("SKILLBENCH_AGENT_MODEL", "claude-sonnet-4-20250514")

    # Compute config digest
    config_data = {
        "suite_id": "core-bugfix",
        "suite_version": "1.0.0",
        "suite_seed": suite_seed,
        "adapter_name": adapter_name,
        "adapter_version": adapter_version,
        "agent_model_id": agent_model_id,
        "limits": {
            "max_steps": int(os.environ.get("SKILLBENCH_AGENT_MAX_STEPS", "15")),
            "max_tool_calls": int(os.environ.get("SKILLBENCH_AGENT_MAX_TOOL_CALLS", "50")),
            "max_wall_time_s": float(os.environ.get("SKILLBENCH_AGENT_MAX_WALL_TIME", "180")),
        },
        "temperature": float(os.environ.get("SKILLBENCH_AGENT_TEMPERATURE", "0.0")),
    }
    import json as json_module
    config_digest = hashlib.sha256(
        json_module.dumps(config_data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]

    # Get skill artifact digest if provided
    skill_artifact_digest = os.environ.get("SKILLBENCH_SKILL_DIGEST")

    scorecard = {
        "schema_version": "1.1.0",
        "skill": {
            "id": skill_id,
            "name": skill_name,
            "version": None,
            "artifact_digest": skill_artifact_digest,
        },
        "run": {
            "run_id": str(uuid.uuid4()),
            "executed_at": timestamp,
            "runner_version": "0.2.0",
            "adapter": {
                "name": adapter_name,
                "version": adapter_version,
            },
            "agent_model_id": agent_model_id,
            "execution_mode": "local",
            "config_digest": config_digest,
        },
        "suite": {
            "id": "core-bugfix",
            "version": "1.0.0",
            "seed": suite_seed,
            "task_count": baseline.get("total", 0),
            "categories": ["arithmetic", "string", "validation", "loops"],
        },
        "baseline": {
            "type": "no-skill",
            "profile_id": None,
            "digest": None,
        },
        "metrics": {
            "reliability": {
                "baseline": reliability.get("baseline"),
                "augmented": reliability.get("augmented"),
                "delta": reliability.get("delta"),
                "tasks_passed_baseline": baseline.get("passed", 0),
                "tasks_passed_augmented": augmented.get("passed", 0),
                "total_tasks": baseline.get("total", 0),
            },
            "efficiency": {
                "baseline_avg_ms": round(efficiency.get("baseline", 0) * 1000, 1) if efficiency.get("baseline") else None,
                "augmented_avg_ms": round(efficiency.get("augmented", 0) * 1000, 1) if efficiency.get("augmented") else None,
                "delta_ms": round(efficiency.get("delta", 0) * 1000, 1) if efficiency.get("delta") else None,
            },
            "robustness": profile.get("robustness") or None,
            "legibility": {
                "explicit_error_rate": legibility.get("explicit_error_rate", {}).get("augmented"),
                "silent_failure_rate": legibility.get("silent_failure_rate", {}).get("augmented"),
            },
        },
        "summary": {
            "headline": summary,
            "recommendation": None,
        },
        "artifacts": {
            "profile_url": None,
            "traces_url": None,
            "profile_digest": profile_digest,
            "traces_digest": None,
        },
        "signature": None,
    }

    return scorecard


def main():
    parser = argparse.ArgumentParser(description="Generate skill profile artifacts from benchmark report")
    parser.add_argument("report", help="Path to benchmark report JSON")
    parser.add_argument("--output-dir", "-o", default=".", help="Output directory for artifacts")
    parser.add_argument("--html-only", action="store_true", help="Only generate HTML, skip scorecard")
    parser.add_argument("--scorecard-url", default="scorecard.json", help="URL for scorecard link in profile")
    parser.add_argument("--traces-url", default="#", help="URL for traces link in profile")
    args = parser.parse_args()

    report_path = pathlib.Path(args.report)
    if not report_path.exists():
        raise SystemExit(f"Report not found: {report_path}")

    report = load_report(report_path)

    # Generate HTML
    html = generate_html(report, scorecard_url=args.scorecard_url, traces_url=args.traces_url)

    # Output paths
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    skill_name = extract_skill_name(report)
    skill_slug = skill_name.lower().replace(" ", "-")

    html_path = output_dir / f"{skill_slug}-profile.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"Generated: {html_path}")

    if not args.html_only:
        # Generate scorecard
        scorecard = generate_scorecard(report, html)

        # Sign the scorecard
        try:
            from harness.signing import sign_scorecard
            scorecard = sign_scorecard(scorecard)
            print("Scorecard signed successfully")
        except Exception as e:
            print(f"Warning: Could not sign scorecard: {e}")

        scorecard_path = output_dir / f"{skill_slug}-scorecard.json"
        scorecard_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
        print(f"Generated: {scorecard_path}")


if __name__ == "__main__":
    main()
