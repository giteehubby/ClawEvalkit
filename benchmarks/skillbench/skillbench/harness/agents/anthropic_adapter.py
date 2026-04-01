#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request

from harness.agents.http_utils import build_ssl_context

def _read_file(path: pathlib.Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _extract_diff(text: str) -> str:
    fenced = re.search(r"```(?:diff|patch)\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    lines = text.strip().splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.startswith(("diff --git", "--- ", "*** ")):
            start = idx
            break
    if start is None:
        return text.strip()
    diff_text = "\n".join(lines[start:]).strip()
    diff_text = re.sub(r"\n```$", "", diff_text)
    return diff_text.strip()


def _apply_patch(diff_text: str, repo_path: pathlib.Path) -> None:
    if not shutil.which("patch"):
        raise RuntimeError("patch binary not found in PATH")
    p_level = 1 if re.search(r"^---\\s+a/", diff_text, re.MULTILINE) else 0
    proc = subprocess.run(
        ["patch", f"-p{p_level}"],
        input=diff_text,
        text=True,
        cwd=repo_path,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"patch failed: {proc.stderr.strip()}")


def build_prompt() -> str:
    task_path = os.environ.get("SKILLBENCH_TASK_PATH")
    skill_path = os.environ.get("SKILLBENCH_SKILL_PATH")
    include_skill_body = os.environ.get("SKILLBENCH_INCLUDE_SKILL_BODY") == "1"

    task_text = ""
    if task_path:
        task_md = pathlib.Path(task_path) / "TASK.md"
        task_text = _read_file(task_md)

    skill_text = ""
    if include_skill_body and skill_path:
        skill_md = pathlib.Path(skill_path) / "SKILL.md"
        skill_text = _read_file(skill_md)

    prompt_parts = [
        "You are an autonomous code agent.",
        "Work in the current repository.",
        "Return a unified diff patch only. Do not include explanations.",
        "Use file paths relative to the repository root.",
        "",
        "Task instructions:",
        task_text,
    ]
    if skill_text:
        prompt_parts.extend(["", "Skill context:", skill_text])
    return "\n".join([p for p in prompt_parts if p is not None])


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    api_url = os.environ.get("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")
    version = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")
    model = os.environ.get("SKILLBENCH_AGENT_MODEL")
    max_tokens = int(os.environ.get("SKILLBENCH_AGENT_MAX_TOKENS", "1024"))
    system_prompt = os.environ.get("SKILLBENCH_AGENT_SYSTEM")

    if not api_key:
        print("ANTHROPIC_API_KEY is required", file=sys.stderr)
        return 2
    if not model:
        print("SKILLBENCH_AGENT_MODEL is required", file=sys.stderr)
        return 2

    prompt = build_prompt()
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        payload["system"] = system_prompt

    request_timeout = float(os.environ.get("SKILLBENCH_AGENT_REQUEST_TIMEOUT", "120"))
    retries = int(os.environ.get("SKILLBENCH_AGENT_RETRIES", "2"))
    backoff_base = float(os.environ.get("SKILLBENCH_AGENT_BACKOFF", "1.5"))

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": version,
        },
        method="POST",
    )

    body = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=request_timeout, context=build_ssl_context()) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:
            if attempt >= retries:
                print(f"Anthropic request failed: {exc}", file=sys.stderr)
                return 2
            sleep_for = backoff_base * (2 ** attempt)
            time.sleep(sleep_for)

    content = body.get("content") or []
    text = content[0].get("text", "") if content else ""
    if not text:
        print("No response text from Anthropic API", file=sys.stderr)
        return 2

    diff_text = _extract_diff(text)
    try:
        _apply_patch(diff_text, pathlib.Path.cwd())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
