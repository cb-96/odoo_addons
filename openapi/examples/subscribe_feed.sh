#!/usr/bin/env env bash
# subscribe_feed.sh — Poll the Sports Federation tournament feed at regular intervals.
#
# Usage:
#   bash subscribe_feed.sh <tournament-slug> [base-url] [interval-seconds]
#
# Examples:
#   bash subscribe_feed.sh summer-cup-2026
#   bash subscribe_feed.sh summer-cup-2026 https://federation.example.com 60
#
# The public feed endpoint requires no authentication.
# It is rate-limited to 60 requests per 60-second window per IP.
# See openapi/ERROR_CODES.md for rate-limit and backoff details.
#
# Requires: curl, jq (optional — falls back to raw JSON if jq is not installed)

set -euo pipefail

SLUG="${1:-}"
BASE_URL="${2:-http://localhost:10019}"
INTERVAL="${3:-30}"

if [[ -z "$SLUG" ]]; then
    echo "Usage: $0 <tournament-slug> [base-url] [interval-seconds]" >&2
    exit 1
fi

ENDPOINT="${BASE_URL%/}/api/v1/tournaments/${SLUG}/feed"
MAX_CONSECUTIVE_ERRORS=5
consecutive_errors=0

echo "Polling ${ENDPOINT} every ${INTERVAL}s (Ctrl+C to stop)"
echo "---"

while true; do
    # Capture HTTP status code separately from body
    HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" --max-time 10 \
        -H "Accept: application/json" \
        "$ENDPOINT" 2>/dev/null) || {
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Connection error. Retrying in ${INTERVAL}s..." >&2
        consecutive_errors=$((consecutive_errors + 1))
        if [[ $consecutive_errors -ge $MAX_CONSECUTIVE_ERRORS ]]; then
            echo "Too many consecutive connection errors. Exiting." >&2
            exit 1
        fi
        sleep "$INTERVAL"
        continue
    }

    HTTP_BODY=$(echo "$HTTP_RESPONSE" | head -n -1)
    HTTP_STATUS=$(echo "$HTTP_RESPONSE" | tail -n 1)

    case "$HTTP_STATUS" in
        200)
            consecutive_errors=0
            echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] HTTP 200 — received feed:"
            if command -v jq &>/dev/null; then
                echo "$HTTP_BODY" | jq '.'
            else
                echo "$HTTP_BODY"
            fi
            ;;
        429)
            # Rate limited — parse Retry-After from headers if available
            # (curl -w "%{http_code}" does not expose headers; use a fixed backoff)
            BACKOFF=65
            echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Rate limited (429). Waiting ${BACKOFF}s..." >&2
            consecutive_errors=$((consecutive_errors + 1))
            sleep "$BACKOFF"
            continue
            ;;
        404)
            echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Tournament '${SLUG}' not found (404). Check the slug." >&2
            exit 1
            ;;
        *)
            echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Unexpected HTTP ${HTTP_STATUS}:" >&2
            echo "$HTTP_BODY" >&2
            consecutive_errors=$((consecutive_errors + 1))
            if [[ $consecutive_errors -ge $MAX_CONSECUTIVE_ERRORS ]]; then
                echo "Too many consecutive errors. Exiting." >&2
                exit 1
            fi
            ;;
    esac

    sleep "$INTERVAL"
done
