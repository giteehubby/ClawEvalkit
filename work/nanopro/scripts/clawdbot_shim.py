#!/usr/bin/env python3
"""
Minimal clawdbot-compatible shim backed by NanoBotAgent.

Supported commands:
  clawdbot --version
  clawdbot plugins list
  clawdbot plugins enable <name>
  clawdbot agent --session-id <id> --message <text> [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))


VERSION = "clawdbot-shim 0.1.0 (nanobot-backed)"


def _get_env(name: str, fallback: str = "") -> str:
    return os.environ.get(name, "") or os.environ.get(name.upper(), "") or fallback


def _default_workspace() -> Path:
    root = _get_env("CLAWDBOT_SHIM_WORKSPACE")
    if root:
        path = Path(root)
    else:
        path = Path(tempfile.gettempdir()) / "clawdbot_shim_workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _default_session_store() -> Path:
    root = _get_env("CLAWDBOT_SHIM_SESSION_STORE")
    if root:
        path = Path(root)
    else:
        path = _default_workspace() / ".sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_agent():
    from src.harness.agent.nanobot import NanoBotAgent

    api_url = _get_env("OPENAI_BASE_URL") or _get_env("API_URL")
    api_key = _get_env("OPENAI_API_KEY") or _get_env("API_KEY")
    model = _get_env("MODEL", "gpt-4o-mini")

    return NanoBotAgent(
        model=model,
        api_url=api_url,
        api_key=api_key,
        workspace=_default_workspace(),
        timeout=int(_get_env("CLAW_TIMEOUT", "120")),
        session_store_dir=_default_session_store(),
    )


def _usage_payload(result_content: str, usage: dict[str, int]) -> dict[str, int]:
    output_tokens = usage.get("output_tokens")
    if not output_tokens:
        output_tokens = max(1, len(result_content.split())) if result_content else 0

    return {
        "input": usage.get("input_tokens", 0),
        "output": output_tokens,
        "total": usage.get("total_tokens", usage.get("input_tokens", 0) + output_tokens),
    }


def _format_agent_json(result, model: str) -> dict:
    content = result.content or ""
    payloads = [{"text": content}] if content else []
    usage = _usage_payload(content, result.usage or {})

    return {
        "ok": result.status == "success",
        "result": {
            "payloads": payloads,
            "meta": {
                "agentMeta": {
                    "model": model,
                    "status": result.status,
                    "usage": usage,
                    "workspace": result.workspace,
                    "execution_time": result.execution_time,
                }
            },
        },
        "error": result.error or None,
    }


def _run_agent(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="clawdbot agent", add_help=False)
    parser.add_argument("--session-id", required=False, default="main")
    parser.add_argument("--message", required=True)
    parser.add_argument("--json", action="store_true")

    args, unknown = parser.parse_known_args(argv)
    if unknown:
        print(f"Unsupported arguments for clawdbot agent: {' '.join(unknown)}", file=sys.stderr)
        return 2

    agent = _build_agent()
    model = agent.model
    result = agent.execute(args.message, session_id=args.session_id, workspace=_default_workspace())

    if args.json:
        print(json.dumps(_format_agent_json(result, model), ensure_ascii=False))
    else:
        print(result.content or result.error or "")

    return 0 if result.status == "success" else 1


def _run_plugins(argv: list[str]) -> int:
    if not argv:
        print("Usage: clawdbot plugins <list|enable>", file=sys.stderr)
        return 2

    subcmd = argv[0]
    if subcmd == "list":
        print("tribecode loaded")
        return 0
    if subcmd == "enable":
        plugin_name = argv[1] if len(argv) > 1 else "unknown"
        print(f"{plugin_name} enabled")
        return 0

    print(f"Unsupported plugins command: {subcmd}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Usage: clawdbot <command>", file=sys.stderr)
        return 2

    if argv[0] in {"--version", "version"}:
        print(VERSION)
        return 0

    command = argv[0]
    if command == "agent":
        return _run_agent(argv[1:])
    if command == "plugins":
        return _run_plugins(argv[1:])

    print(f"Unsupported clawdbot command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
