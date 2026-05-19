# State And Ownership Matrix

Owner: Federation Platform Team
Last reviewed: 2026-04-20
Review cadence: Every release

This document records the canonical lifecycle states and ownership boundaries
for the federation records called out in the roadmap. It is intended to keep
controllers, record rules, tests, and workflow docs aligned with the code.

## Canonical records

| Record | Module | Primary owner | Create path | Canonical states | Ownership boundary | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `federation.tournament` | `sports_federation_tournament` + `sports_federation_portal` | Federation competition operations | Backend UI, scheduling services, website publication helpers | `draft`, `open`, `in_progress`, `closed`, `cancelled` | Federation-owned season / competition scope | Portal tournament workspaces only expose active tournaments (`open`, `in_progress`) and only for teams inside the user's current whole-club or explicit team scope. |
| `federation.match` | `sports_federation_tournament` | Federation competition operations | Backend UI, scheduling services, wizards | `draft`, `scheduled`, `in_progress`, `done`, `cancelled` | Federation-owned tournament/stage/group | Official standings inclusion is further gated by `include_in_official_standings` when `sports_federation_result_control` is installed. |
| `federation.standing` | `sports_federation_standings` | Federation competition operations | Backend UI, recompute/freeze actions | `draft`, `computed`, `frozen` | Federation-owned tournament/stage/group | Only computed or frozen standings are publication candidates. |
| `federation.tournament.participant` | `sports_federation_tournament` | Federation competition operations | Backend UI or confirmed tournament registration | `registered`, `confirmed`, `withdrawn` | Team's club within a federation tournament | Portal users do not write participants directly; confirmed registrations may create them. |
| `federation.tournament.registration` | `sports_federation_portal` | Shared: club representative submits, federation staff reviews | Portal form or backend UI | `draft`, `submitted`, `confirmed`, `rejected`, `cancelled` | Team must belong to one of the submitting user's represented clubs | This is the review buffer before participant creation. |
| `federation.season.registration` | `sports_federation_base` + `sports_federation_portal` | Shared: club representative submits, federation staff confirms | Portal form or backend UI | `draft`, `submitted`, `confirmed`, `cancelled` | Team must belong to one of the submitting user's represented clubs | Portal extension adds `submitted`, `user_id`, and `rejection_reason`. Rejecting a registration returns it to `draft`; there is no persistent `rejected` enum. |
| `federation.finance.event` | `sports_federation_finance_bridge` | Federation finance operations and approved workflow hooks | Backend UI or workflow automation | `draft`, `confirmed`, `settled`, `cancelled` | Source record remains authoritative; finance staff own settlement/cancellation | Season-registration confirmation and match finance hooks create events automatically. |

## Archive behavior

The core master-data records now expose explicit archive and restore actions in
the backend UI so operational records do not disappear through ad hoc writes to
`active`.

| Record | Archive guardrail |
| --- | --- |
| `federation.club` | Clubs can only be archived after their active teams are archived. |
| `federation.team` | Teams can only be archived when all linked season registrations are cancelled. |
| `federation.season` | Open seasons must be closed or cancelled before they can be archived. |
| `federation.tournament` | Open or in-progress tournaments must be closed or cancelled before they can be archived. |

## Transition ownership

| Record | Transition owners | Guardrails |
| --- | --- | --- |
| `federation.tournament` | Federation staff for lifecycle transitions; portal layer for read-only workspace access | Portal workspace helpers must revalidate both active-tournament scope and the caller's visible team or club scope before any elevated detail read. |
| `federation.match` | Federation staff, scheduling services, result-control roles | Public routes are read-only. Match completion may trigger bracket advancement, and result-control transitions may trigger non-frozen standings recomputation. |
| `federation.standing` | Federation staff | Frozen standings block recomputation unless forced. |
| `federation.tournament.participant` | Federation staff, confirmed registration flow | Tournament/team eligibility is validated on create and update. |
| `federation.tournament.registration` | Portal club representatives for submission/cancel, federation staff for confirm/reject | Controllers validate club ownership and the model enforces ownership as defense in depth. |
| `federation.season.registration` | Portal club representatives for submission/cancel, federation staff for confirm | Controllers validate club ownership and the model must enforce ownership as defense in depth. |
| `federation.finance.event` | Federation finance staff for confirm/settle/cancel; approved workflow hooks for draft creation | Auto-created events must stay idempotent per source record and fee type. |

## Enum reconciliation

Use the model enums below in code, docs, and tests:

- Tournament lifecycle ends in `closed`, not `completed`.
- Match lifecycle ends in `done`, not `completed`.
- Tournament registration review uses `submitted` and `rejected`.
- Season registration review uses `submitted`; there is no `rejected` state in the current model.
- Finance event lifecycle uses `settled`; `invoiced` and `paid` are future integration concepts, not current model states.
- Seasons only open from `draft`, close from `open`, and return to `draft` from `cancelled`.
- Tournaments only open from `draft`, start from `open`, close from `in_progress`, and return to `draft` from `cancelled`.

## Review checklist

- New controller writes must validate represented-club ownership before any `sudo().create()` or state change.
- Portal tournament workspace reads and match-day record rules must revalidate active-tournament scope plus the user's current `portal_club_scope_ids` and `portal_team_scope_ids` before any elevated read or cross-team search.
- Portal roster detail, roster-line edit, and roster-line license paths must resolve ids through the shared portal privilege boundary instead of raw elevated browse calls.
- Public website routes must enforce `website_published` and the relevant visibility toggle before reading data with `sudo()`, and slug or numeric compatibility routes must resolve records through those publication-scoped domains up front.
- State transitions referenced in docs and workflows must match the real selection values in the models.
