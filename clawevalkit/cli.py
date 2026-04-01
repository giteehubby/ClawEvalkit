"""CLI entry point — installed as `clawevalkit` command via pyproject.toml."""
import sys
from pathlib import Path


def main():
    """Delegate to run.py logic."""
    # Add project root to path so clawevalkit package is importable
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))

    from .config import load_env, list_models, MODELS
    from .dataset import BENCHMARKS, list_benchmarks
    from .inference import infer_all
    from .summarizer import Summarizer
    from .utils.log import log

    import argparse
    parser = argparse.ArgumentParser(
        description="ClawEvalKit — 8-Benchmark Agent Evaluation Toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bench", "-b", help="Comma-separated benchmark keys")
    parser.add_argument("--model", "-m", default="claude-sonnet", help="Comma-separated model keys")
    parser.add_argument("--sample", "-s", type=int, default=0, help="Sample N tasks per bench")
    parser.add_argument("--summary", action="store_true", help="Print summary of existing results")
    parser.add_argument("--list", action="store_true", help="List benchmarks and models")
    parser.add_argument("--force", action="store_true", help="Force re-evaluation")
    parser.add_argument("--env", help="Path to .env file")
    args = parser.parse_args()

    load_env(args.env)

    if args.list:
        print("\n  Available Benchmarks:")
        for key, name, count in list_benchmarks():
            print(f"    {key:22s} {name:25s} ({count} tasks)")
        print("\n  Available Models:")
        for key, name, provider in list_models():
            print(f"    {key:22s} {name:25s} [{provider}]")
        print()
        return

    summarizer = Summarizer()
    if args.summary:
        summarizer.summary()
        return

    bench_keys = args.bench.split(",") if args.bench else list(BENCHMARKS.keys())
    model_keys = args.model.split(",") if args.model else ["claude-sonnet"]

    for bk in bench_keys:
        if bk not in BENCHMARKS:
            print(f"Unknown benchmark: {bk}. Use --list.")
            sys.exit(1)
    for mk in model_keys:
        if mk not in MODELS:
            print(f"Unknown model: {mk}. Use --list.")
            sys.exit(1)

    log(f"Config: bench={bench_keys}, models={model_keys}, sample={args.sample or 'all'}")
    infer_all(bench_keys, model_keys, sample=args.sample, force=args.force)
    log("\n")
    summarizer.summary()


if __name__ == "__main__":
    main()
