"""CLI entry point — installed as `clawevalkit` command via pyproject.toml.

This is a thin wrapper that delegates to run.py's main() function.
Both entry points share identical functionality.
"""
import sys
from pathlib import Path


def main():
    """Delegate to run.py main function."""
    # Add project root to path
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))

    # Import and call run.py's main
    import run
    run.main()


if __name__ == "__main__":
    main()
