#!/usr/bin/env python3
"""
OpenAI-compatible API adapter for SkillBench.

替代 openai_adapter.py，使用 OpenAI-compatible /chat/completions 端点
而非 OpenAI Responses API。

环境变量:
  OPENAI_API_KEY          — API key
  OPENAI_API_URL          — API base URL (e.g. https://openrouter.ai/api/v1)
  SKILLBENCH_AGENT_MODEL  — model name (e.g. anthropic/claude-sonnet-4.6)
  SKILLBENCH_TASK_PATH    — task directory (auto-set by harness)
  SKILLBENCH_REPO_PATH    — workspace directory (auto-set by harness)
  SKILLBENCH_SKILL_PATH   — optional skill directory
"""
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
import ssl


def _read_file(path: pathlib.Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _extract_diff(text: str) -> str:
    """从 LLM 回复中提取 diff/patch 内容。"""
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


def _extract_file_content(text: str) -> dict[str, str]:
    """从 LLM 回复中提取文件内容块（fallback: 当 diff 格式失败时直接写文件）。

    返回 {文件路径: 文件内容} 字典。支持以下格式：
    - ```python\n# filename.py\ncontent\n```
    - ```filename.py\ncontent\n```
    """
    files = {}
    # 匹配 ```language 或 ```filename 代码块
    blocks = re.findall(r"```(?:python|javascript|typescript|java|go|rust|)?\n(.*?)```", text, re.DOTALL)
    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        # 检查第一行是否像文件名（如 "# utils.py" 或 "// main.go"）
        first = lines[0].strip()
        fname = None
        if re.match(r"^#\s+\S+\.\w+$", first):
            fname = first.lstrip("# ").strip()
            content = "\n".join(lines[1:])
        elif re.match(r"^//\s+\S+\.\w+$", first):
            fname = first.lstrip("/ ").strip()
            content = "\n".join(lines[1:])
        elif re.match(r"^\S+\.\w+$", first) and len(first) < 80:
            fname = first
            content = "\n".join(lines[1:])
        if fname:
            files[fname] = content
    return files


def _apply_patch(diff_text: str, repo_path: pathlib.Path, full_response: str = "") -> None:
    """尝试 apply patch，失败时 fallback 到直接写文件内容。"""
    if not shutil.which("patch"):
        raise RuntimeError("patch binary not found in PATH")

    # 先尝试 p1
    p_level = 1 if re.search(r"^---\s+a/", diff_text, re.MULTILINE) else 0
    proc = subprocess.run(
        ["patch", f"-p{p_level}"],
        input=diff_text,
        text=True,
        cwd=repo_path,
        capture_output=True,
    )
    if proc.returncode == 0:
        return

    # p1 失败，尝试 p0
    if p_level == 1:
        proc = subprocess.run(
            ["patch", "-p0"],
            input=diff_text,
            text=True,
            cwd=repo_path,
            capture_output=True,
        )
        if proc.returncode == 0:
            return

    # Patch 都失败了，尝试从完整回复中提取文件内容直接写入
    if full_response:
        files = _extract_file_content(full_response)
        if files:
            for fname, content in files.items():
                # 在 repo 中查找匹配的文件
                target = repo_path / fname
                if not target.exists():
                    # 尝试在子目录中找
                    candidates = list(repo_path.rglob(pathlib.Path(fname).name))
                    if candidates:
                        target = candidates[0]
                if target.exists() or "/" not in fname:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content + "\n", encoding="utf-8")
            return

    raise RuntimeError(f"patch failed: {proc.stderr.strip()}")


def build_prompt() -> str:
    """构建发送给 LLM 的 prompt，包含 TASK.md 和可选的 SKILL.md。"""
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

    # 同时读取 repo 中的源文件，帮助 LLM 理解代码上下文
    repo_path = os.environ.get("SKILLBENCH_REPO_PATH")
    repo_context = ""
    if repo_path:
        repo_dir = pathlib.Path(repo_path)
        if repo_dir.exists():
            for ext in ("*.py", "*.js", "*.ts", "*.java", "*.go", "*.rs"):
                for f in sorted(repo_dir.rglob(ext)):
                    rel = f.relative_to(repo_dir)
                    # 跳过 test 文件和隐藏文件
                    if "test" in str(rel).lower() or str(rel).startswith("."):
                        continue
                    content = _read_file(f)
                    if content and len(content) < 5000:
                        repo_context += f"\n\n--- {rel} ---\n{content}"

    prompt_parts = [
        "You are an autonomous code agent.",
        "Work in the current repository.",
        "Return a unified diff patch only. Do not include explanations.",
        "Use file paths relative to the repository root.",
        "",
        "Task instructions:",
        task_text,
    ]
    if repo_context:
        prompt_parts.extend(["", "Current source files:", repo_context])
    if skill_text:
        prompt_parts.extend(["", "Skill context:", skill_text])
    return "\n".join([p for p in prompt_parts if p is not None])


def _build_ssl_context():
    """构建 SSL context，兼容各种环境。"""
    ctx = ssl.create_default_context()
    try:
        ctx.load_default_certs()
    except Exception:
        pass
    # ARK API 可能需要跳过证书验证
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_API_URL", "https://openrouter.ai/api/v1")
    model = os.environ.get("SKILLBENCH_AGENT_MODEL")
    max_tokens = int(os.environ.get("SKILLBENCH_AGENT_MAX_TOKENS", "4096"))

    if not api_key:
        print("OPENAI_API_KEY is required", file=sys.stderr)
        return 2
    if not model:
        print("SKILLBENCH_AGENT_MODEL is required", file=sys.stderr)
        return 2

    # 构建 /chat/completions 请求（ARK API 格式）
    prompt = build_prompt()
    api_url = f"{api_base.rstrip('/')}/chat/completions"

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": "You are an expert code agent. Given a task, analyze the source code and return a unified diff patch to fix the issue.\n\nIMPORTANT: Your response must be a valid unified diff wrapped in ```diff ... ``` fences. Example:\n```diff\n--- a/utils.py\n+++ b/utils.py\n@@ -5,3 +5,3 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n```\nReturn ONLY the diff block. No explanations before or after."},
            {"role": "user", "content": prompt},
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    request_timeout = float(os.environ.get("SKILLBENCH_AGENT_REQUEST_TIMEOUT", "120"))
    retries = int(os.environ.get("SKILLBENCH_AGENT_RETRIES", "2"))
    backoff_base = float(os.environ.get("SKILLBENCH_AGENT_BACKOFF", "1.5"))

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    body = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=request_timeout, context=_build_ssl_context()) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:
            if attempt >= retries:
                print(f"ARK API request failed: {exc}", file=sys.stderr)
                return 2
            sleep_for = backoff_base * (2 ** attempt)
            time.sleep(sleep_for)

    # 从 chat completions 响应中提取文本
    text = ""
    try:
        choices = body.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            text = message.get("content", "")
    except Exception:
        pass

    if not text:
        print("No response text from ARK API", file=sys.stderr)
        return 2

    diff_text = _extract_diff(text)
    try:
        _apply_patch(diff_text, pathlib.Path.cwd(), full_response=text)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
