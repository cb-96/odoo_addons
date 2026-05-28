# Workflow: Discipline Pipeline

From match incident through review, decision, sanctions, suspensions, and case
closure.

## Overview

When an incident occurs during or around a match, federation staff capture it
as a **match incident**, group related facts into a **disciplinary case**, and
then record sanctions or suspensions as outcomes. The workflow is intentionally
auditable: incidents stay linked to the case, cases carry dated decisions, and
financial penalties flow into the finance bridge when enabled.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_discipline` | Incidents, cases, sanctions, suspensions |
| `sports_federation_tournament` | Match context where incidents occur |
| `sports_federation_people` | Player subject records |
| `sports_federation_officiating` | Referee as incident reporter |
| `sports_federation_base` | Club subject records |
| `sports_federation_finance_bridge` | Fine amounts as finance events |
| `sports_federation_governance` | Appeals or exceptional follow-up |
| `mail` | Chatter on discipline records |

## Step-by-Step Flow

### 1. Incident Reporting

**Actor**: Referee, match official, or federation staff
**Module**: `sports_federation_discipline`

1. During or after a match, create a **match incident** record.
2. Fill in the match context and at least one subject reference:
   - match
   - player
   - club
   - reporting referee
3. Choose an incident type such as `warning`, `yellow_card`, `red_card`,
   `misconduct`, `violence`, `admin_issue`, or `other`.
4. Add the minute and a factual description.
5. The incident is created in `new` status.
6. `date_reported` and `reported_by_user_id` are recorded automatically.

Incidents are visible from the match form and remain standalone until they are
attached to a case.

### 2. Case Drafting

**Actor**: Disciplinary staff
**Module**: `sports_federation_discipline`

1. Create a **disciplinary case** to group one or more related incidents.
2. The case receives an automatic reference number via `ir.sequence`
   (`FED-DISC-XXXXX`).
3. Link the relevant incident records.
4. Identify the subject: player, club, or referee.
5. Assign a responsible user if the review has a named case owner.
6. The case starts in `draft`.

### 3. Review

**Actor**: Case handler or disciplinary staff
**Module**: `sports_federation_discipline`

1. Submit the case for review: `draft` → `under_review`.
2. Linked incidents that were still `new` are marked `attached`.
3. Review the evidence: incident notes, match sheet, referee report, and any
   supporting material.
4. If the case was submitted too early or needs corrections, use **Reopen** to
   return it from `under_review` to `draft`.

The reopen path is only available while the case is under review. It is a
correction step, not a post-decision appeal mechanism.

### 4. Decision

**Actor**: Disciplinary committee or case handler
**Module**: `sports_federation_discipline`

1. Once the review is complete, decide the case: `under_review` → `decided`.
2. `decided_on` is recorded automatically.
3. Create one or more **sanctions** and/or **suspensions** as outcomes.

#### Sanctions

| Type | Description |
|------|-------------|
| `fine` | Monetary penalty |
| `warning` | Formal warning |
| `ban` | Competition ban |
| `point_deduction` | Standing penalty |
| `other` | Custom disciplinary outcome |

Each sanction records the target, effective date, and optional amount.

#### Suspensions

A suspension is a time-bound match ban for a player.

- `date_start` / `date_end` define the ban window.
- States: `draft` → `active` → `expired` / `cancelled`.
- Active suspensions are consumed by match-sheet eligibility checks.

### 5. Financial Recording

**Actor**: Federation administrator
**Module**: `sports_federation_finance_bridge`

1. When a sanction of type `fine` is created, the finance bridge can create a
   linked **finance event**.
2. The finance event keeps the sanction traceability through source fields.
3. Finance events follow their own lifecycle: `draft` → `confirmed` → `settled`
   or `cancelled`.

### 6. Appeal Or Exceptional Follow-Up

**Actor**: Sanctioned party, federation governance staff
**Module**: `sports_federation_governance`

1. If the decision is disputed, open an **override request** through the
   governance workflow.
2. Mark the case as `appealed` when the disciplinary record needs to show that
   the original decision is under formal challenge.
3. Governance outcomes may lead to operational follow-up outside the case, but
   the case remains the canonical history of the disciplinary review itself.

### 7. Case Closure

**Actor**: Disciplinary staff
**Module**: `sports_federation_discipline`

1. Once the disciplinary handling is complete, close the case: `decided` or
   `appealed` → `closed`.
2. `closed_on` is recorded automatically.
3. Any linked incidents that are not already closed are moved to `closed`.
4. The case remains as the permanent disciplinary record for the subject.

## State Diagram

```
Incident: new → attached → closed

Case: draft → under_review → decided → appealed → closed
              ↘ draft

Suspension: draft → active → expired
                        ↘ cancelled

Sanction: (no state machine — created as final)

Finance Event: draft → confirmed → settled
                                 → cancelled
```

## Integration Points

| Integration | Detail |
|-------------|--------|
| Match form | Incidents tab is available on matches |
| Player form | Discipline tab shows player history |
| Match sheets | Active suspensions block player eligibility |
| Standings | Point-deduction sanctions feed standing adjustments |
| Finance | Fine sanctions create or update finance events |

## Related Workflows

- [Match Day Operations](WORKFLOW_MATCH_DAY_OPERATIONS.md) — incident capture and match-sheet eligibility effects
- [Governance Override](WORKFLOW_GOVERNANCE_OVERRIDE.md) — appeal or exception handling
- [Financial Tracking](WORKFLOW_FINANCIAL_TRACKING.md) — fine payment tracking
