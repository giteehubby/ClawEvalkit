#!/usr/bin/env python3
"""
Extract failure cases from experiment results and copy their transcripts.
Also generates error classification prompts for manual analysis.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
_root_dir = script_dir.parent
sys.path.insert(0, str(_root_dir))


def extract_failures(exp_dir: Path, threshold: float = 0.7):
    """Extract failure cases from experiment results.

    Args:
        exp_dir: Experiment directory
        threshold: Score threshold below which a task is considered failed
    """
    results_dir = exp_dir / "results"
    transcripts_dir = exp_dir / "transcripts"
    failure_dir = exp_dir / "failure_cases"
    failure_dir.mkdir(exist_ok=True)

    # Ensure transcripts subdirectory exists
    failure_transcripts_dir = failure_dir / "transcripts"
    failure_transcripts_dir.mkdir(exist_ok=True)

    all_failures = []

    for result_file in results_dir.glob("*.json"):
        if result_file.name == "transcripts":
            continue

        try:
            with open(result_file) as f:
                data = json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Could not parse {result_file}")
            continue

        benchmark = data.get("benchmark", result_file.stem)
        task_scores = data.get("task_scores", {})

        failures = []
        for task_id, score_data in task_scores.items():
            # Different benchmarks have different score structures
            if isinstance(score_data, dict):
                mean_score = score_data.get("mean", 1.0)
                # For benchmarks with 'passed' field
                if "passed" in score_data and isinstance(score_data.get("passed"), bool):
                    if not score_data["passed"]:
                        failures.append((task_id, score_data))
                # For benchmarks with score-based pass/fail
                elif mean_score < threshold:
                    failures.append((task_id, score_data))
            elif isinstance(score_data, (int, float)):
                # Simple score value
                if score_data < threshold:
                    failures.append((task_id, {"mean": score_data}))

        if failures:
            print(f"\n{benchmark}: {len(failures)} failures")
            for task_id, score_data in failures:
                mean_score = score_data.get("mean", 0)
                print(f"  {task_id}: {mean_score:.2f}")
                all_failures.append({
                    "benchmark": benchmark,
                    "task_id": task_id,
                    "score": mean_score,
                    "score_data": score_data
                })

                # Copy transcript
                _copy_transcript(transcripts_dir, failure_transcripts_dir, benchmark, task_id)

    # Save failures manifest
    manifest = f"""# Failure Cases Manifest

Total failures across all benchmarks: {len(all_failures)}

## Failure Summary by Benchmark
"""
    by_benchmark = {}
    for f in all_failures:
        bm = f["benchmark"]
        if bm not in by_benchmark:
            by_benchmark[bm] = []
        by_benchmark[bm].append(f)

    for bm, cases in sorted(by_benchmark.items()):
        manifest += f"\n### {bm}: {len(cases)} failures\n"
        manifest += "| Task ID | Score |\n"
        manifest += "|---------|-------|\n"
        for c in sorted(cases, key=lambda x: x["task_id"]):
            manifest += f"| {c['task_id']} | {c['score']:.2f} |\n"

    manifest += f"\n## All Failures\n"
    manifest += "| Benchmark | Task ID | Score |\n"
    manifest += "|-----------|---------|-------|\n"
    for f in sorted(all_failures, key=lambda x: (x["benchmark"], x["task_id"])):
        manifest += f"| {f['benchmark']} | {f['task_id']} | {f['score']:.2f} |\n"

    (failure_dir / "manifest.md").write_text(manifest)
    print(f"\nManifest saved to {failure_dir / 'manifest.md'}")

    # Save JSON version
    with open(failure_dir / "failures.json", "w") as f:
        json.dump(all_failures, f, indent=2)

    return all_failures


def _copy_transcript(transcripts_dir: Path, failure_transcripts_dir: Path, benchmark: str, task_id: str):
    """Copy transcript for a failed task."""
    # Try different naming patterns
    patterns = [
        f"{task_id}_0.jsonl",
        f"{benchmark}_{task_id}_0.jsonl",
        f"{benchmark.replace('-', '_')}_{task_id}_0.jsonl",
    ]

    # Also try without _0 suffix
    patterns.extend([
        f"{task_id}.jsonl",
        f"{benchmark}_{task_id}.jsonl",
    ])

    for pattern in patterns:
        transcript_path = transcripts_dir / pattern
        if transcript_path.exists():
            dest = failure_transcripts_dir / f"{benchmark}_{task_id}_0.jsonl"
            shutil.copy2(transcript_path, dest)
            return

    # Try to find by searching
    for tf in transcripts_dir.glob(f"*{task_id}*0.jsonl"):
        dest = failure_transcripts_dir / f"{benchmark}_{task_id}_0.jsonl"
        shutil.copy2(tf, dest)
        return

    # Print warning but don't fail
    print(f"  Warning: Transcript not found for {benchmark}/{task_id}")


def main():
    parser = argparse.ArgumentParser(description="Extract failure cases from experiment")
    parser.add_argument("exp_dir", type=Path, help="Experiment directory")
    parser.add_argument("--threshold", type=float, default=0.7, help="Score threshold (default: 0.7)")
    args = parser.parse_args()

    extract_failures(args.exp_dir, args.threshold)


if __name__ == "__main__":
    main()
