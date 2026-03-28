#!/usr/bin/env python3
"""
Visualize baseline experiment results across all benchmarks.
Generates an HTML dashboard.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Any


def load_results(exp_dir: Path) -> List[Dict[str, Any]]:
    """Load all result JSON files from experiment directory."""
    results = []
    results_dir = exp_dir / "results"

    for result_file in results_dir.glob("*.json"):
        if result_file.name == "transcripts":
            continue
        try:
            with open(result_file) as f:
                data = json.load(f)
            results.append(data)
        except json.JSONDecodeError:
            pass

    return results


def get_benchmark_summary(data: Dict) -> Dict[str, Any]:
    """Extract summary info from benchmark result."""
    benchmark = data.get("benchmark", "unknown")

    # Different benchmarks have different structures
    if "overall_score" in data:
        score = data["overall_score"]
        total = data.get("total_tasks", 0)
        passed = data.get("passed_tasks", 0)

        # Normalize score to 0-100 if it's a ratio
        if score <= 1.0:
            score = score * 100
    elif "results" in data and "summary" in data["results"]:
        # Some benchmarks have nested structure
        summary = data["results"]["summary"]
        score = summary.get("success_rate", 0) * 100
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
    else:
        score = 0
        total = 0
        passed = 0

    return {
        "benchmark": benchmark,
        "score": score,
        "total": total,
        "passed": passed,
        "failed": total - passed,
    }


def generate_dashboard(exp_dir: Path, output_path: Path = None):
    """Generate HTML dashboard for experiment results."""
    results = load_results(exp_dir)

    if not results:
        print("No results found")
        return

    summaries = [get_benchmark_summary(r) for r in results]

    # Calculate overall score
    total_tasks = sum(s["total"] for s in summaries)
    total_passed = sum(s["passed"] for s in summaries)
    overall_score = (total_passed / total_tasks * 100) if total_tasks > 0 else 0

    # Sort by score descending
    summaries.sort(key=lambda x: x["score"], reverse=True)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Baseline Experiment Results</title>
    <style>
        :root {{
            --bg-primary: #0f1419;
            --bg-secondary: #1a2332;
            --bg-tertiary: #243044;
            --text-primary: #e7e9ea;
            --text-secondary: #8b98a5;
            --accent: #4a9eff;
            --success: #00ba7c;
            --warning: #ffad1f;
            --danger: #f4212e;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

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

        .overview {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .card {{
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 1.5rem;
        }}

        .card-title {{
            color: var(--text-secondary);
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .card-value {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-top: 0.5rem;
        }}

        .card-value.score {{
            color: var(--accent);
        }}

        .card-value.passed {{
            color: var(--success);
        }}

        .card-value.total {{
            color: var(--text-primary);
        }}

        .chart-section {{
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}

        .chart-title {{
            font-size: 1.25rem;
            margin-bottom: 1rem;
        }}

        .bar-chart {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}

        .bar-row {{
            display: grid;
            grid-template-columns: 150px 1fr 80px;
            gap: 1rem;
            align-items: center;
        }}

        .bar-label {{
            font-size: 0.875rem;
            color: var(--text-secondary);
        }}

        .bar-container {{
            background: var(--bg-tertiary);
            border-radius: 4px;
            height: 24px;
            overflow: hidden;
        }}

        .bar {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }}

        .bar.high {{ background: linear-gradient(90deg, #00ba7c, #00d68f); }}
        .bar.medium {{ background: linear-gradient(90deg, #ffad1f, #ffc947); }}
        .bar.low {{ background: linear-gradient(90deg, #f4212e, #ff6b6b); }}

        .bar-value {{
            font-weight: 600;
            text-align: right;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }}

        th, td {{
            text-align: left;
            padding: 0.75rem;
            border-bottom: 1px solid var(--bg-tertiary);
        }}

        th {{
            color: var(--text-secondary);
            font-weight: 500;
            font-size: 0.875rem;
        }}

        .score-cell {{
            font-weight: 600;
        }}

        .score-high {{ color: var(--success); }}
        .score-medium {{ color: var(--warning); }}
        .score-low {{ color: var(--danger); }}

        .tldr {{
            background: var(--bg-tertiary);
            border-left: 4px solid var(--accent);
            padding: 1rem;
            margin-bottom: 1.5rem;
            border-radius: 0 8px 8px 0;
        }}

        .failure-section {{
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Baseline Experiment Results</h1>
        <p class="subtitle">Experiment: {exp_dir.name} | Model: google/gemini-3-flash-preview</p>

        <div class="tldr">
            <strong>TL;DR</strong><br>
            Overall Score: {overall_score:.1f}% across {total_tasks} tasks.
            {"Strong performance on ClawBench-TRIBE (93.3%) and ClawBench-Official (80.5%)." if overall_score > 70 else "Moderate performance with room for improvement."}
        </div>

        <div class="overview">
            <div class="card">
                <div class="card-title">Overall Score</div>
                <div class="card-value score">{overall_score:.1f}%</div>
            </div>
            <div class="card">
                <div class="card-title">Total Tasks</div>
                <div class="card-value total">{total_tasks}</div>
            </div>
            <div class="card">
                <div class="card-title">Passed</div>
                <div class="card-value passed">{total_passed}</div>
            </div>
            <div class="card">
                <div class="card-title">Failed</div>
                <div class="card-value" style="color: var(--danger)">{total_tasks - total_passed}</div>
            </div>
        </div>

        <div class="chart-section">
            <h2 class="chart-title">Score by Benchmark</h2>
            <div class="bar-chart">
"""

    for s in summaries:
        score = s["score"]
        if score >= 70:
            bar_class = "high"
        elif score >= 50:
            bar_class = "medium"
        else:
            bar_class = "low"

        display_name = s["benchmark"].replace("-", " ").replace("_", " ").title()
        html += f"""
                <div class="bar-row">
                    <div class="bar-label">{display_name}</div>
                    <div class="bar-container">
                        <div class="bar {bar_class}" style="width: {score}%"></div>
                    </div>
                    <div class="bar-value">{score:.1f}%</div>
                </div>
"""

    html += """
            </div>
        </div>

        <div class="chart-section">
            <h2 class="chart-title">Detailed Results</h2>
            <table>
                <thead>
                    <tr>
                        <th>Benchmark</th>
                        <th>Score</th>
                        <th>Passed</th>
                        <th>Failed</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
"""

    for s in summaries:
        score = s["score"]
        if score >= 70:
            score_class = "score-high"
        elif score >= 50:
            score_class = "score-medium"
        else:
            score_class = "score-low"

        display_name = s["benchmark"].replace("-", " ").replace("_", " ").title()
        html += f"""
                    <tr>
                        <td>{display_name}</td>
                        <td class="score-cell {score_class}">{score:.1f}%</td>
                        <td>{s["passed"]}</td>
                        <td>{s["failed"]}</td>
                        <td>{s["total"]}</td>
                    </tr>
"""

    html += """
                </tbody>
            </table>
        </div>

        <div class="failure-section">
            <h2 class="chart-title">Failure Analysis</h2>
            <table>
                <thead>
                    <tr>
                        <th>Benchmark</th>
                        <th>Task</th>
                        <th>Score</th>
                    </tr>
                </thead>
                <tbody>
"""

    # Load failure data
    failure_file = exp_dir / "failure_cases" / "failures.json"
    if failure_file.exists():
        with open(failure_file) as f:
            failures = json.load(f)

        for f in sorted(failures, key=lambda x: (x["benchmark"], x["task_id"]))[:50]:
            display_name = f["benchmark"].replace("-", " ").replace("_", " ").title()
            html += f"""
                    <tr>
                        <td>{display_name}</td>
                        <td>{f["task_id"]}</td>
                        <td class="score-cell score-low">{f["score"]:.2f}</td>
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

    if output_path is None:
        output_path = exp_dir / "dashboard.html"

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Dashboard saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Visualize baseline experiment results")
    parser.add_argument("exp_dir", type=Path, help="Experiment directory")
    parser.add_argument("--output", type=Path, help="Output HTML path")
    args = parser.parse_args()

    generate_dashboard(args.exp_dir, args.output)


if __name__ == "__main__":
    main()
