"""WildClawBench Grading — 自动化 checks + LLM Judge 评分。

评分方式:
1. 自动化 checks: 直接在宿主机运行任务 markdown 中的 Python grading 函数
2. LLM Judge: 通过 run_judge_eval 使用 Judge Model 评分

不依赖 Docker。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

logger = logging.getLogger(__name__)

TMP_WORKSPACE = os.environ.get("TMP_WORKSPACE", "/tmp_workspace")


def run_automated_checks(
    automated_checks: str,
    workspace: Path,
    transcript: list = None,
    timeout: int = 120,
) -> dict:
    """Run automated checks Python code directly on host (no Docker).

    Args:
        automated_checks: Python code containing grade() function
        workspace: Path to the task workspace (where /tmp_workspace points to)
        transcript: Optional agent transcript for transcript-based checks
        timeout: Timeout in seconds for grading script

    Returns:
        Dict of scores from the grade() function, or {"error": ...} on failure
    """
    if not automated_checks or not automated_checks.strip():
        return {"error": "No automated checks provided"}

    # Prepare the grading code
    # Replace /tmp_workspace with actual workspace path
    runner_code_parts = [
        "import json",
        "import sys",
        "import os",
        "from pathlib import Path",
        "import re",
        f'os.environ["TMP_WORKSPACE"] = "{str(workspace)}"',
        f'os.chdir("{str(workspace)}")',
        "",
        automated_checks,
        "",
        # Call grade function with proper arguments
        f'result = grade(workspace_path="{str(workspace)}", transcript={json.dumps(transcript or [])})',
        "print(json.dumps(result))",
    ]
    runner_code = "\n".join(runner_code_parts) + "\n"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(runner_code)
        tmp_script = f.name

    try:
        result = subprocess.run(
            [sys.executable or "python3", tmp_script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workspace),
            env=os.environ.copy(),
        )

        if result.returncode != 0:
            logger.error(f"Automated checks failed: {result.stderr}")
            return {"error": f"grade script failed: {result.stderr[:200]}"}

        try:
            scores = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            # Try to find JSON in output
            scores = None
            for line in reversed(result.stdout.strip().splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        scores = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue

            if scores is None:
                logger.error(f"Failed to parse grading result: {result.stdout[:200]}")
                return {"error": f"json parse failed: {result.stdout[:200]}"}

        return scores

    except subprocess.TimeoutExpired:
        logger.error(f"Automated checks timed out after {timeout}s")
        return {"error": f"timeout after {timeout}s"}
    except Exception as e:
        logger.error(f"Automated checks error: {e}")
        return {"error": str(e)}
    finally:
        Path(tmp_script).unlink(missing_ok=True)


def run_grading(task_id: str, automated_checks: str, output_dir: Path) -> dict:
    """Run grading (for backward compatibility with Docker-based setup).

    This function is kept for compatibility but delegates to run_automated_checks
    when no Docker is available.
    """
    logger.info("[%s] Starting native grading (no Docker)...", task_id)

    # Create a temporary workspace for grading
    workspace = Path(tempfile.mkdtemp(prefix=f"grading_{task_id}_"))

    try:
        scores = run_automated_checks(
            automated_checks=automated_checks,
            workspace=workspace,
        )

        score_path = output_dir / "score.json"
        score_path.parent.mkdir(parents=True, exist_ok=True)
        score_path.write_text(json.dumps(scores, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("[%s] Grading results written to → %s", task_id, score_path)
        return scores

    finally:
        import shutil
        shutil.rmtree(workspace, ignore_errors=True)


def format_scores(task_id: str, scores: dict) -> str:
    """Format scores for display."""
    if "error" in scores:
        return f"[{task_id}] Grading error: {scores['error']}"
    lines = [f"\n{'='*60}", f"  {task_id}", f"{'='*60}"]

    for k, v in scores.items():
        if isinstance(v, (int, float)):
            bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
            lines.append(f"  {bar} {v:.2f}  {k}")

    lines.append("=" * 60)
    return "\n".join(lines)


def print_summary(results: list[dict], category: str, output_dir: Path, model_name: str) -> None:
    """Print per-category summary."""
    print(f"\n{'#'*60}")
    print(f"  Summary Report — {category}")
    print(f"{'#'*60}")

    all_scores: dict[str, float] = {}
    for r in results:
        task_id = r["task_id"]
        if r.get("error"):
            print(f"  ✗ {task_id}: {r['error']}")
            continue
        scores = r.get("scores", {})
        if not scores:
            print(f"  - {task_id}: No scores")
            continue
        if "error" in scores:
            print(f"  ✗ {task_id}: Grading error {scores['error']}")
            continue
        numeric_dict = {k: v for k, v in scores.items() if isinstance(v, (int, float))}

        if not numeric_dict:
            print(f"  - {task_id}: No valid numeric scores")
            continue

        avg = sum(numeric_dict.values()) / len(numeric_dict)
        print(f"  ✓ {task_id}: avg {avg:.2f}  ({len(numeric_dict)} items)")

        final_score_val = numeric_dict.get("overall_score", avg)
        all_scores[task_id] = final_score_val

    if all_scores:
        print(f"\n  Final scores per task:")
        for k, score in sorted(all_scores.items()):
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            print(f"    {bar} {score:.2f}  {k}")

    summary_path = output_dir / category / f"summary_{model_name}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n  Summary written to → {summary_path}")
    print("#" * 60)


def extract_usage_from_jsonl(jsonl_path: Path) -> dict:
    """Extract usage statistics from JSONL transcript file."""
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "request_count": 0,
    }
    if not jsonl_path.exists():
        return totals

    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "message":
            continue
        msg = entry.get("message", {})
        if msg.get("role") != "assistant":
            continue
        totals["request_count"] += 1
        usage = msg.get("usage", {})
        totals["input_tokens"] += usage.get("input", 0)
        totals["output_tokens"] += usage.get("output", 0)
        totals["cache_read_tokens"] += usage.get("cacheRead", 0)
        totals["cache_write_tokens"] += usage.get("cacheWrite", 0)
        totals["total_tokens"] += usage.get("totalTokens", 0)
        cost = usage.get("cost", {})
        totals["cost_usd"] += cost.get("total", 0.0)
    totals["cost_usd"] = round(totals["cost_usd"], 6)
    return totals


def print_global_summary(results: list[dict], output_dir: Path, model_name: str) -> None:
    """Print global summary across all categories."""
    print(f"\n{'#'*60}")
    print(f"  Global Summary Report — ALL CATEGORIES")
    print(f"{'#'*60}")

    all_scores: list[float] = []
    for r in results:
        if r.get("error"):
            continue
        scores = r.get("scores", {})
        if not scores or "error" in scores:
            continue
        numeric = {k: v for k, v in scores.items() if isinstance(v, (int, float))}
        if not numeric:
            continue
        final = numeric.get("overall_score", sum(numeric.values()) / len(numeric))
        all_scores.append(final)

    global_avg = 0.0
    if all_scores:
        global_avg = sum(all_scores) / len(all_scores)
        bar = "█" * int(global_avg * 10) + "░" * (10 - int(global_avg * 10))
        print(f"\n  Completed tasks: {len(all_scores)} / {len(results)}")
        print(f"  Global average: {bar} {global_avg:.4f}")
    else:
        print("  No valid scoring data")

    total_out_tok = sum(r.get("usage", {}).get("output_tokens", 0) for r in results)
    total_cost = sum(r.get("usage", {}).get("cost_usd", 0.0) for r in results)
    print(f"  Total output tokens: {total_out_tok}   Total cost: ${total_cost:.4f}")

    summary_path = output_dir / f"summary_all_{model_name}.json"
    summary_path.write_text(
        json.dumps(
            {
                "global_avg": global_avg if all_scores else None,
                "task_count": len(all_scores),
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\n  Global summary written to → {summary_path}")
    print("#" * 60)
