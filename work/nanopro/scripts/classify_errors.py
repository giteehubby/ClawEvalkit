#!/usr/bin/env python3
"""
Classify failure cases using OpenRouter's gemini-3.1-pro-preview.
Identifies which of 5 error categories each failure belongs to:
- A: Planning / Reasoning Failure
- B: Tool Use Failure
- C: State Grounding Failure
- D: Execution Failure
- E: Knowledge / Skill Gap
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

import httpx
from dotenv import load_dotenv

load_dotenv('/Volumes/F/Clauding/.env')

# Add project root to path
script_dir = Path(__file__).parent
_root_dir = script_dir.parent
sys.path.insert(0, str(_root_dir))

# Error categories
ERROR_CATEGORIES = {
    "A": "Planning / Reasoning Failure",
    "B": "Tool Use Failure",
    "C": "State Grounding Failure",
    "D": "Execution Failure",
    "E": "Knowledge / Skill Gap",
}

SYSTEM_PROMPT = """You are an expert at analyzing AI agent failure cases. Given a task transcript, you will classify the failure into exactly one of these categories:

A: Planning / Reasoning Failure - The agent made logical errors in planning, misunderstood the task requirements, or reasoning went wrong early in the process.

B: Tool Use Failure - The agent selected wrong tools, used tools incorrectly, or failed to properly invoke/call available tools.

C: State Grounding Failure - The agent lost track of workspace state, didn't notice previous changes, worked with stale information, or confused file versions.

D: Execution Failure - The agent made direct execution mistakes: syntax errors, wrong parameter values, file operation errors, or implementation bugs.

E: Knowledge / Skill Gap - The agent lacked domain knowledge or skill to complete the task properly, even with correct reasoning.

Output your classification in this exact format:
CATEGORY: [X]
REASON: [Brief explanation in 1-2 sentences]
"""


def load_transcript(transcripts_dir: Path, benchmark: str, task_id: str) -> Optional[str]:
    """Load transcript content for a failed task."""
    # Try different patterns
    patterns = [
        f"{task_id}_0.jsonl",
        f"{benchmark}_{task_id}_0.jsonl",
        f"{benchmark.replace('-', '_')}_{task_id}_0.jsonl",
    ]

    for pattern in patterns:
        path = transcripts_dir / pattern
        if path.exists():
            return path.read_text(encoding="utf-8")

    # Search
    for tf in transcripts_dir.glob(f"*{task_id}*0.jsonl"):
        return tf.read_text(encoding="utf-8")

    return None


def truncate_transcript(transcript: str, max_chars: int = 15000) -> str:
    """Truncate transcript to fit within context window."""
    if len(transcript) <= max_chars:
        return transcript
    return transcript[:max_chars] + "\n\n[TRANSCRIPT TRUNCATED]"


def construct_prompt(task_info: Dict, transcript: str, benchmark_data: Dict) -> str:
    """Construct the evaluation prompt from task info and transcript."""
    truncated = truncate_transcript(transcript)

    prompt = f"""Task: {task_info.get('task_id', 'unknown')}
Benchmark: {task_info.get('benchmark', 'unknown')}
Task Score: {task_info.get('score', 0):.2f}/100

Task Description:
{task_info.get('instruction', 'No description available')}

Transcript:
{truncated}

Based on the transcript above, classify this failure into category A, B, C, D, or E.
"""
    return prompt


def call_openrouter(prompt: str, api_key: str, api_url: str) -> Dict[str, str]:
    """Call OpenRouter API to classify the error."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    data = {
        "model": "google/gemini-3.1-pro-preview",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 200,
    }

    try:
        response = httpx.post(
            f"{api_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=60.0,
        )
        response.raise_for_status()
        result = response.json()

        content = result["choices"][0]["message"]["content"]
        return parse_response(content)
    except Exception as e:
        print(f"  Error calling API: {e}")
        return {"category": "ERROR", "reason": str(e)}


def parse_response(content: str) -> Dict[str, str]:
    """Parse the model response into category and reason."""
    result = {"category": "UNKNOWN", "reason": "Could not parse response", "raw_response": content[:500]}

    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("CATEGORY:"):
            cat = line.split(":", 1)[1].strip().upper()
            if cat in ERROR_CATEGORIES:
                result["category"] = cat
        elif line.startswith("REASON:"):
            result["reason"] = line.split(":", 1)[1].strip()

    # If category still UNKNOWN, try to find just the letter
    if result["category"] == "UNKNOWN":
        import re
        # Try patterns like "Category: A" or "The answer is C" or "[A]"
        match = re.search(r'\[([A-E])\]', content)
        if match:
            result["category"] = match.group(1)
            result["reason"] = "Parsed from context"
        match = re.search(r'\b([A-E])\b.*?(?:failure|error|issue)', content, re.IGNORECASE)
        if match:
            result["category"] = match.group(1)
            result["reason"] = "Parsed from context"

    return result


def classify_failures(
    exp_dir: Path,
    output_path: Path,
    api_key: str,
    api_url: str,
    max_tasks: int = None,
) -> List[Dict]:
    """Classify all failures in the experiment directory."""
    failures_file = exp_dir / "failure_cases" / "failures.json"
    if not failures_file.exists():
        print("No failures.json found. Run extract_failures.py first.")
        return []

    with open(failures_file) as f:
        failures = json.load(f)

    transcripts_dir = exp_dir / "failure_cases" / "transcripts"

    # Filter to only those with transcripts
    failures_with_transcripts = []
    for f in failures:
        transcript = load_transcript(transcripts_dir, f["benchmark"], f["task_id"])
        if transcript:
            f["transcript"] = transcript
            failures_with_transcripts.append(f)

    print(f"Found {len(failures_with_transcripts)} failures with transcripts")

    if max_tasks:
        failures_with_transcripts = failures_with_transcripts[:max_tasks]

    results = []

    for i, failure in enumerate(failures_with_transcripts, 1):
        print(f"[{i}/{len(failures_with_transcripts)}] Classifying {failure['benchmark']}/{failure['task_id']}...")

        prompt = construct_prompt(failure, failure.get("transcript", ""), failure)
        result = call_openrouter(prompt, api_key, api_url)

        results.append({
            "benchmark": failure["benchmark"],
            "task_id": failure["task_id"],
            "score": failure["score"],
            "category": result["category"],
            "reason": result["reason"],
        })

        # Save progress
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        # Rate limiting
        time.sleep(1)

    return results


def visualize_classification(exp_dir: Path, results: List[Dict]):
    """Generate HTML visualization of error classification."""
    # Count by category
    category_counts = {cat: 0 for cat in ERROR_CATEGORIES}
    category_counts["ERROR"] = 0
    category_counts["UNKNOWN"] = 0

    for r in results:
        category_counts[r["category"]] = category_counts.get(r["category"], 0) + 1

    total = len(results)
    valid = sum(category_counts.get(cat, 0) for cat in ERROR_CATEGORIES)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error Classification Results</title>
    <style>
        :root {{
            --bg-primary: #0f1419;
            --bg-secondary: #1a2332;
            --bg-tertiary: #243044;
            --text-primary: #e7e9ea;
            --text-secondary: #8b98a5;
            --cat-a: #f4212e;
            --cat-b: #ff6b6b;
            --cat-c: #ffad1f;
            --cat-d: #00ba7c;
            --cat-e: #4a9eff;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }}

        h1 {{
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }}

        .subtitle {{
            color: var(--text-secondary);
            margin-bottom: 2rem;
        }}

        .tldr {{
            background: var(--bg-tertiary);
            border-left: 4px solid var(--cat-a);
            padding: 1rem;
            margin-bottom: 1.5rem;
            border-radius: 0 8px 8px 0;
        }}

        .overview {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .card {{
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
        }}

        .card-value {{
            font-size: 2rem;
            font-weight: 700;
        }}

        .card-label {{
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-transform: uppercase;
        }}

        .cat-a {{ color: var(--cat-a); }}
        .cat-b {{ color: var(--cat-b); }}
        .cat-c {{ color: var(--cat-c); }}
        .cat-d {{ color: var(--cat-d); }}
        .cat-e {{ color: var(--cat-e); }}

        .section {{
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}

        .section-title {{
            font-size: 1.25rem;
            margin-bottom: 1rem;
        }}

        .bar-chart {{
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }}

        .bar-row {{
            display: grid;
            grid-template-columns: 200px 1fr 80px;
            gap: 1rem;
            align-items: center;
        }}

        .bar-container {{
            background: var(--bg-tertiary);
            border-radius: 4px;
            height: 20px;
            overflow: hidden;
        }}

        .bar {{
            height: 100%;
            border-radius: 4px;
        }}

        .bar.cat-a {{ background: var(--cat-a); }}
        .bar.cat-b {{ background: var(--cat-b); }}
        .bar.cat-c {{ background: var(--cat-c); }}
        .bar.cat-d {{ background: var(--cat-d); }}
        .bar.cat-e {{ background: var(--cat-e); }}

        table {{
            width: 100%;
            border-collapse: collapse;
        }}

        th, td {{
            text-align: left;
            padding: 0.75rem;
            border-bottom: 1px solid var(--bg-tertiary);
        }}

        th {{
            color: var(--text-secondary);
            font-size: 0.875rem;
        }}

        .category-badge {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.75rem;
        }}

        .badge-a {{ background: var(--cat-a); color: white; }}
        .badge-b {{ background: var(--cat-b); color: white; }}
        .badge-c {{ background: var(--cat-c); color: black; }}
        .badge-d {{ background: var(--cat-d); color: white; }}
        .badge-e {{ background: var(--cat-e); color: white; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Error Classification Results</h1>
        <p class="subtitle">Experiment: {exp_dir.name}</p>

        <div class="tldr">
            <strong>TL;DR</strong><br>
            Classified {valid} failures. {"Planning/Reasoning failures are most common" if category_counts.get("A", 0) > category_counts.get("B", 0) else "Tool Use failures are most common"}.
        </div>

        <div class="overview">
"""

    for cat, name in ERROR_CATEGORIES.items():
        count = category_counts.get(cat, 0)
        pct = (count / total * 100) if total > 0 else 0
        html += f"""
            <div class="card">
                <div class="card-value cat-{cat.lower()}">{count}</div>
                <div class="card-label">{cat}: {name[:20]}</div>
            </div>
"""

    html += f"""
            <div class="card">
                <div class="card-value">{total}</div>
                <div class="card-label">Total</div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">Distribution by Category</h2>
            <div class="bar-chart">
"""

    for cat, name in ERROR_CATEGORIES.items():
        count = category_counts.get(cat, 0)
        pct = (count / total * 100) if total > 0 else 0
        html += f"""
                <div class="bar-row">
                    <div>{cat}: {name}</div>
                    <div class="bar-container">
                        <div class="bar cat-{cat.lower()}" style="width: {pct}%"></div>
                    </div>
                    <div>{pct:.1f}%</div>
                </div>
"""

    html += """
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">Detailed Classifications</h2>
            <table>
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>Benchmark</th>
                        <th>Task</th>
                        <th>Score</th>
                        <th>Reason</th>
                    </tr>
                </thead>
                <tbody>
"""

    for r in sorted(results, key=lambda x: x["category"]):
        cat = r["category"]
        badge_class = f"badge-{cat.lower()}" if cat.isalpha() else ""
        html += f"""
                    <tr>
                        <td><span class="category-badge {badge_class}">{cat}</span></td>
                        <td>{r['benchmark']}</td>
                        <td>{r['task_id']}</td>
                        <td>{r['score']:.2f}</td>
                        <td>{r.get('reason', 'N/A')[:100]}</td>
                    </tr>
"""

    html += """
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

    output_path = exp_dir / "error_classification.html"
    with open(output_path, "w") as f:
        f.write(html)

    print(f"Visualization saved to {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Classify failure cases using OpenRouter")
    parser.add_argument("exp_dir", type=Path, help="Experiment directory")
    parser.add_argument("--api-key", help="OpenRouter API key (or set OPENAI_API_KEY env)")
    parser.add_argument("--api-url", default=os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"), help="OpenRouter API URL")
    parser.add_argument("--max-tasks", type=int, help="Maximum number of tasks to classify")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set. Pass --api-key or set OPENAI_API_KEY env var.")
        sys.exit(1)

    output_path = args.exp_dir / "error_classification_results.json"

    results = classify_failures(
        args.exp_dir,
        output_path,
        api_key,
        args.api_url,
        args.max_tasks,
    )

    if results:
        visualize_classification(args.exp_dir, results)


if __name__ == "__main__":
    main()
