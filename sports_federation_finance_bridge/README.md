# Sports Federation Finance Bridge

Records billable and reimbursable federation events without requiring a full
accounting module. Provides fee types and finance events as a lightweight
financial tracking layer.

## Purpose

Bridges the gap between federation operations and future accounting integration.
Every registration fee, disciplinary fine, referee reimbursement, or venue booking is logged as a
**finance event** with amount, state, and source reference — ready to be fed into
an accounting system when one is connected.

## Dependencies

| Module | Reason |
|--------|--------|
| `sports_federation_base` | Clubs |
| `sports_federation_people` | Players |
| `sports_federation_tournament` | Tournament context |
| `sports_federation_result_control` | Result approval pipeline (automatic event hooks) |
| `sports_federation_officiating` | Referees |
| `sports_federation_discipline` | Fines and sanctions |
| `sports_federation_venues` | Venue booking passthroughs |

## Models

### `federation.fee.type`

A catalogue of fee categories.

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char | Fee type name |
| `code` | Char | Unique code |
| `category` | Selection | registration / fine / reimbursement / other |
| `default_amount` / `currency_id` | Monetary | Default amount |
| `active` | Boolean | In use |
| `notes` | Text | Description |

### `federation.finance.event`

An individual financial occurrence.

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char | Event title |
| `fee_type_id` | Many2one | Fee category |
| `event_type` | Selection | Type classification |
| `amount` / `currency_id` | Monetary | Actual amount |
| `state` | Selection | draft / confirmed / settled / cancelled |
| `source_model` / `source_res_id` | Char / Integer | Origin record |
| `season_id` | Many2one | Resolved season scope for planning and reporting |
| `partner_id` | Many2one | Related partner |
| `club_id` / `player_id` / `referee_id` | Many2one | Federation entity |
| `invoice_ref` / `external_ref` | Char | External references |
| `handoff_state` | Selection | pending_export / exported / reconciled / closed |
| `accounting_batch_ref` / `reconciliation_ref` | Char | Accounting handoff references |
| `notes` | Text | Details |

- **State machine**: draft → confirmed → settled / cancelled.
- **Handoff state machine**: pending_export → exported → reconciled → closed.

## Key Behaviours

1. **Source traceability** — Every finance event links back to its originating record
   (registration, sanction, assignment) via model/res_id.
2. **Fee catalogue** — Standardised fee types with default amounts.
3. **Accounting-ready** — `invoice_ref` and `external_ref` keep the bridge ready
   for future accounting integration while the current lightweight workflow ends
   in `settled`.
4. **Idempotent automation** — source-driven helpers reuse or reactivate matching
  draft finance events instead of duplicating them on workflow re-entry.
5. **Multi-entity** — Covers clubs, players, and referees.
6. **Accounting handoff governance** — finance events now track export,
   reconciliation, and closure checkpoints for downstream accounting workflows.
7. **Season intelligence support** — finance events infer a season scope from
  their source record whenever possible so reporting and budget views can roll
  up actuals without duplicate data entry.
8. **Operator-safe batch invoicing** — list-view "Create Invoices" now reports
  per-event failures instead of silently skipping exceptions, so reconciliation
  issues are visible immediately.

### `federation.season.budget`

Planning baseline per season and fee type.

| Field | Type | Description |
|-------|------|-------------|
| `season_id` / `fee_type_id` | Many2one | Budget scope |
| `budget_amount` | Monetary | Planned amount |
| `actual_amount` | Monetary | Confirmed and settled actuals for the same scope |
| `actual_event_count` | Integer | Count of matching actual finance events |
| `variance_amount` / `variance_pct` | Monetary / Float | Planned vs actual variance |
| `notes` | Text | Budget commentary |

The backend exposes season budgets under Federation > Finance and provides a
stat button that opens the scoped finance events behind the variance figures.

## Accounting Handoff Contract

The finance bridge now supports an explicit accounting handoff workflow:

- `action_mark_exported()` marks confirmed or settled events as exported
- `action_mark_reconciled()` requires settlement and an exported handoff state
- `action_close_handoff()` closes only reconciled, settled events

Detailed handoff CSV contract:

- route: `/reporting/export/finance/events`
- contract id: `finance_event_v1`
- includes schema version, handoff state, accounting batch reference,
  reconciliation reference, source traceability, and execution timestamps

## Season Registration Finance Hooks

The finance bridge now auto-creates a finance event when a
`federation.season.registration` record moves into `confirmed`.

- Default fee type code: `season_registration`
- Creation mode: idempotent; reconfirming a registration reuses the same source
  record and does not create duplicates
- Source traceability: events use `source_model = federation.season.registration`
  and `source_res_id = <registration id>`
- Reconciliation support: auto-created events also receive a deterministic
  `external_ref` using the fee-type code and source record identity

## Result Approval Finance Hooks (Phase 2)

match_result_hooks.py extends `federation.match` with:

- **`result_fee_type_id`** (Many2one → `federation.fee.type`): optional; when set,
  a `federation.finance.event` (charge) is automatically created when
  `action_approve_result()` completes.
- **`result_finance_event_ids`** (computed): finance events created with the
  configured result fee type for this match.
- **`action_approve_result()`** override: calls the base result pipeline and then
  fires the auto-event through the idempotent source helper.

## Discipline Fine Hooks

`sanction_finance_hooks.py` extends `federation.sanction` so that:

- sanctions of type `fine` automatically create a `federation.finance.event`
- the default fee type code is `discipline_fine`
- fine events inherit subject references from the sanction or disciplinary case
- changing the fine amount updates the linked draft finance event instead of
  creating a second one

## Referee Reimbursement Hooks

`referee_reimbursement_hooks.py` extends `federation.match.referee` so that:

- assignments reaching `done` automatically create a reimbursement event
- the default fee type code is `referee_reimbursement`
- reverting the assignment out of `done` cancels the draft reimbursement event
- returning to `done` reuses the same source-traceable reimbursement event

## Venue Booking Hooks

`venue_finance_hooks.py` extends `federation.match` so that:

- scheduled matches with a venue automatically create a venue booking charge
- the default fee type code is `venue_booking`
- removing the venue or unscheduling the match cancels the draft venue event
- the manual `action_create_venue_finance_event()` helper now reuses the same
  source event instead of failing on duplicate creation

### Migration note (v19.0.1.2.0)

The finance bridge now depends on `sports_federation_venues` and adds automatic
hooks for discipline fines, completed referee assignments, and scheduled venue
bookings. Run `-u sports_federation_finance_bridge` after upgrade.

### Migration note (v19.0.1.3.0)

Finance events now include accounting handoff states and references used by the
reporting export contract. Run `-u sports_federation_finance_bridge` after
upgrade to create the new fields and updated views.

### Migration note (v19.0.1.4.0)

Finance events now store an inferred `season_id`, and the module adds the new
`federation.season.budget` planning model and views. Run
`-u sports_federation_finance_bridge` after upgrade.