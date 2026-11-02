# Workflow: Financial Tracking

Lightweight financial event recording for registration fees, disciplinary fines,
referee reimbursements, and other federation-related financial activity.

## Overview

The federation needs to track money flowing in and out — registration fees from
clubs, fines from disciplinary actions, reimbursements for referees — without
requiring a full accounting module. The finance bridge module records these as
**finance events** linked to their source, with states that prepare them for
future accounting integration.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_finance_bridge` | Fee types, finance events |
| `sports_federation_base` | Clubs (fee payers) |
| `sports_federation_people` | Players (registration fees) |
| `sports_federation_tournament` | Tournament context |
| `sports_federation_officiating` | Referees (reimbursements) |
| `sports_federation_discipline` | Sanctions (fines) |
| `sports_federation_notifications` | Finance confirmation notifications |
| `sports_federation_reporting` | Financial summary reports |

## Step-by-Step Flow

### 1. Fee Type Catalogue Setup

**Actor**: Federation administrator
**Module**: `sports_federation_finance_bridge`

1. Navigate to **Federation → Finance → Fee Types**.
2. Create fee type entries:

| Example | Category | Default Amount |
|---------|----------|---------------|
| Season Registration Fee | `registration` | €250.00 |
| Player License Fee | `registration` | €25.00 |
| Disciplinary Fine (Yellow Card) | `fine` | €50.00 |
| Disciplinary Fine (Red Card) | `fine` | €150.00 |
| Referee Travel Reimbursement | `reimbursement` | €75.00 |
| Match Officials Fee | `reimbursement` | €100.00 |
| Venue Booking (passthrough) | `other` | variable |

Each fee type has a unique code, category, and default amount.

### 2. Finance Event Creation

**Actor**: Federation staff or automated from source modules
**Module**: `sports_federation_finance_bridge`

Finance events are created in two ways:

**Manual**: Staff creates an event from the Finance Events list view.

**From source modules**: Other modules create events when relevant actions occur:
- Registration approved → registration fee event
- Sanction with fine → fine event
- Referee assignment completed → reimbursement event
- Match result approved with `result_fee_type_id` → result-processing charge event
- Match scheduled with a confirmed venue → venue booking event

All automatic hooks create source-linked events idempotently and assign a
deterministic `external_ref` so repeated workflow entries reuse the same draft
record instead of creating duplicates.

Each event records:
- Fee type (from catalogue)
- Amount and currency
- Source record (via `source_model` / `source_res_id`)
- Target entity: club, player, or referee
- Partner (for accounting integration)

### 3. Event Confirmation

**Actor**: Federation finance staff
**Module**: `sports_federation_finance_bridge`

1. Review draft finance events.
2. Verify amounts, source references, and the deterministic `external_ref`.
3. **Confirm**: state `draft` → `confirmed`.
4. Confirmed events represent accepted financial obligations.
5. Confirmation triggers a notification email to the resolved partner, club,
   player, or referee contact; missing-recipient cases are logged without
   blocking the state change.

### 4. Invoicing

**Actor**: Federation finance staff
**Module**: `sports_federation_finance_bridge`

For confirmed events that need an external accounting reference:

1. Use the native accounting command when the federation accounting integration
   is installed. The bridge fallback requires an explicit invoice partner and a
   configured invoice product so accounting can resolve its income account.
2. Record the generated invoice reference in `invoice_ref` when using the bridge
   fallback.
3. Keep the bridge event in `confirmed` until it is financially settled.

### 5. Payment Recording

**Actor**: Federation finance staff
**Module**: `sports_federation_finance_bridge`

1. When payment is received or reimbursement is completed:
2. Set state to `settled`.
3. Record external references if applicable (`external_ref`).

### 6. Cancellation

**Actor**: Federation administrator
**Module**: `sports_federation_finance_bridge`

1. Events can be cancelled at any stage before `settled`.
2. State → `cancelled`.
3. Cancelled events remain in the system for audit but are excluded from totals.

### 7. Reporting

**Actor**: Federation administrator
**Module**: `sports_federation_reporting`

The **Finance Report** (SQL view-backed model) provides:
- Summary by fee type and state
- Total amounts per category
- Event counts for monitoring
- A **Finance Reconciliation** queue showing open follow-up items by event,
    counterparty, reference coverage, and ageing
- Report schedules that can generate weekly or monthly CSV snapshots from the
    reporting menu without direct database access
- CSV export via `/reporting/export/finance` for lightweight leadership dashboards

## State Diagram

```
Finance Event: draft → confirmed → settled
                     → cancelled (from any pre-settled state)
```

## Financial Event Sources

| Source Action | Fee Category | Auto-Created? |
|--------------|-------------|---------------|
| Season registration approved | Registration | Yes |
| Player license issued | Registration | Extendable |
| Tournament participation | Registration | Extendable |
| Disciplinary fine | Fine | Yes |
| Referee assignment completed | Reimbursement | Yes |
| Match result approved | Charge | Yes, when `result_fee_type_id` is set |
| Match scheduled with venue | Other | Yes |

> Note: The finance bridge provides the **framework** and now includes default
> hooks for season-registration confirmation, match result approval,
> disciplinary fines, completed referee assignments, and scheduled venue
> bookings. Other modules can continue to create finance events programmatically via the shared
> finance event API.

## Accounting Integration Points

The module is designed to bridge to a full accounting system:

| Field | Purpose |
|-------|---------|
| `partner_id` | Maps to `res.partner` for accounting |
| `invoice_ref` | Links to accounting invoice |
| `external_ref` | External system reference |
| `currency_id` | Multi-currency support |
| `state` (`confirmed`/`settled`) | Aligns with the current lightweight workflow |

## Related Workflows

- [Season Registration](WORKFLOW_SEASON_REGISTRATION.md) — registration fee generation
- [Discipline Pipeline](WORKFLOW_DISCIPLINE_PIPELINE.md) — fine event generation
- [Match Day Operations](WORKFLOW_MATCH_DAY_OPERATIONS.md) — referee reimbursement events
