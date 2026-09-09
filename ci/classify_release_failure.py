#!/usr/bin/env python3
"""Classify a failed release lane from its focused log evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

RULES = (
    ("unsupported_configuration", ("websocket-client module is not installed", "browser test dependency")),
    ("documentation_drift", ("documentation freshness", "broken markdown link", "delivery language")),
    ("migration_defect", ("migration", "upgrade failed", "invariant mismatch", "rollback")),
    ("performance_regression", ("performance regression", "query budget exceeded")),
    ("fixture_defect", ("duplicate key value violates unique constraint", "fixture setup")),
    ("test_defect", ("test collection", "test discovery", "no tests were found")),
    ("infrastructure_defect", ("docker is required", "connection refused", "timed out", "no space left")),
    ("product_defect", ("fail:", "error:", "validationerror", "assertionerror")),
)


def classify(log_text: str, lane: str = "") -> str:
    text = log_text.lower()
    if lane == "preflight" and "release workspace contains tracked changes" in text:
        return "unsupported_configuration"
    for classification, patterns in RULES:
        if any(pattern in text for pattern in patterns):
            return classification
    return "unclassified"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--lane", default="")
    args = parser.parse_args()
    text = args.log.read_text(errors="replace") if args.log.is_file() else ""
    print(classify(text, args.lane))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
