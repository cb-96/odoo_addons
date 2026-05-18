# Workflow: Club Representative Appeal & Dispute

End-to-end process for raising, reviewing, and resolving a result or standing
dispute submitted by a club representative.

## Overview

When a club representative believes a match result is incorrect or that a ruling
was applied unfairly, they can raise a formal dispute. The dispute is captured as
a `federation.override_request` and goes through the governance review pipeline.
The outcome may be a result correction, a sanction reduction, a standing
adjustment, or a formal rejection with reasons.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_governance` | Override requests, decisions, audit notes, outcomes |
| `sports_federation_result_control` | Result correction after approved override |
| `sports_federation_standings` | Standing adjustment after result correction |
| `sports_federation_portal` | Club representative raises appeal via portal or back-office |
| `sports_federation_notifications` | Notifications to all parties at key decision points |
| `sports_federation_base` | Core club / match records referenced by the request |
| `mail` | Chatter audit trail on the override request |

## Models

| Model | Key Fields |
|-------|-----------|
| `federation.override.request` | `title`, `request_type`, `target_model`, `target_res_id`, `reason`, `state`, `requester_id`, `decision_note`, `implementation_note` |

## Override Request Types relevant to appeals

| Type | Use case |
|------|---------|
| `result_correction` | Incorrect score, forfeit dispute, missing goal |
| `standing_adjustment` | Points awarded incorrectly; does not require score change |
| `eligibility_waiver` | Player ruled ineligible unfairly |
| `sanction_reduction` | Disciplinary fine or suspension reduction request |

## State Machine

```
draft → submitted → approved → implemented → closed
                 ↘ rejected  → closed
      ← withdrawn (submitted → draft)
```

## Step-by-Step Flow

### 1. Club Representative Raises a Dispute

**Actor**: Club representative
**Module**: `sports_federation_governance` (via portal or back office)

1. Navigate to **Federation → Governance → Override Requests** (back office) or
   the portal appeal section (if enabled).
2. Click **New** and fill in:
   - **Title** — clear one-line description of the dispute
   - **Request Type** — e.g. `result_correction`
   - **Target Record** — the match, result, or standing being disputed (set
     `target_model` and `target_res_id`)
   - **Reason** — full factual justification
3. Save in `draft` state. Add supporting attachments via the chatter.
4. Click **Submit** when ready: `draft → submitted`.

The requester and request timestamp are recorded automatically.

**Withdrawal**: if the club needs to amend the request before a decision is
made, click **Withdraw** to return from `submitted → draft`, edit, and resubmit.

### 2. Federation Staff Governance Review

**Actor**: Governance officer
**Module**: `sports_federation_governance`

1. Open the submitted request from
   **Federation → Governance → Override Requests → Submitted**.
2. Review the request, target record, and any supporting attachments.
3. Use the chatter to request clarification from the club if needed (keeps a
   timestamped record).
4. Add **Audit Notes** for internal commentary that should not be visible to
   the club representative.

There is no separate `under_review` state. Operational review happens while the
request remains in `submitted` state.

### 3. Decision Recording

**Actor**: Governance officer
**Module**: `sports_federation_governance`

After review, the governance officer decides:

- **Approve**: `submitted → approved`
  - Add a `decision_note` explaining the basis for approval.
  - The standard approve action creates a decision record automatically.
- **Reject**: `submitted → rejected`
  - Add a `decision_note` with the rejection reason.
  - The club representative is notified (if notifications module is installed).

The governance officer records only the decision — implementation is handled
separately to keep the audit trail clean.

### 4. Decision Notification

**Actor**: System
**Module**: `sports_federation_notifications`

On state transition to `approved` or `rejected`:

- The club representative (requester) receives a notification with the decision
  and the `decision_note`.
- The federation manager group receives a notification for `approved` requests
  that require implementation.

### 5. Outcome Implementation

**Actor**: Federation administrator
**Module**: `sports_federation_governance` + affected owning module

If approved:

| Request Type | Implementation Action |
|---|---|
| `result_correction` | Update `home_score` / `away_score` on the match; re-run result approval pipeline |
| `standing_adjustment` | Unfreeze standings if frozen; manually adjust; re-freeze |
| `eligibility_waiver` | Create or reinstate player license; update roster line |
| `sanction_reduction` | Edit disciplinary sanction amount or suspension length |

Steps:
1. Open the approved override request.
2. Implement the correction in the relevant module (see table above).
3. Record what was done in `implementation_note` on the request form.
4. Click **Mark Implemented**: `approved → implemented`.
5. An outcome-log row is written automatically so later review can see what was
   done, not just what was approved.

### 6. Closure

**Actor**: Governance officer or federation administrator
**Module**: `sports_federation_governance`

Once all follow-up is complete:

1. Open the `implemented` or `rejected` request.
2. Click **Close**: state → `closed`.
3. Only `implemented` or `rejected` requests can be closed.
4. Closed requests are read-only and permanently preserved in the audit trail.

## Audit Trail

The complete audit trail includes:

- Request creation with requester and timestamp
- Submission and any withdrawal back to draft (with timestamps)
- Decision (approve / reject) with decision note and officer identity
- Implementation note describing what was done
- Closure timestamp

All state transitions are logged in the chatter via `mail.tracking.value`.

## Impact on Standings

For result corrections that change scores:

1. Corrected result re-enters the approval pipeline: the administrator re-submits
   and re-approves the result.
2. Standings in `draft` or `ready` state recompute automatically.
3. If standings are `frozen`, the administrator must unfreeze → recompute →
   re-freeze (see [WORKFLOW_STANDINGS_LIFECYCLE.md](WORKFLOW_STANDINGS_LIFECYCLE.md)).

## Related Workflows

- [WORKFLOW_GOVERNANCE_OVERRIDE.md](WORKFLOW_GOVERNANCE_OVERRIDE.md) — Generic override request process for all exception types.
- [WORKFLOW_RESULT_PIPELINE.md](WORKFLOW_RESULT_PIPELINE.md) — Result approval and re-approval after correction.
- [WORKFLOW_STANDINGS_LIFECYCLE.md](WORKFLOW_STANDINGS_LIFECYCLE.md) — Freeze / unfreeze and recompute steps.
