# ADR-0001: Portal Trust Boundaries

Owner: Federation Platform Team
Last reviewed: 2026-11-13
Review cadence: Every release
Status: Accepted

## Context

Portal club representatives and officials must create or update federation records without receiving broad backend ACLs. Controller-only checks are insufficient because direct model calls, guessed identifiers, or future routes could otherwise widen access.

## Decision

Portal writes use explicit, model-owned privilege boundaries:

- Controllers resolve the request user and the candidate record, reject malformed input, and invoke a model-owned portal method.
- Ownership and scope are enforced again in the model or shared privilege service.
- Elevated reads and writes go through `federation.portal.privilege`, including helpers such as `elevate()`, `portal_search()`, `portal_create()`, `portal_write()`, and `portal_call()` where applicable.
- The privilege boundary preserves the request user for audit attribution while keeping elevation narrow and explicit.
- Controllers must not perform business writes through raw `sudo()`.
- Positive in-scope, negative out-of-scope, direct-ID, and elevated-helper tests are mandatory for every privileged portal write surface.

## ORM access of portal users

Portal pages are not the only way in: a logged-in portal user can call the ORM
directly (`/web/dataset/call_kw`), which uses access rights and record rules,
not the page filters. Therefore:

- Every access right granted to a portal group on a `federation.*` model has a
  record rule for that same group (or a global one) that limits it to the
  user's scope. `ci/check_portal_record_rules.py` enforces this; the only
  exception, read-only seasons, is listed there with its reason.
- Portal rules scope through `user.portal_club_scope_ids` (whole-club tenures)
  and `user.portal_team_scope_ids` (team tenures), never through the raw
  `user.representative_ids`, which includes ended tenures and treats a team
  coach as a representative of the whole club.
- Creation goes through `portal_create` (a field allowlist, then elevation);
  portal groups therefore have no create right on players.
- A tenure or delegation ends by date. `is_current` is evaluated for today and
  never stored, and the stored portal scopes that record rules read are
  refreshed hourly (`_cron_refresh_time_based_state`) and on upgrade.

## Consequences

- Privilege escalation remains centralized and reviewable.
- Controller and ORM boundaries fail closed independently.
- Cross-club and team-scoped access can be regression-tested consistently.
- New portal features must reuse the privilege service or add a reviewed model-owned equivalent.
- Raw elevated controller writes are treated as security defects.


## Privileged mutation enforcement

Controllers may perform elevated reads only under the documented route and
ownership rules. They must not invoke `sudo().create()`, `sudo().write()`,
`sudo().unlink()`, or an elevated `action_*()` method directly. Mutations cross
an owning command service or `federation.portal.privilege`, which repeats the
scope assertion and records the audit event.

`ci/check_privileged_mutation_boundaries.py` enforces this repository-wide for
federation controllers. `ci/check_portal_sudo_guard.py` separately maintains the
reviewed inventory of portal elevated reads.

Destructive cross-addon deletion uses a process-local object identity and the
shared context-key constant from
`sports_federation_base.destructive_tokens`. Only the explicitly reviewed
match-day, scheduling, and publication integrity modules may import that token.
`ci/check_destructive_token_contract.py` rejects new consumers and raw copies of
the context-key string.


Result approval and contesting are owned by
`federation.result.commands`. The command re-resolves the target within the
actor's current club scope and is the only portal path allowed to supply the
process-local result-transition token. Superuser mode by itself never satisfies
a result role check.


## Workflow transition mechanics

Owned command services may delegate common state-transition mechanics to
`federation.workflow.transition`. The helper is not an HTTP or RPC boundary and
controllers must not call it directly. Eligibility and object scope remain in
the owning command service.


## Match-day command transactions

Controllers and wizards call `federation.matchday.commands`; they do not mutate
operational records directly. Public command methods establish a savepoint,
validate competition roles, and delegate transition mechanics to
`federation.workflow.transition`.


## Result workflow transactions

Result controllers call the scoped result command service. Backend actions and
portal commands establish savepoints, lock the match row, and delegate common
state and audit mechanics to `federation.workflow.transition`.
