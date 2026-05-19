# Workflow: Governance Override

Formal exception-request process for situations that require bending standard
rules, with a compact decision flow and full audit traceability.

## Overview

Standard federation processes have rules and deadlines. When an exception is
legitimate, the governance module captures it as a formal **override request**
so the justification, decision, implementation, and outcome stay visible after
the immediate issue is resolved.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_governance` | Override requests, decisions, audit notes, outcomes |
| `sports_federation_base` | Core records referenced by requests |
| `sports_federation_people` | Player references |
| `sports_federation_tournament` | Tournament and match references |
| `mail` | Chatter tracking on requests |

## Common Override Scenarios

| Scenario | Example |
|----------|---------|
| Late registration | Club missed the deadline but has a valid reason |
| Eligibility waiver | Player needs an exception to a standard rule |
| Result correction | Approved result requires governance-backed correction |
| Standing adjustment | Federation needs a formal ranking correction |
| Administrative forfeit | A match outcome must be imposed administratively |

## Step-by-Step Flow

### 1. Override Request Creation

**Actor**: Federation official or authorised user
**Module**: `sports_federation_governance`

1. Navigate to **Federation → Governance → Override Requests**.
2. Create a new request with:
   - title
   - request type
   - target record (`target_model` / `target_res_id`)
   - justification in `reason`
3. The requester and request timestamp are recorded automatically.
4. The request starts in `draft`.

### 2. Submission And Withdrawal

**Actor**: Requester
**Module**: `sports_federation_governance`

1. Review the draft for completeness.
2. Submit the request: `draft` → `submitted`.
3. If the request needs correction before a decision is made, use **Withdraw**
   to return it from `submitted` to `draft`.

The withdraw path is only available while the request is still `submitted`.

### 3. Governance Decision

**Actor**: Governance officer
**Module**: `sports_federation_governance`

1. Review the submitted request, target record, and supporting context.
2. Add audit notes if the review needs extra findings or commentary.
3. Decide the request while it is still `submitted`:
   - **Approve**: `submitted` → `approved`
   - **Reject**: `submitted` → `rejected`
4. The standard approve/reject actions create a decision record automatically.

There is no separate `under_review` state in the current model. Operationally,
review happens while the request remains `submitted`.

### 4. Implementation

**Actor**: Federation administrator
**Module**: `sports_federation_governance` plus the affected owning module

1. If approved, implement the exception in the relevant workflow.
2. Record the operational note in `implementation_note` when useful.
3. Mark the request implemented: `approved` → `implemented`.
4. Implementation writes an outcome-log row so later review can see what was
   actually done, not just what was approved.

### 5. Closure

**Actor**: Governance officer or federation administrator
**Module**: `sports_federation_governance`

1. Once follow-up is complete, close the request.
2. Only `implemented` or `rejected` requests can move to `closed`.

## Audit Trail

The complete audit trail includes:

- request creation with requester and timestamp
- submission and any withdrawal back to draft
- approval or rejection decision rows
- audit notes with author and timestamp
- implementation notes and outcome-log rows
- chatter log of tracked state changes

## State Diagram

```
Override Request: draft → submitted → approved → implemented → closed
                         ↘ draft     ↘ rejected → closed

Decision: approved / rejected
          (recorded when the request leaves submitted)
```

## Security Model

| Group | Permissions |
|-------|-------------|
| Federation Staff | Can create override requests |
| Governance Officer | Can review, approve, reject, and close requests |

## Generic Target

Override requests use a **model/res_id pattern** and can link to many record
types, including:

- `federation.season.registration` — late registration exception
- `federation.player` — eligibility waiver
- `federation.match` — result correction or replay follow-up
- `federation.sanction` — discipline exception handling
- `federation.team.roster` — roster limit exception

## Related Workflows

- [Result Pipeline](WORKFLOW_RESULT_PIPELINE.md) — contested results may require governance action
- [Discipline Pipeline](WORKFLOW_DISCIPLINE_PIPELINE.md) — disciplinary appeals or exception handling
- [Season Registration](WORKFLOW_SEASON_REGISTRATION.md) — late registration exceptions
- [Compliance Management](WORKFLOW_COMPLIANCE_MANAGEMENT.md) — compliance exceptions
