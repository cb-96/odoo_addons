# API Error Codes Reference

Last updated: 2026-05-18
Owner: Federation Platform Team
Review cadence: Every release train

This document is the authoritative reference for all `error_code` values
returned by federation JSON endpoints, per-scope rate limits, backoff
recommendations, and `Retry-After` header semantics.

---

## Error Code Catalogue

All JSON error responses from federation endpoints share this envelope:

```json
{
  "error": "Human-readable operator-safe summary",
  "error_code": "machine_readable_code"
}
```

The `error` field is safe to surface to operators and partners. It must not
contain PII, internal stack traces, or database details.

| `error_code` | HTTP Status | Meaning | Retryable? |
|---|---|---|---|
| `retryable_delivery` | 429 or 503 | Temporary failure; the request should be retried after the `Retry-After` interval | Yes |
| `not_found` | 404 | The requested resource does not exist or is not visible to this caller | No |
| `validation_error` | 400 | Request payload failed server-side validation (missing field, invalid value, constraint violation) | No — fix the payload |
| `unauthorized` | 401 | Authentication is required but missing or expired | No — re-authenticate |
| `access_denied` | 401 or 403 | Authenticated but not permitted to access this resource (wrong club, wrong partner code, or revoked token) | No |
| `rate_limited` | 429 | Caller has exceeded the per-scope rate limit; see `Retry-After` header | Yes — after backoff |
| `configuration_error` | 500 | Server-side configuration problem (missing `ir.config_parameter`, misconfigured module) | No — contact federation admin |
| `data_validation` | 422 | Data accepted but failed business rule validation (e.g. season not open, duplicate registration) | No — fix the business data |
| `operator_input` | 400 | The payload is syntactically valid but semantically incorrect for the current state of the record | No — fix the input |
| `unexpected_bug` | 500 | Unhandled exception; the federation will investigate | No — contact federation tech team |

### Integration API Error Codes (`integration_v1.yaml`)

The integration API uses the subset defined in `components/schemas/ErrorResponse`
of `openapi/integration_v1.yaml`:

| `error_code` | Applies to |
|---|---|
| `retryable_delivery` | Inbound delivery staging failures, temporary DB locks |
| `access_denied` | Invalid or expired partner token or partner code |
| `configuration_error` | Required module not installed, partner not active |
| `data_validation` | Malformed CSV payload, unknown field in delivery body |
| `operator_input` | Delivery references a non-existent external ID |
| `unexpected_bug` | Unhandled server error |

### Public Feed Error Codes (`public_feeds_v1.yaml`)

| `error_code` | Applies to |
|---|---|
| `not_found` | Tournament slug or ID not found |
| `rate_limited` | Caller exceeded per-scope limit (see rate limits below) |
| `unexpected_bug` | Unhandled server error |

### Portal API Error Codes (`portal_v1.yaml`)

| `error_code` | Applies to |
|---|---|
| `not_found` | Match, tournament, or team not found or not visible to this club |
| `validation_error` | Missing field, score < 0, team not in match |
| `unauthorized` | Session expired or not present |
| `access_denied` | Team or match belongs to a different club |
| `data_validation` | Registration for a closed season, duplicate registration |
| `unexpected_bug` | Unhandled server error |

---

## Per-Scope Rate Limits

Rate limits are enforced by `federation.request.rate.limit` using fixed
time windows. The default policies are defined in
`sports_federation_base/models/request_rate_limit.py → _POLICIES`.

Limits can be overridden at runtime via `ir.config_parameter` without a code
deployment:

- Key: `sports_federation.rate_limit.<scope>.limit`
- Key: `sports_federation.rate_limit.<scope>.window_seconds`

| Scope | Default Limit | Window | Endpoint(s) |
|---|---|---|---|
| `public_competitions_json` | 30 requests | 60 seconds | `GET /competitions/api/json` |
| `public_competition_feed` | 60 requests | 60 seconds | `GET /api/v1/tournaments/<slug>/feed` |
| `public_team_feed` | 60 requests | 60 seconds | `GET /api/v1/tournaments/<slug>/teams` |
| `integration_contracts` | 20 requests | 60 seconds | `GET /integration/v1/contracts` |
| `integration_finance_events` | 20 requests | 60 seconds | `GET /integration/v1/finance-events` |
| `integration_inbound_deliveries` | 20 requests | 60 seconds | `POST /integration/v1/deliveries` |

Rate-limit subjects:

- **Public routes**: subject is the caller's IP address (`ip:<address>`).
- **Integration routes**: subject is the partner code (`partner:<code>`).
- **Portal routes**: subject is the authenticated user ID (`user:<id>`).

---

## `Retry-After` Header Semantics

When a request is rate-limited (`error_code = rate_limited`), the response
includes a `Retry-After` header:

```
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 43

{"error": "Rate limit exceeded. Retry after 43 seconds.", "error_code": "rate_limited"}
```

The value is the number of **whole seconds** until the current window expires
and the counter resets. It is calculated as:

$$\text{Retry-After} = \text{window\_start} + \text{window\_seconds} - \text{now (UTC)}$$

### Backoff Recommendation

For automated clients (integration partners, feed pollers):

1. On receiving `Retry-After: N`, pause for **at least `N + 1` seconds** before
   retrying (the extra second accounts for clock skew).
2. Apply **exponential backoff with jitter** if you receive more than 3
   consecutive `rate_limited` responses — this indicates the configured limit
   is too low for your polling frequency.
3. Do not retry immediately. Zero-delay retries will hit the same rate-limit
   bucket and waste quota.

Recommended backoff formula:

$$\text{wait} = \max(\text{Retry-After} + 1,\ 2^{\text{consecutive\_429s}} + \text{random}(0, 1))$$

Contact the federation technical team to request a limit increase if your
legitimate polling frequency consistently exceeds the default limits.

---

## Checking and Overriding Limits at Runtime

```bash
# Check current effective limit for a scope
docker compose exec odoo odoo shell -c /etc/odoo/odoo.conf -d odoo <<'EOF'
print(env['ir.config_parameter'].sudo().get_param(
    'sports_federation.rate_limit.public_competitions_json.limit', '30 (default)'))
EOF

# Override the public feed limit to 120 requests per minute
docker compose exec odoo odoo shell -c /etc/odoo/odoo.conf -d odoo <<'EOF'
env['ir.config_parameter'].sudo().set_param(
    'sports_federation.rate_limit.public_competitions_json.limit', '120')
env.cr.commit()
EOF
```

Overrides are stored in `ir.config_parameter` and survive Odoo restarts.
They are lost on database restore from a backup taken before the override.

---

## Clearing Stale Buckets

Rate-limit buckets from expired windows are cleaned up by the
`Federation: GC Rate Limit Buckets` scheduled action (default: every hour).
To clear manually:

```bash
docker compose exec -T db psql -U odoo -d odoo \
  -c "DELETE FROM federation_request_rate_limit
      WHERE window_start < NOW() - INTERVAL '10 minutes';"
```
