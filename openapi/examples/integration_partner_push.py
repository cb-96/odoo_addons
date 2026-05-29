#!/usr/bin/env python3
"""
integration_partner_push.py — Example integration partner client.

Demonstrates:
  1. Authenticating as an integration partner
  2. Fetching the contract manifest (GET /integration/v1/contracts)
  3. Pushing a staged inbound delivery (POST /integration/v1/deliveries)
  4. Fetching finance events for reconciliation (GET /integration/v1/finance-events)

Usage:
    python3 integration_partner_push.py \\
        --base-url https://federation.example.com \\
        --partner-code MYPARTNER \\
        --partner-token <token>

Requires:
    pip install requests

The integration API uses partner-code + partner-token header authentication.
Tokens are one-time-issued secrets obtained from the federation administrator.
See openapi/integration_v1.yaml and openapi/ERROR_CODES.md for full details.
"""

import argparse
import json
import sys
import time

import requests

DEFAULT_BASE_URL = "http://localhost:10019"
MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds; doubles on each retry


def make_session(
    base_url: str, partner_code: str, partner_token: str
) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "X-Federation-Partner-Code": partner_code,
            "X-Federation-Partner-Token": partner_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    session.base_url = base_url.rstrip("/")
    return session


def request_with_retry(
    session: requests.Session, method: str, path: str, **kwargs
) -> dict:
    url = session.base_url + path
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = getattr(session, method)(url, timeout=15, **kwargs)
        except requests.ConnectionError as exc:
            print(f"Connection error: {exc}", file=sys.stderr)
            sys.exit(1)

        if response.status_code == 200:
            return response.json()

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            wait = retry_after + 1
            print(
                f"Rate limited (attempt {attempt}/{MAX_RETRIES}). Waiting {wait}s...",
                file=sys.stderr,
            )
            if attempt < MAX_RETRIES:
                time.sleep(wait)
                continue
            print("Max retries exceeded after rate limiting.", file=sys.stderr)
            sys.exit(1)

        if response.status_code in (503, 502):
            wait = BACKOFF_BASE**attempt
            print(
                f"Server unavailable ({response.status_code}, attempt {attempt}/{MAX_RETRIES}). "
                f"Retrying in {wait}s...",
                file=sys.stderr,
            )
            if attempt < MAX_RETRIES:
                time.sleep(wait)
                continue

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

    print("Max retries exceeded.", file=sys.stderr)
    sys.exit(1)


def fetch_contracts(session: requests.Session) -> dict:
    print("Fetching contract manifest...")
    result = request_with_retry(session, "get", "/integration/v1/contracts")
    contracts = result.get("contracts", [])
    print(f"  Partner: {result.get('partner', {}).get('name')}")
    print(f"  Contracts available: {len(contracts)}")
    for contract in contracts:
        status = "✓ available" if contract.get("available") else "✗ unavailable"
        print(
            f"    [{status}] {contract['code']} v{contract['version']} ({contract['direction']})"
        )
    return result


def push_delivery(session: requests.Session, delivery_payload: dict) -> dict:
    print("\nPushing inbound delivery...")
    result = request_with_retry(
        session,
        "post",
        "/integration/v1/deliveries",
        json=delivery_payload,
    )
    print(f"  Delivery accepted. State: {result.get('state')}")
    print(f"  External ref: {result.get('external_ref')}")
    return result


def fetch_finance_events(
    session: requests.Session, since: str | None = None
) -> list[dict]:
    print("\nFetching finance events...")
    path = "/integration/v1/finance-events"
    if since:
        path += f"?since={since}"
    result = request_with_retry(session, "get", path)
    events = result.get("events", [])
    print(f"  Events returned: {len(events)}")
    for event in events[:5]:  # show first 5
        print(
            f"    [{event.get('state')}] {event.get('fee_type_code')} "
            f"— {event.get('amount')} {event.get('currency')} "
            f"(external_ref: {event.get('external_ref')})"
        )
    if len(events) > 5:
        print(f"    ... and {len(events) - 5} more")
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Integration partner example client")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--partner-code", required=True)
    parser.add_argument("--partner-token", required=True)
    parser.add_argument(
        "--since",
        default=None,
        help="ISO datetime filter for finance events (e.g. 2026-05-01T00:00:00Z)",
    )
    args = parser.parse_args()

    session = make_session(args.base_url, args.partner_code, args.partner_token)

    # 1. Fetch contracts
    fetch_contracts(session)

    # 2. Push a sample delivery
    sample_delivery = {
        "contract_code": "player_registration_import",
        "external_ref": "DEMO-DELIVERY-001",
        "payload": json.dumps(
            [
                {"player_id": "EXT-P-001", "club_code": "MFC", "season_code": "2026"},
            ]
        ),
    }
    push_delivery(session, sample_delivery)

    # 3. Fetch finance events
    fetch_finance_events(session, since=args.since)

    print("\nDone.")


if __name__ == "__main__":
    main()
