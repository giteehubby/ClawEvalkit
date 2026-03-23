#!/usr/bin/env python3
"""
SkillBench Verification CLI

Verify scorecard signatures from the command line.

Usage:
    skillbench verify https://skillbench.dev/s/abc123
    python3 -m harness.verify_cli https://skillbench.dev/s/abc123
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.request
from urllib.parse import urljoin, urlparse


def fetch_json(url: str) -> dict:
    """Fetch and parse JSON from URL."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verify_scorecard(scorecard_url: str, keys_url: str | None = None) -> dict:
    """
    Verify a scorecard's signature.

    Args:
        scorecard_url: URL to the scorecard JSON
        keys_url: URL to keys.json (defaults to /.well-known/keys.json on same host)

    Returns:
        dict with verification results
    """
    # Fetch scorecard
    scorecard = fetch_json(scorecard_url)

    # Determine keys URL
    if not keys_url:
        parsed = urlparse(scorecard_url)
        keys_url = f"{parsed.scheme}://{parsed.netloc}/.well-known/keys.json"

    # Fetch keys
    keys_data = fetch_json(keys_url)

    # Check signature exists
    signature = scorecard.get("signature")
    if not signature:
        return {
            "valid": False,
            "error": "No signature present in scorecard",
        }

    # Find matching key
    key_id = signature.get("key_id")
    matching_key = None
    for key in keys_data.get("keys", []):
        if key.get("key_id") == key_id:
            matching_key = key
            break

    if not matching_key:
        return {
            "valid": False,
            "error": f"Key '{key_id}' not found in published keys",
        }

    if matching_key.get("algorithm") != signature.get("algorithm"):
        return {
            "valid": False,
            "error": f"Algorithm mismatch: key uses {matching_key.get('algorithm')}, signature uses {signature.get('algorithm')}",
        }

    # Verify signature using cryptography library
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        # Decode public key
        public_key_bytes = base64.b64decode(matching_key["public_key"])
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

        # Reconstruct signed message
        message = f"{signature['payload_digest']}|{signature['signed_at']}".encode("utf-8")
        signature_bytes = base64.b64decode(signature["signature"])

        # Verify
        public_key.verify(signature_bytes, message)

        return {
            "valid": True,
            "key_id": key_id,
            "algorithm": signature.get("algorithm"),
            "signed_at": signature.get("signed_at"),
            "payload_digest": signature.get("payload_digest"),
            "skill": scorecard.get("skill", {}).get("name"),
            "suite": f"{scorecard.get('suite', {}).get('id')} v{scorecard.get('suite', {}).get('version')}",
            "runner_version": scorecard.get("run", {}).get("runner_version"),
        }

    except Exception as e:
        return {
            "valid": False,
            "error": f"Signature verification failed: {e}",
        }


def main():
    parser = argparse.ArgumentParser(
        description="Verify SkillBench scorecard signatures",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s https://skillbench.dev/s/abc123
    %(prog)s ./scorecard.json --keys https://skillbench.dev/.well-known/keys.json
        """,
    )
    parser.add_argument(
        "scorecard",
        help="URL or path to scorecard JSON",
    )
    parser.add_argument(
        "--keys",
        help="URL to keys.json (defaults to /.well-known/keys.json on scorecard host)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted text",
    )
    args = parser.parse_args()

    # Handle local files
    scorecard_url = args.scorecard
    if not scorecard_url.startswith(("http://", "https://")):
        # Local file - read directly
        import pathlib
        path = pathlib.Path(scorecard_url)
        if not path.exists():
            print(f"Error: File not found: {scorecard_url}", file=sys.stderr)
            return 1
        scorecard = json.loads(path.read_text())

        # For local files, we need a keys URL
        if not args.keys:
            print("Error: --keys required for local scorecard files", file=sys.stderr)
            return 1

        # Inline verification for local files
        from harness.signing import verify_signature
        is_valid, message = verify_signature(scorecard)
        result = {
            "valid": is_valid,
            "message": message,
            "skill": scorecard.get("skill", {}).get("name"),
            "suite": f"{scorecard.get('suite', {}).get('id')} v{scorecard.get('suite', {}).get('version')}",
        }
    else:
        result = verify_scorecard(scorecard_url, args.keys)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("valid"):
            print("✓ Signature valid")
            print()
            print(f"  Skill:    {result.get('skill', 'Unknown')}")
            print(f"  Suite:    {result.get('suite', 'Unknown')}")
            print(f"  Runner:   {result.get('runner_version', 'Unknown')}")
            print(f"  Key ID:   {result.get('key_id', 'Unknown')}")
            print(f"  Signed:   {result.get('signed_at', 'Unknown')}")
        else:
            print("✗ Verification failed")
            print()
            print(f"  Error: {result.get('error', 'Unknown error')}")

    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    sys.exit(main())
