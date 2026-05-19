# Sports Federation Officiating

Referee management and match assignment tracking. Maintains a registry of
officials, their certifications, and automates the assignment workflow for matches.

## Purpose

Manages the **referee lifecycle** separately from the club/team hierarchy. Referees
operate across tournaments and are assigned to specific matches in defined roles
(head referee, assistant, etc.).

## Dependencies

| Module | Reason |
|--------|--------|
| `sports_federation_base` | Core entities |
| `sports_federation_tournament` | Matches |
| `sports_federation_people` | Person concept reference |

## Models

### `federation.referee`

Master record for each registered official.

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char | Full name |
| `user_id` | Many2one | Optional linked portal user for self-service assignment response |
| `email` / `phone` / `mobile` | Char | Contact channels |
| `certification_level` | Selection | national / regional / local / trainee |
| `active` | Boolean | Active in the registry |
| `certification_ids` | One2many | Certification history |
| `match_assignment_ids` | One2many | Match assignments |
| `certification_count` / `assignment_count` | Integer | Stat-button counters |
| `notes` | Text | Free-form notes |

### `federation.referee.certification`

A specific certification held by a referee, with validity tracking.

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char | Certificate title |
| `referee_id` | Many2one | Referee |
| `level` | Selection | national / regional / local / trainee |
| `issue_date` / `expiry_date` | Date | Validity window |
| `issuing_body` | Char | Certification authority |
| `active` | Boolean | Currently valid |
| `notes` | Text | Remarks |

### `federation.match.referee`

Links a referee to a match in a specific role.

| Field | Type | Description |
|-------|------|-------------|
| `match_id` | Many2one | The match |
| `referee_id` | Many2one | The official |
| `tournament_id` | Many2one | Computed from match |
| `role` | Selection | head / assistant_1 / assistant_2 / fourth / table |
| `state` | Selection | assigned / confirmed / done / cancelled |
| `assigned_on` / `confirmed_on` / `completed_on` / `cancelled_on` | Datetime | Lifecycle timestamps |
| `confirmation_deadline` | Datetime | Match-based deadline, 48 hours before kick-off |
| `is_confirmation_overdue` | Boolean | Draft assignments that missed the deadline |
| `assignment_ready` | Boolean | Whether the assigned official can be confirmed |
| `readiness_feedback` | Text | Operator-readable explanation for readiness gaps |
| `response_note` | Text | Optional note supplied by the official when confirming or declining |
| `notes` | Text | Assignment notes |

- **SQL constraint**: unique (match_id, referee_id, role) — prevents duplicate
  role assignments.

### `federation.match` officiating extension

Matches receive computed officiating-readiness fields so staff can spot issues
before the match goes live.

| Field | Type | Description |
|-------|------|-------------|
| `referee_assignment_count` | Integer | Number of linked officiating assignments |
| `required_referee_count` | Integer | Expected official count from the tournament rule set |
| `confirmed_referee_count` | Integer | Officials already confirmed |
| `missing_referees_count` | Integer | Gap between required and confirmed assignments |
| `overdue_referee_confirmation_count` | Integer | Draft assignments that missed the deadline |
| `is_officially_ready` | Boolean | True when required roles are covered and no readiness issues remain |
| `official_readiness_issues` | Text | Aggregated shortage / overdue / certification issues |

## Key Behaviours

1. **Certification tracking** — Expiry dates allow monitoring whether officials
   meet current requirements.
2. **Role-based assignment** — Each match can have multiple referees in distinct
   roles.
3. **Confirmation governance** — assignments expose a 48-hour confirmation deadline,
   overdue status, and block confirmation when the referee is inactive or lacks a
   valid certification window for the match.
4. **Match readiness visibility** — matches show confirmed counts, shortages, overdue
   confirmations, and aggregated officiating issues in the form and list views.
5. **Assignment state machine** — assigned → confirmed → done / cancelled.
6. **Tournament context** — Assignments carry a computed tournament reference for
   filtering and reporting.
7. **Odoo 19-safe view inheritance** — the match readiness stat button inherits the
   base match form with `hasclass('oe_title')`, which avoids the platform warning
   triggered by raw `@class` XPath selectors during module loading.
7. **Finance bridge integration** — When `sports_federation_finance_bridge` is installed,
   assignments that reach `done` automatically create reusable reimbursement events.
8. **Portal self-service** — When `sports_federation_portal` is installed, linked officials can review, confirm, or decline their own draft assignments through the portal.
