"""Deterministic fingerprints for persisted planning previews."""

import hashlib
import json


def fingerprint(value):
    """Return a stable digest for JSON-compatible planning evidence."""
    payload = json.dumps(
        value,
        default=str,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
