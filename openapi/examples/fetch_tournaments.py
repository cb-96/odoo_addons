#!/usr/bin/env python3
"""
fetch_tournaments.py — Example consumer for the Sports Federation public competition feed.

Usage:
    python3 fetch_tournaments.py --base-url https://federation.example.com

Requires:
    pip install requests

The public JSON endpoint requires no authentication.
It is rate-limited to 30 requests per 60-second window per IP address.
See openapi/ERROR_CODES.md for rate-limit and backoff details.
"""

import argparse
import json
import sys
import time

import requests

DEFAULT_BASE_URL = "http://localhost:10019"
ENDPOINT = "/competitions/api/json"
MAX_RETRIES = 3


def fetch_tournaments(base_url: str) -> list[dict]:
    url = base_url.rstrip("/") + ENDPOINT
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=10)
        except requests.ConnectionError as exc:
            print(f"Connection error: {exc}", file=sys.stderr)
            sys.exit(1)

        if response.status_code == 200:
            data = response.json()
            return data.get("tournaments", [])

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            wait = retry_after + 1  # add 1 second for clock skew
            print(
                f"Rate limited (attempt {attempt}/{MAX_RETRIES}). "
                f"Waiting {wait}s before retry...",
                file=sys.stderr,
            )
            if attempt < MAX_RETRIES:
                time.sleep(wait)
                continue
            print("Max retries exceeded after rate limiting.", file=sys.stderr)
            sys.exit(1)

        # Non-retryable error
        try:
            error_body = response.json()
            error_code = error_body.get("error_code", "unknown")
            error_msg = error_body.get("error", response.text)
        except ValueError:
            error_code = "unknown"
            error_msg = response.text

        print(
            f"Error {response.status_code} [{error_code}]: {error_msg}",
            file=sys.stderr,
        )
        sys.exit(1)

    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch federation tournaments")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the federation server (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--output",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    args = parser.parse_args()

    tournaments = fetch_tournaments(args.base_url)

    if not tournaments:
        print("No tournaments returned.")
        return

    if args.output == "json":
        print(json.dumps(tournaments, indent=2))
        return

    # Table output
    header = f"{'ID':>6}  {'Code':<12}  {'Name':<40}  {'State':<12}  {'Date Start':<12}"
    print(header)
    print("-" * len(header))
    for t in tournaments:
        print(
            f"{t.get('id', ''):>6}  "
            f"{t.get('code', ''):12}  "
            f"{t.get('name', '')[:40]:<40}  "
            f"{t.get('state', ''):12}  "
            f"{t.get('date_start') or '':12}"
        )
    print(f"\nTotal: {len(tournaments)} tournament(s)")


if __name__ == "__main__":
    main()
