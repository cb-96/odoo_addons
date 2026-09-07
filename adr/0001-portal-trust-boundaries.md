# ADR-0001: Portal Trust Boundaries

Last updated: 2026-08-20
Owner: Federation Platform Team
Last reviewed: 2026-08-20
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
