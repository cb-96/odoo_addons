# Sports Federation Result Control

Result lifecycle and approval workflow for match scores. Adds a formal
submit → verify → approve pipeline to match results, ensuring scores are
reviewed before being used in official standings.

## Purpose

Prevents unchecked score entry from flowing directly into standings or public
results. Federation staff submit results, verifiers check them, and approvers
sign off before the result is considered official.

## Dependencies

| Module | Reason |
|--------|--------|
| `sports_federation_tournament` | Matches |
| `mail` | Chatter and tracking |

## Models

### `federation.match` (inherited)

Extends the match model with result-control fields.

| Field | Type | Description |
|-------|------|-------------|
| `result_state` | Selection | not_submitted / submitted / verified / approved / contested / corrected |
| `result_submitted_by_id` | Many2one | Who submitted |
| `result_submitted_on` | Datetime | Submission timestamp |
| `result_verified_by_id` | Many2one | Who verified |
| `result_verified_on` | Datetime | Verification timestamp |
| `result_approved_by_id` | Many2one | Who approved |
| `result_approved_on` | Datetime | Approval timestamp |
| `result_contest_reason` | Text | Why the result was disputed |
| `result_correction_reason` | Text | Why the result was changed |
| `include_in_official_standings` | Boolean | Flag for standings computation |
| `result_audit_ids` | One2many | Detailed transition timeline for disputes and approvals |

### `federation.match.result.audit`

Immutable result-workflow timeline for a match.

| Field | Type | Description |
|-------|------|-------------|
| `match_id` | Many2one | The audited match |
| `event_type` | Selection | submitted / verified / approved / contested / corrected / reset |
| `from_state` / `to_state` | Char | Transition boundary |
| `reason` | Text | Contest or correction rationale |
| `description` | Text | Human-readable summary |
| `author_id` / `created_on` | Many2one / Datetime | Attribution and timestamp |

### Actions

| Method | Transition | Description |
|--------|-----------|-------------|
| `action_submit_result()` | `draft` or `corrected` → `submitted` | Staff records the score |
| `action_verify_result()` | → verified | Verifier confirms accuracy |
| `action_approve_result()` | → approved | Final sign-off; includes in standings |
| `action_contest_result()` | → contested | A party disputes the result |
| `action_correct_result()` | → corrected | Revised after contest |
| `action_reset_result_to_draft()` | contested or corrected → draft | Re-open the record for a controlled restart |

## Security Groups

| Group | Purpose |
|-------|---------|
| Result Verifier | Can verify submitted results |
| Result Approver | Can approve verified results |

## Key Behaviours

1. **Three-step approval** — submit → verify → approve ensures multiple eyes.
2. **Contest / correction** — Disputed results can be flagged and later corrected.
3. **Standings gating** — Only approved results set `include_in_official_standings = True`.
4. **Audit trail** — Every transition records who and when via user/datetime fields and a persistent `federation.match.result.audit` entry.
5. **Separation of duties** — Submitter, verifier, and approver must be distinct users for the same match.
6. **Auto recomputation** — Approve, contest, correct, and reset actions recompute linked non-frozen standings automatically.
7. **Approved score immutability** — Home and away scores cannot be edited while a result remains approved.
8. **Corrected resubmission** — A corrected result is expected to re-enter the pipeline through `submitted` before it becomes official again.
9. **Guided standings handoff** — Match forms now direct operators back to the owning tournament when the next task is standings review, standings publication, or public follow-up rather than another score edit.
