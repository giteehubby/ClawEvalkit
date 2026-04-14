#!/usr/bin/env python3
"""Run LLM-based error classification on failed agent traces.

Reads prompts from outputs/error_classification_prompts.json,
calls the specified LLM to classify each failure into categories A-F,
and saves results with resume support.

Usage:
    python scripts/run_error_classification.py --model minimax-m2.7 --batch-size 10
    python scripts/run_error_classification.py --model glm-4.7 --batch-size 10
"""

import argparse
import csv
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Ensure project root on sys.path so clawevalkit is importable ──
sys.path.insert(0, str(PROJECT_ROOT))

from clawevalkit.config import load_env, get_model_config

import json as _json
import ssl as _ssl
import urllib.request as _urllib_request
import time as _time


def _call_anthropic_compatible(messages: list, config: dict, max_tokens: int = 4096, timeout: float = 180) -> str:
    """Call Anthropic-compatible /v1/messages API."""
    api_url = f"{config['api_url'].rstrip('/')}/v1/messages"
    payload = {
        "model": config["model"],
        "max_tokens": max_tokens,
        "messages": messages,
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": config["api_key"],
        "anthropic-version": "2023-06-01",
    }
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    req = _urllib_request.Request(
        api_url,
        data=_json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    for attempt in range(3):
        try:
            with _urllib_request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = _json.loads(resp.read().decode("utf-8"))
            # Anthropic response format
            content = body.get("content", [])
            if content:
                return "".join(c.get("text", "") for c in content if c.get("type") == "text")
            return ""
        except Exception as exc:
            if attempt >= 2:
                return f"ERROR: {exc}"
            _time.sleep(2 * (2 ** attempt))
    return ""


def _call_openai_compatible(messages: list, config: dict, max_tokens: int = 4096, timeout: float = 180) -> str:
    """Call OpenAI-compatible /chat/completions API."""
    from clawevalkit.utils.api import call_llm
    return call_llm(messages, config, max_tokens=max_tokens, timeout=timeout)


def _is_anthropic_endpoint(config: dict) -> bool:
    """Detect if the API endpoint is Anthropic-compatible."""
    url = config.get("api_url", "")
    provider = config.get("provider", "")
    return "/anthropic" in url or provider in ("minimax", "glm")


def call_model(messages: list, config: dict, max_tokens: int = 4096, timeout: float = 180) -> str:
    """Auto-detect API type and call the appropriate endpoint."""
    if _is_anthropic_endpoint(config):
        return _call_anthropic_compatible(messages, config, max_tokens, timeout)
    return _call_openai_compatible(messages, config, max_tokens, timeout)

PROMPTS_PATH = PROJECT_ROOT / "outputs/error_classification_prompts.json"
RESULTS_JSON = PROJECT_ROOT / "outputs/error_classification_results.json"
RESULTS_CSV = PROJECT_ROOT / "outputs/error_classification_results.csv"

LABEL_RE = re.compile(r"\\boxed\{([A-F])\}")


def extract_label(text: str) -> str:
    """Extract classification label from LLM response."""
    m = LABEL_RE.search(text)
    if m:
        return m.group(1)
    # Fallback: standalone uppercase letter A-F
    m = re.search(r"\b([A-F])\b", text)
    if m:
        return m.group(1)
    return "UNPARSED"


def load_prompts() -> list[dict]:
    with open(PROMPTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_existing_results() -> dict:
    """Load existing results keyed by (bench, task_id)."""
    if not RESULTS_JSON.exists():
        return {}
    with open(RESULTS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return {(r["bench"], r["task_id"]): r for r in data}


def save_results(results: list[dict]):
    """Save results to JSON and CSV."""
    # JSON
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # CSV
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["bench", "task_id", "score", "classification"])
        for r in results:
            writer.writerow([r["bench"], r["task_id"], r["score"], r.get("classification", "")])

    print(f"  Saved {len(results)} results -> {RESULTS_JSON.name} & {RESULTS_CSV.name}")


def main():
    parser = argparse.ArgumentParser(description="LLM error classification")
    parser.add_argument("--model", required=True, help="Model key (e.g. minimax-m2.7, glm-4.7)")
    parser.add_argument("--batch-size", type=int, default=10, help="Save every N completions")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max tokens per request")
    parser.add_argument("--retry-unparsed", action="store_true", help="Retry UNPARSED results (e.g. due to network errors)")
    args = parser.parse_args()

    # Load env & config
    load_env()
    try:
        config = get_model_config(args.model)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Load data
    prompts = load_prompts()
    print(f"Loaded {len(prompts)} prompts from {PROMPTS_PATH.name}")

    existing = load_existing_results()
    print(f"Found {len(existing)} existing results (will skip those)")

    # Build results list from existing
    results = list(existing.values())
    done_keys = set(existing.keys())

    # If --retry-unparsed, treat UNPARSED results as needing retry
    if args.retry_unparsed:
        unparsed_keys = {(r["bench"], r["task_id"]) for r in existing.values() if r.get("classification") == "UNPARSED"}
        print(f"  --retry-unparsed: will retry {len(unparsed_keys)} UNPARSED tasks")
        done_keys -= unparsed_keys
        # Remove UNPARSED entries from results list; will be re-added with fresh classification
        results = [r for r in results if (r["bench"], r["task_id"]) not in unparsed_keys]

    # Filter out already-done tasks
    todo = [p for p in prompts if (p["bench"], p["task_id"]) not in done_keys]
    print(f"Remaining: {len(todo)} tasks to classify with {args.model}")

    if not todo:
        print("Nothing to do. Exiting.")
        return

    # Graceful Ctrl+C handling
    interrupted = False

    def _sigint_handler(sig, frame):
        nonlocal interrupted
        if interrupted:
            print("\nForce exit.")
            sys.exit(1)
        interrupted = True
        print("\n\nCtrl+C caught — saving progress and exiting gracefully...")
        save_results(results)
        sys.exit(0)

    signal.signal(signal.SIGINT, _sigint_handler)

    # Progress tracking
    total = len(todo)
    batch_count = 0

    for i, item in enumerate(todo, 1):
        bench, tid = item["bench"], item["task_id"]
        prompt_text = item["prompt_for_llm"]
        print(f"[{i}/{total}] {bench}/{tid} ...", end=" ", flush=True)

        messages = [{"role": "user", "content": prompt_text}]
        t0 = time.time()

        raw_response = call_model(messages, config, max_tokens=args.max_tokens, timeout=180)
        elapsed = time.time() - t0

        label = extract_label(raw_response)
        print(f"{label} ({elapsed:.1f}s)")

        result = {
            **item,
            "classification": label,
            "raw_response": raw_response,
            "extracted_label": label,
        }
        # Remove the long prompt to keep JSON compact
        result.pop("prompt_for_llm", None)

        results.append(result)
        done_keys.add((bench, tid))
        batch_count += 1

        # Periodic save
        if batch_count >= args.batch_size:
            save_results(results)
            batch_count = 0

    # Final save
    if not interrupted:
        save_results(results)
        print(f"\nDone! {len(results)} results total.")

        # Summary stats
        from collections import Counter
        labels = Counter(r.get("classification", "?") for r in results)
        print("\nClassification distribution:")
        for label, count in sorted(labels.items()):
            print(f"  {label}: {count}")


if __name__ == "__main__":
    main()
