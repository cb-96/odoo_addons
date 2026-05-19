# Integration Contracts

Last updated: 2026-04-13
Owner: Federation Platform Team
Last reviewed: 2026-04-17
Review cadence: Every release

This document defines the stable partner-facing contracts currently supported by
the federation platform and the policy used to version, evolve, and deprecate
them.

Machine-readable partner route definitions live in `openapi/integration_v1.yaml`.
Keep the OpenAPI file, this document, and the route implementations aligned in
the same change set whenever a managed integration contract changes.

## Contract Principles

- Every external export or feed must expose an explicit contract identifier.
- Version changes must be additive within a version whenever possible.
- Breaking schema changes require a new contract version rather than silent
  mutation of an existing response.
- Deprecated routes or payloads remain available for at least one supported
  release cycle after the replacement contract is published, unless security or
  legal requirements force a faster removal.
- Contract changes must be reflected in code, tests where applicable, this
  document, and the roadmap or release notes in the same change set.

## Authentication Strategy

Public tournament contracts:

- `auth="public"`
- intended for website visitors, public calendars, and read-only partner
  consumption

Operator-authenticated reporting exports:

- `auth="user"`
- require an authenticated backend session
- intended for federation operators using backend actions and reporting screens

Managed partner contracts:

- `auth="public"` routes protected by partner credentials
- require `X-Federation-Partner-Code` and `X-Federation-Partner-Token`
- enforce per-partner contract subscriptions before a payload is served or a
  delivery is accepted
- intended for explicit machine-to-machine integrations without sharing backend
  user sessions

Import contracts:

- executed either through backend import wizards or through managed partner
  delivery staging before entering the same wizard flow
- guarded by dry-run preview, governance-job approval, and checksum matching for
  live imports

## Public Contracts

### Tournament Feed

- Canonical route: `/api/v1/tournaments/<slug>/feed`
- Compatibility routes:
  - `/api/v1/tournaments/<id>/feed`
  - `/api/v1/competitions/<id>/feed`
- Response type: `application/json`
- Headers:
  - `X-Federation-Contract: tournament_feed`
  - `X-Federation-Contract-Version: v1`
- Payload anchor:
  - top-level `api_version = "v1"`
- Stability expectation:
  - top-level keys in the v1 payload are stable
  - additive nested fields are allowed in v1 when they do not alter existing
    semantics

### Tournament Schedule Calendar

- Canonical route: `/tournaments/<slug>/schedule.ics`
- Compatibility route: `/tournament/<id>/schedule.ics`
- Response type: `text/calendar`
- Headers:
  - `X-Federation-Contract: tournament_schedule_ics`
  - `X-Federation-Contract-Version: ics_v1`
- Stability expectation:
  - calendar structure stays compatible with standard ICS consumers
  - field enrichment should be additive inside event descriptions, not a change
    to the ICS envelope

## Authenticated CSV Contracts

All authenticated CSV exports expose these headers:

- `X-Federation-Contract`
- `X-Federation-Contract-Version`

### Standings Export

- Route: `/reporting/export/standings/<tournament_id>`
- Contract: `standings_csv`
- Version: `csv_v1`
- Notes:
  - intended for downstream standings review and board-pack style extracts

### Participation Export

- Route: `/reporting/export/participation/<season_id>`
- Contract: `participation_csv`
- Version: `csv_v1`

### Finance Summary Export

- Route: `/reporting/export/finance`
- Contract: `finance_summary_csv`
- Version: `csv_v1`

### Finance Event Handoff Export

- Route: `/reporting/export/finance/events`
- Contract: `finance_event_v1`
- Versioning anchor:
  - detailed finance-event handoff rows expose a schema version column and the
    matching response header contract version
- Required handoff fields include:
  - event identity and state
  - handoff state
  - fee type and amount
  - invoice, external, accounting-batch, and reconciliation references
  - source traceability
  - exported, reconciled, and closed timestamps

## Managed Partner Contracts

### Contract Manifest

- Route: `/integration/v1/contracts`
- Response type: `application/json`
- Authentication:
  - `X-Federation-Partner-Code`
  - `X-Federation-Partner-Token`
- Payload includes:
  - contract code, version, direction, transport, and route hint
  - deprecation stage and replacement contract
  - `available` flag for database-specific operational availability
  - partner subscription state and last-used timestamp

### Partner Finance Event Handoff

- Route: `/integration/v1/outbound/finance/events`
- Response type: `text/csv`
- Contract: `finance_event_v1`
- Optional query parameters:
  - `limit` to request one bounded page of rows; defaults to `200` and caps at `500`
  - `cursor` to resume after the last row from the previous page
- Invalid `limit` or `cursor` values return `400` with the standard `data_validation` payload.
- Headers:
  - `X-Federation-Contract: finance_event_v1`
  - `X-Federation-Contract-Version: <schema version>`
  - `X-Federation-Partner-Code: <partner code>`
  - `X-Federation-Export-Mode: cursor_page` when cursor pagination is active
  - `X-Federation-Export-Count: <row count>` when cursor pagination is active
  - `X-Federation-Has-More: true|false` when cursor pagination is active
  - `X-Federation-Page-Limit: <effective limit>` when cursor pagination is active
  - `X-Federation-Next-Cursor: <timestamp>|<id>` when another page is available
- Authentication:
  - `X-Federation-Partner-Code`
  - `X-Federation-Partner-Token`

### Inbound Delivery Staging

- Route: `/integration/v1/inbound/<contract_code>/deliveries`
- Method: `POST`
- Request type: JSON object
- Authentication:
  - `X-Federation-Partner-Code`
  - `X-Federation-Partner-Token`
  - optional `X-Federation-Idempotency-Key` to safely reuse the same staged delivery for matching retries
- Request fields:
  - `filename`
  - `payload_base64`
  - optional `notes`
  - optional `source_reference`
- Response header on every successful delivery request:
  - `X-Federation-Delivery-Outcome: created|checksum_reuse|idempotency_replay`
- Response headers when an idempotency key is supplied:
  - `X-Federation-Idempotency-Key: <normalized key>`
  - `X-Federation-Idempotent-Replay: true|false`
- Response fields:
  - `delivery_outcome` with `created`, `checksum_reuse`, or `idempotency_replay`
  - delivery identity and current state
  - partner and contract codes
  - echoed `idempotency_key` when present
  - payload checksum
  - contract route hint
- Duplicate handling:
  - the same partner, contract, and payload checksum reuse the active staged
    delivery while it remains in preview or approval flow and report
    `delivery_outcome = checksum_reuse`
  - the same partner, contract, and idempotency key replay the original delivery
    across all states, report `delivery_outcome = idempotency_replay`, and
    still return `400` if the key is reused for a different payload

## Import Contracts

Reusable import templates are versioned backend contracts and live under
`federation.import.template`.

Current template codes:

- `clubs_csv`
- `players_csv`
- `seasons_csv`
- `teams_csv`
- `tournament_participants_csv`

Current template version:

- `csv_v1`

Managed inbound delivery policy:

1. A subscribed partner posts a base64 payload to the inbound delivery route for
  the relevant contract.
2. The system stages a `federation.integration.delivery` record, deduplicates
  active resubmissions by checksum, and can also bind an explicit idempotency
  key to the request for safer client retries.
3. Operators open the staged delivery in the matching import wizard for preview.
4. Approval and live execution continue through the standard governance-job
  workflow already used for manual rollover imports.

Live import policy:

1. Run a dry-run preview for the uploaded CSV.
2. Request approval, which creates a governance job tied to the file checksum,
   target model, template, and preview results.
3. Approve the governance job.
4. Execute the live import only if the CSV checksum and selected template still
   match the approved job.

Verification policy:

- governance jobs store preview totals, execution totals, and before/after
  target-model record counts
- live imports that partially succeed remain visible as
  `completed_with_errors`
- staged partner deliveries mirror preview, approval, completion, and failure
  states so operators can reconcile inbound handoffs without leaving the app

## Versioning Policy

- Public JSON versions are encoded in both the path and the payload.
- CSV and ICS contracts use stable routes plus explicit response headers.
- Import templates use a version field on the template and a matching schema
  snapshot on the governance job.
- Breaking changes require a new contract identifier or version rather than a
  silent replacement.

## Deprecation Policy

The working list of compatibility aliases, owners, review dates, and target
sunset dates lives in `COMPATIBILITY_INVENTORY.md` and must be updated in the
same change set as any contract-facing deprecation decision.

- Slug-based public routes are canonical.
- Numeric public routes remain compatibility shims and should not be used for
  new integrations.
- Legacy competition-named public feed routes remain compatibility aliases for
  the tournament feed and are considered deprecated in favor of the canonical
  tournament path.
- Older CSV shapes should remain available for one supported release cycle once
  a replacement contract is published.
- Removals must be announced by updating this file, relevant READMEs, and the
  roadmap in the same release window.