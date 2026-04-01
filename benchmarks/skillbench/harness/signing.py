#!/usr/bin/env python3
"""
Scorecard signing infrastructure for SkillBench.

Provides Ed25519 signatures for scorecard verification by marketplaces.
"""
from __future__ import annotations

import base64
import hashlib
import json
import pathlib
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Key storage location
KEYS_DIR = pathlib.Path(__file__).resolve().parent.parent / "keys"
PRIVATE_KEY_PATH = KEYS_DIR / "signing.key"
PUBLIC_KEY_PATH = KEYS_DIR / "signing.pub"

# Key identifier (changes if key is rotated)
KEY_ID = "skillbench-v1"


def ensure_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Ensure signing keypair exists, generating if needed."""
    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        # Load existing keys
        private_key = serialization.load_pem_private_key(
            PRIVATE_KEY_PATH.read_bytes(),
            password=None,
        )
        public_key = serialization.load_pem_public_key(
            PUBLIC_KEY_PATH.read_bytes(),
        )
        return private_key, public_key

    # Generate new keypair
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Save private key (PEM format)
    PRIVATE_KEY_PATH.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    # Restrict permissions
    PRIVATE_KEY_PATH.chmod(0o600)

    # Save public key (PEM format)
    PUBLIC_KEY_PATH.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    return private_key, public_key


def get_public_key_b64() -> str:
    """Get the public key as base64-encoded raw bytes."""
    _, public_key = ensure_keypair()
    raw_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw_bytes).decode("ascii")


def compute_payload_digest(scorecard: dict) -> str:
    """
    Compute SHA-256 digest of the signable payload.

    The payload covers the critical fields that define the evaluation:
    - skill artifact digest
    - suite id/version
    - runner version
    - baseline type/digest
    - metrics block
    - artifacts digests
    """
    payload = {
        "skill": {
            "id": scorecard.get("skill", {}).get("id"),
            "artifact_digest": scorecard.get("skill", {}).get("artifact_digest"),
        },
        "suite": {
            "id": scorecard.get("suite", {}).get("id"),
            "version": scorecard.get("suite", {}).get("version"),
        },
        "run": {
            "runner_version": scorecard.get("run", {}).get("runner_version"),
        },
        "baseline": scorecard.get("baseline"),
        "metrics": scorecard.get("metrics"),
        "artifacts": {
            "profile_digest": scorecard.get("artifacts", {}).get("profile_digest"),
            "traces_digest": scorecard.get("artifacts", {}).get("traces_digest"),
        },
    }

    # Canonical JSON (sorted keys, no whitespace)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sign_scorecard(scorecard: dict) -> dict:
    """
    Sign a scorecard and return it with signature block added.

    The signature block contains:
    - key_id: Identifier for the signing key
    - algorithm: "Ed25519"
    - signed_at: ISO timestamp
    - payload_digest: SHA-256 of signable fields
    - signature: Base64-encoded Ed25519 signature
    """
    private_key, _ = ensure_keypair()

    payload_digest = compute_payload_digest(scorecard)
    signed_at = datetime.now(timezone.utc).isoformat()

    # Sign the payload digest
    message = f"{payload_digest}|{signed_at}".encode("utf-8")
    signature_bytes = private_key.sign(message)
    signature_b64 = base64.b64encode(signature_bytes).decode("ascii")

    # Add signature block
    scorecard_with_sig = dict(scorecard)
    scorecard_with_sig["signature"] = {
        "key_id": KEY_ID,
        "algorithm": "Ed25519",
        "signed_at": signed_at,
        "payload_digest": payload_digest,
        "signature": signature_b64,
    }

    return scorecard_with_sig


def verify_signature(scorecard: dict) -> tuple[bool, str]:
    """
    Verify a scorecard signature.

    Returns (is_valid, message).
    """
    sig_block = scorecard.get("signature")
    if not sig_block:
        return False, "No signature block"

    if sig_block.get("algorithm") != "Ed25519":
        return False, f"Unsupported algorithm: {sig_block.get('algorithm')}"

    # Recompute payload digest
    expected_digest = compute_payload_digest(scorecard)
    if sig_block.get("payload_digest") != expected_digest:
        return False, "Payload digest mismatch (scorecard may have been modified)"

    # Verify signature
    try:
        _, public_key = ensure_keypair()
        message = f"{sig_block['payload_digest']}|{sig_block['signed_at']}".encode("utf-8")
        signature_bytes = base64.b64decode(sig_block["signature"])
        public_key.verify(signature_bytes, message)
        return True, "Signature valid"
    except Exception as e:
        return False, f"Signature verification failed: {e}"


def get_well_known_keys() -> dict:
    """
    Generate the /.well-known/keys.json response.

    This allows marketplaces to fetch public keys for verification.
    """
    public_key_b64 = get_public_key_b64()

    return {
        "keys": [
            {
                "key_id": KEY_ID,
                "algorithm": "Ed25519",
                "public_key": public_key_b64,
                "created_at": "2026-01-25T00:00:00Z",  # Could track actual creation
                "status": "active",
            }
        ],
        "verification_doc": "https://skillbench.dev/docs/verification",
    }


if __name__ == "__main__":
    # Test key generation and signing
    ensure_keypair()
    print(f"Public key: {get_public_key_b64()}")

    # Test with sample scorecard
    sample = {
        "skill": {"id": "test-skill", "artifact_digest": "abc123"},
        "suite": {"id": "core-bugfix", "version": "1.0.0"},
        "run": {"runner_version": "0.2.0"},
        "baseline": {"type": "no-skill"},
        "metrics": {"reliability": {"delta": 0.1}},
        "artifacts": {"profile_digest": "def456"},
    }

    signed = sign_scorecard(sample)
    print(f"Signature: {signed['signature']['signature'][:40]}...")

    valid, msg = verify_signature(signed)
    print(f"Verification: {valid} - {msg}")
