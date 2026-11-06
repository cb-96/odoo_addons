# State and ownership

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Canonical lifecycle states and ownership boundaries for the core federation
records. Controllers, record rules, tests and workflow documents must match
this table and the model selections. Competition-chain records (entries,
participant sets, structures, schedules, publications) are described in the
[competition model](competition-model.md).

## Canonical records

| Record | Module | Primary owner | Create path | Canonical states | Ownership boundary | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `federation.tournament` (division) | `sports_federation_tournament` | Federation competition operations | Competition setup, back office | `draft`, `open`, `in_progress`, `closed`, `cancelled` | Federation-owned season competition scope | The portal shows divisions only through the competition projection and only for teams in the user's current whole-club or team scope. Archived competitions and divisions are hidden from portal workflows. |
| `federation.match` | `sports_federation_tournament` | Federation competition operations | Backend UI, scheduling services, wizards | `draft`, `scheduled`, `in_progress`, `done`, `cancelled` | Federation-owned tournament/stage/group | Future matches require active, ready team rosters once the roster deadline is reached; official standings inclusion is further gated by `include_in_official_standings` when `sports_federation_result_control` is installed. |
| `federation.schedule.slot` | `sports_federation_calendar` | Calendar operations prepare capacity; scheduling assigns fixtures; approval publishes the resulting schedule | Match-day calendar and scheduling views | `available`, `break`, `blocked` | Federation-owned match day / playing-area scope | A slot belongs to one match day. Fixture assignment and overlap validation are enforced server-side. |
| `federation.standing` | `sports_federation_standings` | Federation competition operations | Backend UI, recompute/freeze actions | `draft`, `computed`, `frozen` | Federation-owned tournament/stage/group | Only computed or frozen standings are publication candidates. |
| `federation.tournament.participant` | `sports_federation_tournament` | Federation competition operations | Created from finalized participant sets; back office for manual corrections | `registered`, `confirmed`, `withdrawn`, `eliminated` | Federation-owned division; team eligibility is checked server-side | Finalizing a team list creates the confirmed participants, and each participant gets a roster prepared. Portal users do not write this record directly. |
| `federation.competition.entry` | `sports_federation_registration` + `sports_federation_portal` | Club representative submits/corrects/withdraws within team scope; federation registration roles review | Club portal or public competition registration page; Registration Desk | `draft`, `submitted`, `approved`, `rejected`, `withdrawn` | Entry team must be in the authenticated representative's current team/club scope; writes are audited through the portal privilege boundary | A returned entry is `draft` with a review note. Resubmission reuses the same `(window, team)` row. Only federation roles approve, return/reject, or finalize participants. |
| `federation.season.registration` | `sports_federation_base` + `sports_federation_portal` | Shared: club representative submits, federation staff confirms | Portal form or backend UI | `draft`, `submitted`, `confirmed`, `cancelled` | Team must belong to one of the submitting user's represented clubs | Portal extension adds `submitted`, `user_id`, and `rejection_reason`. Rejecting a registration returns it to `draft`; there is no persistent `rejected` enum. |
| `federation.operation.task` | `sports_federation_portal` | Projection only; source workflow retains lifecycle ownership | Idempotent source synchronization | `open`, `acknowledged`, `done` | Current whole-club representatives see their club's work; team-scoped representatives see only their assigned teams; managers use the manager queue | Expired representatives lose scope. Confirmed registrations without a roster project a task but do not create a roster. No task transition substitutes for a source action; source status is checked for the actual viewer, and unreadable/missing sources are unavailable. |
| `federation.finance.event` | `sports_federation_finance_bridge` | Federation finance operations and approved workflow hooks | Backend UI or workflow automation | `draft`, `confirmed`, `settled`, `cancelled` | Source record remains authoritative; finance staff own settlement/cancellation | Season-registration confirmation and match finance hooks create events automatically. |

## Archive behaviour

Core master-data records have explicit archive and restore actions so
operational records do not disappear through ad hoc writes to `active`.

| Record | Archive guardrail |
| --- | --- |
| `federation.club` | Clubs can only be archived after their active teams are archived. |
| `federation.team` | Teams can only be archived when all linked season registrations are cancelled. |
| `federation.season` | Open seasons must be closed or cancelled before they can be archived. |
| `federation.tournament` | Open or in-progress divisions must be closed or cancelled before they can be archived. |
| `federation.competition.edition` | Archiving hides the competition and its divisions, entries, matches, line-ups, rosters, duties, game days and tasks from portal workflows; open tasks are closed. **Restore** makes them visible again. System administrators can **Delete permanently** test competitions; master data is never deleted. |

## Transition ownership

| Record | Transition owners | Guardrails |
| --- | --- | --- |
| `federation.tournament` | Federation staff and the guided competition finish | Portal reads revalidate the caller's visible team or club scope before any elevated detail read. |
| `federation.match` | Federation staff, scheduling services, result-control roles | Public routes are read-only. Match completion may trigger bracket advancement, and result-control transitions may trigger non-frozen standings recomputation. |
| `federation.schedule.slot` | Calendar owns slot capacity and lifecycle; scheduling assigns fixtures; schedule approval publishes the resulting schedule | Slot availability and capacity are prepared by `sports_federation_calendar`; assignment validation is enforced by `sports_federation_scheduling`; approved schedules are immutable and published by `sports_federation_schedule_approval`. |
| `federation.standing` | Federation staff | Frozen standings block recomputation unless forced. |
| `federation.tournament.participant` | Participant-set finalization; federation staff for corrections | Division/team eligibility is validated on create and update. |
| `federation.competition.entry` | Portal club representatives for submission, correction/resubmission, and withdrawal; federation registration roles for approval, return, rejection, and participant finalization | Team ownership is asserted before creation and records are re-resolved within current team scope. Elevated writes and calls provide an explicit team/window domain to `federation.portal.privilege`. Submission also validates window dates, division eligibility, duplicate entry, and capacity. |
| `federation.season.registration` | Portal club representatives for submission/cancel, federation staff for confirm | Controllers validate club ownership and the model must enforce ownership as defense in depth. |
| `federation.finance.event` | Federation finance staff for confirm/settle/cancel; approved workflow hooks for draft creation | Auto-created events must stay idempotent per source record and fee type. |

## Enum reconciliation

Use the model enums below in code, docs, and tests:

- Division (`federation.tournament`) lifecycle ends in `closed`, not `completed`.
- Match lifecycle ends in `done`, not `completed`.
- Competition planning is handed over through registration, format freeze, calendar capacity, scheduling, approval publication, and match-day execution.
- Schedule slots use the calendar lifecycle `available`, `break`, and `blocked`; schedule approval protects published snapshots from routine edits.
- Competition entry review uses `draft`, `submitted`, `approved`, `rejected`, and `withdrawn`; a return is represented by `draft` plus a federation review note.
- Participants may also be `eliminated`; this is distinct from finalized participant-set lines.
- Season registration review uses `submitted`; there is no `rejected` state in the current model.
- Finance event lifecycle uses `settled`; `invoiced` and `paid` are future integration concepts, not current model states.
- Seasons only open from `draft`, close from `open`, and return to `draft` from `cancelled`.
- Divisions only open from `draft`, start from `open`, close from `in_progress`, and return to `draft` from `cancelled`.

## Review checklist

- New controller writes must validate represented-club ownership before any `sudo().create()` or state change.
- Portal competition and match-day reads must revalidate the user's current `portal_club_scope_ids` and `portal_team_scope_ids` before any elevated read or cross-team search.
- Portal roster detail, roster-line edit, and roster-line license paths must resolve ids through the shared portal privilege boundary instead of raw elevated browse calls.
- Public website routes must enforce `website_published` and the relevant visibility toggle before reading data with `sudo()`, and compatibility redirects must resolve records through those publication-scoped domains up front.
- State transitions referenced in docs and workflows must match the real selection values in the models.
