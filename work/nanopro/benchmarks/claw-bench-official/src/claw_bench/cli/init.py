"""claw-bench init — initialize a new benchmark workspace."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def init_cmd(
    directory: Path = typer.Argument(
        Path("."),
        help="Directory to initialize. Defaults to current directory.",
    ),
    framework: str = typer.Option(
        "openclaw",
        "--framework",
        "-f",
        help="Default framework adapter.",
    ),
    model: str = typer.Option(
        "gpt-4.1",
        "--model",
        "-m",
        help="Default model identifier.",
    ),
) -> None:
    """Initialize a new benchmark workspace with recommended structure."""
    target = directory.resolve()
    target.mkdir(parents=True, exist_ok=True)

    created = []

    # Create config file
    config_path = target / "bench.json"
    if not config_path.exists():
        config = {
            "framework": framework,
            "model": model,
            "skills": "vanilla",
            "runs": 5,
            "parallel": 4,
            "timeout": 300,
            "profile": "general",
        }
        config_path.write_text(json.dumps(config, indent=2))
        created.append("bench.json")

    # Create results directory
    results_dir = target / "results"
    if not results_dir.exists():
        results_dir.mkdir()
        (results_dir / ".gitkeep").touch()
        created.append("results/")

    # Create logs directory
    logs_dir = target / "logs"
    if not logs_dir.exists():
        logs_dir.mkdir()
        (logs_dir / ".gitkeep").touch()
        created.append("logs/")

    # Create a sample run script
    run_script = target / "run.sh"
    if not run_script.exists():
        run_script.write_text(
            "#!/bin/bash\n"
            "# Claw Bench — run the benchmark\n"
            "# Your AI agent reads skill.md and completes tasks directly.\n"
            "set -euo pipefail\n\n"
            "echo 'To run ClawBench, have your AI agent read:'\n"
            "echo '  https://clawbench.net/skill.md'\n"
            "echo ''\n"
            "echo 'Or submit existing results:'\n"
            "echo '  claw-bench submit ./results/latest'\n"
        )
        run_script.chmod(0o755)
        created.append("run.sh")

    if created:
        console.print(f"[bold green]Initialized benchmark workspace at {target}[/]\n")
        console.print("Created:")
        for f in created:
            console.print(f"  [cyan]{f}[/]")
        console.print(
            "\nHave your AI agent read [bold]https://clawbench.net/skill.md[/] to start."
        )
    else:
        console.print(f"[bold yellow]Workspace already initialized at {target}[/]")
