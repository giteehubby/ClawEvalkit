#!/usr/bin/env python3
"""
Test script for PinchBench Docker mode.
Usage: python test_docker.py [--sample N] [--parallel P]
"""

import argparse
import os
import sys
from pathlib import Path

# Add ClawEvalKit to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from clawevalkit.dataset.pinchbench import PinchBench


def main():
    parser = argparse.ArgumentParser(description="Test PinchBench Docker mode")
    parser.add_argument("--sample", "-s", type=int, default=1, help="Number of tasks to sample (default: 1)")
    parser.add_argument("--parallel", "-p", type=int, default=1, help="Parallel tasks (default: 1)")
    parser.add_argument("--model", "-m", default="test-model", help="Model key to use")
    args = parser.parse_args()

    # Get API key from environment
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("Warning: OPENROUTER_API_KEY not set")

    # Model config
    config = {
        "name": "Test Model",
        "api_url": "https://openrouter.ai/api/v1",
        "model": "anthropic/claude-3-haiku",
        "provider": "openrouter",
        "api_key": api_key,
    }

    print("=" * 80)
    print("PinchBench Docker Mode Test")
    print("=" * 80)
    print(f"Model: {args.model}")
    print(f"Sample: {args.sample} tasks")
    print(f"Parallel: {args.parallel}")
    print("=" * 80)

    # Run evaluation
    bench = PinchBench(use_docker=True)
    result = bench.evaluate(
        args.model,
        config,
        sample=args.sample,
        parallel=args.parallel,
    )

    print("\n" + "=" * 80)
    print("Results:")
    print("=" * 80)
    print(f"Score: {result.get('score', 0)}")
    print(f"Passed: {result.get('passed', 0)}/{result.get('total', 0)}")

    if "details" in result:
        print("\nTask Details:")
        for detail in result["details"]:
            tid = detail.get("task_id", "unknown")
            status = detail.get("status", "unknown")
            mean = detail.get("mean", 0)
            print(f"  {tid}: status={status}, mean={mean:.4f}")

    print("=" * 80)


if __name__ == "__main__":
    main()
