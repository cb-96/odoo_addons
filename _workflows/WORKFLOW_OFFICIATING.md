# Workflow: Officiating

End-to-end lifecycle for managing referees — from certification registration
through match assignment, confirmation, completion, and shortage alerting.

## Overview

The **officiating** domain tracks referees (`federation.referee`), their
certification records (`federation.referee.certification`), and per-match role
assignments (`federation.match.referee`). When a referee is assigned to a
match, they receive an automated notification. If the assignment is not
confirmed before the deadline, the system flags it as overdue and optionally
sends an alert to the referee coordinator.

## Modules Involved

| Module | Role |
|--------|------|
| `sports_federation_officiating` | Referee registry, certifications, match assignments |
| `sports_federation_tournament` | Match records |
| `sports_federation_notifications` | Referee assignment and shortage alert dispatching |

## Models

| Model | Purpose |
|-------|---------|
| `federation.referee` | Master referee record with contact info and certification level |
| `federation.referee.certification` | Dated certification for a specific officiating level |
| `federation.match.referee` | Assignment of one referee to one match in a specific role |

## Step-by-Step Flow

### 1. Referee Registration

**Actor**: Federation administrator
**Module**: `sports_federation_officiating`

1. Navigate to **Federation → Officiating → Referees** and click **New**.
2. Enter name, contact details (email, phone, mobile).
3. Set `certification_level` to the highest level held:
   `local` | `regional` | `national` | `international`.
4. Save. The referee is immediately available for match assignments.

### 2. Certification Records

**Actor**: Federation administrator
**Module**: `sports_federation_officiating`

1. On the referee form, open the **Certifications** tab.
2. Add one `federation.referee.certification` line per certification granted:
   - Certification number (unique per referee / level / issue date)
   - Level (matches the levels on the referee itself)
   - Issue date and optional expiry date
   - Issuing body
3. Active certifications (`active = True`) are considered valid.
4. An expired certification (`expiry_date` in the past) should be archived
   (`active = False`) by an admin; the system does not auto-archive.

Certification uniqueness: `(referee_id, level, issue_date)` — one certification
per level per issuance date.

### 3. Match Assignment

**Actor**: Federation referee coordinator
**Module**: `sports_federation_officiating`

1. Open the match record in **Federation → Tournaments → Matches**.
2. In the **Referees** tab (or from the Referees list), click **Add a line**.
3. Select the referee and assign a **role**:
   - `head` — Head Referee
   - `assistant_1` / `assistant_2` — Assistant Referees
   - `fourth` — Fourth Official
   - `table` — Table Official
4. Save. The assignment starts in state **`draft`** ("Assigned").
5. On creation, the notification dispatcher fires `send_referee_assigned` if
   `federation.notification.dispatcher` is available, sending an assignment
   notice to the referee.

Assignment uniqueness: `(match_id, referee_id, role)` — one role per referee per match.

### 4. Readiness Check

**Actor**: System (computed field)
**Module**: `sports_federation_officiating`

After assignment, the system computes:
- `confirmation_deadline` — 48 hours before the scheduled match kickoff.
- `is_confirmation_overdue` — True if past deadline and still in `draft`.
- `assignment_ready` — True when the assignment is `confirmed`, the referee
  is active, and holds a valid certification for the match's required level.
- `readiness_feedback` — human-readable summary of any blocking reasons.

These fields re-compute whenever match scheduling, referee certification, or
assignment state changes.

### 5. Referee Confirmation

**Actor**: Referee or federation administrator
**Module**: `sports_federation_officiating`

1. Referee or administrator sets the assignment state: **`draft` → `confirmed`**.
2. `confirmed_on` timestamp is recorded.
3. `assignment_ready` becomes True (assuming valid certification and active referee).

### 6. Overdue / Shortage Detection

**Actor**: System (notification scan) or administrator
**Module**: `sports_federation_officiating` + `sports_federation_notifications`

1. Assignments with `is_confirmation_overdue = True` are surfaced as a warning
   in the coordinator's dashboard and in the readiness feedback.
2. If the `sports_federation_notifications` module is installed, a scheduled
   notification scan can detect unconfirmed assignments and send alerts.
3. The coordinator resolves shortages by:
   - Following up with the originally assigned referee, OR
   - Cancelling the assignment (`draft` → `cancelled`) and assigning a replacement.

### 7. Match Completion

**Actor**: System or federation administrator (after match result entry)
**Module**: `sports_federation_officiating`

1. When a match is completed (state → `done`), assignments are marked **`done`**.
2. `completed_on` timestamp is recorded.
3. `done` assignments contribute to `assignment_count` on the referee record for
   performance and reporting purposes.

### 8. Cancellation

**Actor**: Federation coordinator
**Module**: `sports_federation_officiating`

1. Any assignment in `draft` or `confirmed` can be cancelled by setting state → **`cancelled`**.
2. `cancelled_on` timestamp is recorded.
3. Cancelled assignments remain in the record for audit purposes but are excluded
   from the assignment count and readiness checks.

## State Diagram

```
Assignment: draft (Assigned) → confirmed → done
                             ↘ cancelled
            draft → cancelled
```

## Certification States

```
Certification: active=True  (valid, current)
               active=False (archived/expired — set manually by administrator)
```

## Notification Triggers

| Event | Notification |
|-------|-------------|
| Assignment created | `send_referee_assigned` via notification dispatcher |
| Assignment overdue | Alert to referee coordinator (notification scan) |

## Key Decision Points

| Question | Outcome |
|----------|---------|
| No active certification at required level? | `assignment_ready = False`; readiness feedback lists reason |
| Confirmation deadline passed, still `draft`? | `is_confirmation_overdue = True`; flagged in dashboard |
| Match cancelled? | Coordinator cancels all assignments; `cancelled_on` recorded |
| Referee deactivated (`active = False`)? | All future assignments blocked; `assignment_ready = False` |

## Referee Availability & Self-Service

> **Note**: The availability model is a planned feature. The fields and steps
> below describe the intended design; the `federation.referee.availability`
> model may not yet be present in all installations. Check the module README
> for the current implementation status.

### Marking Availability Windows

**Actor**: Referee (portal) or federation coordinator (back office)
**Module**: `sports_federation_officiating` + `sports_federation_portal`

1. Referee logs into the federation portal.
2. Navigates to **My Availability** in the officiating section.
3. Creates `federation.referee.availability` records specifying:
   - **Start** and **End** datetime of the available window
   - Optional notes (e.g. "available only from 14:00")
4. Saves. Availability records are immediately visible to the coordinator.

Alternatively, the coordinator creates availability records on behalf of the
referee from the back office (**Federation → Officiating → Referees → Availability tab**).

### Assignment Engine Conflict Check

**Actor**: System (at assignment creation time)
**Module**: `sports_federation_officiating`

When the coordinator assigns a referee to a match:

1. The system checks whether the match's scheduled kickoff falls within any
   `federation.referee.availability` window for that referee.
2. If the match falls **outside** all recorded availability windows, a warning
   is shown on the assignment form: *"No availability record covers this match
   slot."*
3. The coordinator can override the warning and save the assignment (warnings
   do not block creation).
4. If no availability records exist for a referee, no conflict check is
   performed and no warning is raised.

The assignment engine does **not** prevent double-booking across matches: if
a referee is already assigned to another match that overlaps, the coordinator
sees this via the `assignment_count` field and the referee's assignment list.

### Portal Accept / Decline Flow

**Actor**: Referee (portal)
**Module**: `sports_federation_officiating` + `sports_federation_portal`

After an assignment is created in `draft` state and the referee receives the
assignment notification:

1. Referee opens the notification or navigates to **My Assignments** in the portal.
2. Views the match date, venue, and role.
3. Clicks **Confirm** or **Decline**:
   - **Confirm**: assignment state `draft → confirmed`.
   - **Decline**: assignment state `draft → cancelled`. The coordinator is
     notified to assign a replacement.

Both actions are available until the `confirmation_deadline` (48 hours before
kickoff) passes.

### Confirmation Deadline and Overdue Escalation

**Actor**: System + federation coordinator
**Module**: `sports_federation_officiating` + `sports_federation_notifications`

If the referee does not confirm or decline before the `confirmation_deadline`:

1. `is_confirmation_overdue` becomes `True` on the assignment.
2. The assignment is surfaced in the coordinator's overdue-assignment dashboard
   filter (**Federation → Officiating → Assignments → Overdue**).
3. If `sports_federation_notifications` is installed, the scheduled notification
   scan sends an overdue alert to the coordinator.
4. The coordinator:
   - Contacts the referee directly, OR
   - Cancels the assignment and assigns a replacement.

There is no auto-cancel on deadline expiry. The coordinator makes the final
decision on shortage resolution.

## Related Workflows

- [Match Day Operations](WORKFLOW_MATCH_DAY_OPERATIONS.md) — referee assignment within the broader match-day sequence
- [Tournament Lifecycle](WORKFLOW_TOURNAMENT_LIFECYCLE.md) — match scheduling that triggers officiating needs
