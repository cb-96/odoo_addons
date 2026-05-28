# Sports Federation Reporting

Cross-module analytical reports backed by PostgreSQL views plus scheduled report
snapshots. Provides read-only report models that aggregate participation,
officiating, compliance, finance, and tournament-readiness data into
operator-facing views.

## Purpose

Gives federation administrators a **dashboard-level view** of key metrics without
writing SQL or building custom reports. Each report model is a database view
that joins and aggregates data from multiple modules into a single, filterable
list or pivot view, while report schedules generate recurring weekly or monthly
CSV snapshots from inside Odoo.

## Dependencies

| Module | Reason |
|--------|--------|
| `sports_federation_base` | Clubs, teams, seasons |
| `sports_federation_people` | Players |
| `sports_federation_tournament` | Tournaments |
| `sports_federation_officiating` | Referees, assignments |
| `sports_federation_standings` | Standings data |
| `sports_federation_discipline` | Disciplinary data |
| `sports_federation_compliance` | Compliance data |
| `sports_federation_finance_bridge` | Finance events |
| `sports_federation_import_tools` | Inbound delivery failures for operator checklist reporting |

Audit dashboard surfaces:

- `Reporting > Portal Audit` groups privileged portal create/write/call activity
	emitted through `federation.portal.privilege`.
- `Reporting > Token Rotation Audit` groups manager-driven integration partner
	token rotation events emitted from the import-tools token rotation flow.
- both dashboards read the shared `federation.audit.event` log so additional
	audited workflows can reuse the same reporting contract later.

## Models (all SQL view-backed, `_auto = False`)

### `federation.report.participation`

Club participation summary per season.

| Field | Type | Description |
|-------|------|-------------|
| `season_id` | Many2one | Season |
| `club_id` | Many2one | Club |
| `team_count` | Integer | Teams registered |
| `player_count` | Integer | Players licensed |
| `tournament_count` | Integer | Tournaments entered |

### `federation.report.officiating`

Referee workload summary.

| Field | Type | Description |
|-------|------|-------------|
| `referee_id` | Many2one | Referee |
| `certification_level` | Char | Current level |
| `assignment_count` | Integer | Total assignments |
| `completed_assignment_count` | Integer | Completed assignments |

### `federation.report.compliance`

Compliance status overview by entity type.

| Field | Type | Description |
|-------|------|-------------|
| `target_model` | Char | Entity type |
| `compliant_count` | Integer | Entities in compliance |
| `missing_count` | Integer | Missing documents |
| `pending_count` | Integer | Awaiting review |
| `expired_count` | Integer | Expired documents |
| `non_compliant_count` | Integer | Explicitly rejected or non-compliant checks |

### `federation.report.finance`

Financial event summary by fee type and state.

| Field | Type | Description |
|-------|------|-------------|
| `fee_type_id` | Many2one | Fee category |
| `state` | Selection | Event state |
| `event_count` | Integer | Number of events |
| `total_amount` | Float | Sum of amounts |

### `federation.report.operational`

Tournament-level operational KPI view.

| Field | Type | Description |
|-------|------|-------------|
| `season_id` / `tournament_id` | Many2one | Scope of the KPI row |
| `participant_count` / `confirmed_participant_count` | Integer | Enrolment totals |
| `participant_confirmation_rate` | Float | Confirmed-participant percentage |
| `match_count` / `completed_match_count` | Integer | Match execution totals |
| `match_completion_rate` | Float | Completed-match percentage |
| `pending_finance_event_count` / `pending_finance_amount` | Integer / Float | Open finance follow-up tied to match operations |
| `open_club_compliance_count` | Integer | Outstanding club compliance checks for participating clubs |
| `readiness_status` | Selection | `healthy`, `attention`, or `blocked` |
| `readiness_note` | Text | Operator-readable summary of the active readiness blockers or follow-up work |

### `federation.report.standing.reconciliation`

Tournament-level standings coverage check.

| Field | Type | Description |
|-------|------|-------------|
| `confirmed_participant_count` | Integer | Confirmed tournament participants |
| `covered_participant_count` | Integer | Distinct participants represented in standings |
| `missing_participant_count` | Integer | Confirmed participants missing from standings coverage |
| `orphaned_participant_count` | Integer | Standings entries without a matching confirmed participant |
| `reconciliation_status` | Selection | `healthy`, `attention`, or `blocked` |
| `reconciliation_note` | Text | Operator-readable mismatch explanation |

### `federation.report.finance.reconciliation`

Finance follow-up queue by event.

| Field | Type | Description |
|-------|------|-------------|
| `finance_event_id` | Many2one | Source finance event |
| `counterparty_display` | Char | Club, player, referee, or partner name |
| `follow_up_status` | Selection | Draft / awaiting settlement / awaiting reference / complete / cancelled |
| `needs_follow_up` | Boolean | Whether the event still needs operator attention |
| `age_days` | Integer | Days since the event was created |
| `invoice_ref` / `external_ref` | Char | Reconciliation references |

### `federation.report.notification.exception`

Failed-notification queue backed by the notification log.

| Field | Type | Description |
|-------|------|-------------|
| `notification_log_id` | Many2one | Source notification log entry |
| `created_on` | Datetime | When the failed log was created |
| `target_model` / `target_res_id` | Char / Integer | Failing target record |
| `recipient_email` | Char | Intended recipient |
| `template_xmlid` | Char | Template attempted by the dispatcher |
| `message` | Text | Failure reason |

### `federation.report.finance.exception`

Missing automation queue for discipline-side fine events.

| Field | Type | Description |
|-------|------|-------------|
| `sanction_id` | Many2one | Fine sanction missing a linked finance event |
| `case_reference` | Char | Disciplinary case reference |
| `player_id` / `club_id` / `referee_id` | Many2one | Sanction subject |
| `expected_fee_type_id` | Many2one | Expected finance fee type |
| `expected_amount` | Monetary | Expected finance event amount |
| `issue_type` | Selection | Current exception classification |
| `issue_note` | Text | Operator-readable explanation |

### `federation.report.workflow.exception`

Cross-module queue for stalled result-control and governance work.

| Field | Type | Description |
|-------|------|-------------|
| `season_id` / `tournament_id` | Many2one | Seasonal or tournament scope when available |
| `match_id` / `override_request_id` | Many2one | Source record needing follow-up |
| `exception_type` | Selection | Verification backlog, approval backlog, review backlog, or implementation backlog |
| `responsible_user_id` | Many2one | Current accountable operator when known |
| `age_days` | Integer | How long the item has been waiting |
| `exception_note` | Text | Operator-readable queue explanation |

### `federation.report.season.checklist`

Season-by-season readiness checklist for high-volume federation administration.

| Field | Type | Description |
|-------|------|-------------|
| `season_id` | Many2one | Season being reviewed |
| `draft_season_registration_count` / `submitted_season_registration_count` | Integer | Season registration work queue |
| `draft_tournament_registration_count` / `submitted_tournament_registration_count` | Integer | Tournament registration work queue |
| `live_tournament_count` | Integer | Open or in-progress tournaments |
| `published_tournament_count` / `unpublished_tournament_count` | Integer | Public publication checklist |
| `workflow_exception_count` | Integer | Linked stalled workflow items |
| `checklist_status` | Selection | `healthy`, `attention`, or `blocked` |
| `checklist_note` | Text | Summary of the main operational blocker |

### `federation.report.season.portfolio`

Season-level planning portfolio that compares the Year 4 planning baseline with
current delivery, finance, and compliance position.

| Field | Type | Description |
|-------|------|-------------|
| `season_id` / `season_state` | Many2one / Selection | Planned season in scope |
| `target_*` / `actual_*` / `*_delta` | Integer | Planned vs actual clubs, teams, tournaments, and participants |
| `budget_amount` / `actual_finance_amount` / `budget_variance_amount` | Float | Planned vs actual finance position |
| `open_compliance_item_count` | Integer | Outstanding compliance load for confirmed clubs |
| `planning_status` / `planning_note` | Selection / Text | Operator-readable planning health |

### `federation.report.club.performance`

Club-by-club seasonal performance roll-up for tournament activity, results,
finance queue load, and compliance attention.

| Field | Type | Description |
|-------|------|-------------|
| `season_id` / `club_id` | Many2one | Club performance scope |
| `confirmed_team_count` / `confirmed_tournament_entry_count` | Integer | Seasonal participation footprint |
| `completed_match_count`, `win_count`, `draw_count`, `loss_count` | Integer | Competitive activity and outcomes |
| `goals_for`, `goals_against`, `goal_difference`, `win_rate` | Integer / Float | Performance detail |
| `pending_finance_event_count` | Integer | Open finance queue items for the club |
| `open_compliance_item_count` | Integer | Open club compliance items |
| `performance_status` / `performance_note` | Selection / Text | Operator-readable club status |

### `federation.report.schedule`

Persistent schedule for recurring application-layer report generation.

| Field | Type | Description |
|-------|------|-------------|
| `report_type` | Selection | Operational, reconciliation, compliance, board/audit packs, season portfolio, or club performance |
| `period_type` | Selection | Weekly or monthly cadence |
| `season_id` | Many2one | Optional season scope for season-based reports |
| `next_run_on` / `last_attempt_on` / `last_run_on` | Datetime | Scheduling metadata and last execution attempt |
| `last_run_status` | Selection | `never`, `success`, or `failed` |
| `last_failure_on` / `last_error_message` | Datetime / Text | Persisted failure state for the most recent failed generation |
| `consecutive_failure_count` | Integer | Number of failed generation attempts in a row |
| `generated_file` | Binary | Last generated CSV snapshot |
| `last_row_count` | Integer | Number of exported data rows |

Implementation note:

- Report-type-specific row builders and back-office action metadata now live in `services/report_schedule_builders.py`.
- Keep new schedule types in that registry so `federation.report.schedule` stays focused on cadence, CSV serialization, retention, and failure capture.

### `federation.report.audit.event`

Read-only audit log reporting view for privileged portal activity and
integration token rotations.

| Field | Type | Description |
|-------|------|-------------|
| `event_family` | Selection | `portal_privilege` or `integration_token` |
| `event_type` / `action_name` | Char | Normalized audit classification and originating method |
| `actor_user_id` | Many2one | User who triggered the audited action |
| `target_model` / `target_res_id` / `target_display_name` | Char / Integer / Char | Record affected by the audited action |
| `changed_fields` | Text | Comma-separated field names touched by the action when known |
| `description` | Text | Operator-readable audit summary |

### `federation.report.operator.checklist`

Operator-facing queue roll-up that consolidates the release-critical exception
surfaces into a single reporting menu.

| Field | Type | Description |
|-------|------|-------------|
| `queue_code` / `queue_name` | Selection / Char | Stable identifier and display name for the queue |
| `owner_display` | Char | Operational owner for the queue |
| `open_count` / `escalated_count` | Integer | Queue depth and escalated subset |
| `oldest_age_days` | Integer | Oldest unresolved item age |
| `status` | Selection | `healthy`, `attention`, or `blocked` |
| `summary` | Text | Operator-readable explanation of what the queue means |

## Key Behaviours

1. **Read-only views** — Analytical models use `_auto = False` with `init()` creating SQL views.
2. **Role-oriented reporting surfaces** — Operational KPIs, standings reconciliation, finance reconciliation, and compliance summaries are separated into task-specific menus instead of a single generic export path.
3. **Cross-module joins** — Operational KPIs combine tournament, standings, finance, and compliance data into one application-layer view.
4. **Recurring snapshots** — `federation.report.schedule` can generate weekly or monthly CSV snapshots and a daily cron refreshes active schedules.
5. **Reconciliation-first reporting** — Standings coverage, finance follow-up, failed-notification queues, missing discipline-finance events, and stalled workflow queues expose the specific gaps operators must resolve before relying on downstream outputs.
6. **Season operations checklist** — The reporting layer now includes a season-level checklist that surfaces review queues, publication gaps, and unresolved workflow exceptions in one place.
7. **Planning decision support** — Season portfolio and club performance views turn the reporting layer into a planning and delivery-monitoring surface instead of a pure export utility.
8. **Legacy CSV exports preserved** — The lightweight HTTP CSV endpoints remain available for ad hoc export use.
9. **Contract-tagged exports** — Authenticated CSV responses now include explicit contract and version headers for downstream consumers.
10. **Operator checklist** — Notification failures, workflow exceptions, finance follow-up, inbound delivery failures, blocked season readiness, and scheduled report failures now surface in one menu.
11. **Persistent schedule failure tracking** — Report schedules keep the last failure timestamp, error message, and consecutive failure count so recurring problems survive beyond transient logs.
12. **Generated-file retention** — Scheduled report artifacts are cleared automatically after the retention window in `DATA_RETENTION_POLICY.md`, while the schedule metadata and next run remain intact.

## CSV exports

Authenticated backend users can export lightweight KPI CSV files from the
reporting controllers:

- `/reporting/export/standings/<tournament_id>` — standings lines with tie-break notes
- `/reporting/export/participation/<season_id>` — season participation roster
- `/reporting/export/finance` — finance summary grouped by fee type and state
- `/reporting/export/finance/events` — detailed finance-event handoff export with reconciliation references and closure timestamps

Each export now exposes `X-Federation-Contract` and
`X-Federation-Contract-Version` headers. The detailed finance-event handoff
export uses the `finance_event_v1` contract.

For recurring in-application reporting, create records under **Federation → Reporting → Report Schedules**.
Each schedule stores the last generated CSV snapshot directly on the schedule record.
Use **Federation → Reporting → Operator Checklist** for the release-readiness
queue view that links back to the underlying exception surfaces.
