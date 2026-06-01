# Integration Golden Examples (v1)

This file provides partner-facing reference examples for the managed integration API.

## 1) Contract Manifest Request

### Request

GET /integration/v1/contracts
X-Federation-Partner-Code: PARTNER_FINANCE
X-Federation-Partner-Token: <token>
X-Federation-Correlation-Id: onboarding-req-001

### Response (200)

{
  "correlation_id": "onboarding-req-001",
  "partner": {
    "code": "PARTNER_FINANCE",
    "name": "Finance Vendor"
  },
  "contracts": [
    {
      "code": "finance_event_v1",
      "version": "csv_v1",
      "direction": "outbound",
      "transport": "csv",
      "route_hint": "/integration/v1/outbound/finance/events",
      "available": true,
      "subscription_state": "active"
    }
  ]
}

## 2) Finance Event Export (paged)

### Request

GET /integration/v1/outbound/finance/events?limit=2
X-Federation-Partner-Code: PARTNER_FINANCE
X-Federation-Partner-Token: <token>
X-Federation-Correlation-Id: onboarding-req-002

### Response headers (200)

X-Federation-Correlation-Id: onboarding-req-002
X-Federation-Export-Mode: cursor_page
X-Federation-Export-Count: 2
X-Federation-Has-More: true
X-Federation-Page-Limit: 2
X-Federation-Next-Cursor: 2026-04-18 12:00:00|300

## 3) Inbound delivery with idempotency

### Request

POST /integration/v1/inbound/clubs_csv/deliveries
X-Federation-Partner-Code: PARTNER_IMPORT
X-Federation-Partner-Token: <token>
X-Federation-Correlation-Id: onboarding-req-003
X-Federation-Idempotency-Key: clubs-batch-2026-06-01

{
  "filename": "clubs.csv",
  "content_type": "text/csv",
  "payload_base64": "bmFtZSxjb2RlCkRlbGl2ZXJ5IENsdWIsREMwMDE="
}

### Response (201)

{
  "correlation_id": "onboarding-req-003",
  "delivery_outcome": "created",
  "delivery": {
    "id": 42,
    "name": "DEL-00042",
    "partner_code": "PARTNER_IMPORT",
    "contract_code": "clubs_csv",
    "state": "staged",
    "filename": "clubs.csv",
    "idempotency_key": "clubs-batch-2026-06-01",
    "payload_checksum": "sha256:...",
    "route_hint": "/integration/v1/inbound/clubs_csv/deliveries"
  }
}

## 4) Error shape (invalid pagination)

### Request

GET /integration/v1/outbound/finance/events?limit=0
X-Federation-Partner-Code: PARTNER_FINANCE
X-Federation-Partner-Token: <token>
X-Federation-Correlation-Id: onboarding-req-004

### Response (400)

{
  "error": "Finance event export limits must be positive integers.",
  "error_code": "data_validation",
  "correlation_id": "onboarding-req-004"
}
