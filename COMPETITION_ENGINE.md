# Competition Engine

This implementation provides role-owned capabilities and explicit handovers for competition planning and operations.

## Addons

1. `sports_federation_competition_core`: identity, roles, lifecycle and events.
2. `sports_federation_registration`: application queue and finalized participant sets.
3. `sports_federation_format`: versioned logical structures and fixtures.
4. `sports_federation_calendar`: physical match days, round allocations and capacity.
5. `sports_federation_scheduling`: one-way fixture-to-slot assignments, pure validation and deterministic proposals.
6. `sports_federation_schedule_approval`: independent review and immutable publication snapshots.
7. `sports_federation_matchday`: live operational control and incidents.

## Required handovers

Registration finalizes a participant set. Format freezes a structure. Calendar prepares physical capacity. Scheduling submits a complete schedule. Approval publishes an immutable snapshot. Match-day operations execute only a published snapshot.

## Migration policy

The legacy monolithic engine has been removed from the addon set. New and existing operational flows use the ownership split. Databases upgraded from a release that installed the legacy addon require the normal reviewed upgrade/migration procedure before production rollout; do not silently reinterpret existing production records.


## Schedule handoff operator handoff

The operator path is fully exposed in the backend: Schedule Planner submits a
validated revision, Schedule Review Queue provides independent request-changes
or approval decisions, Publication exposes approved schedules and immutable
publication history, and Match-Day Operations consumes only the current live
publication. Submission creates its pending review atomically when the approval
addon is installed; there is no operator-visible intermediate state that
requires a separate "start review" action.

## Phases 5.1.1 to 5.3: publication and live operations

Schedule review decisions are command-only: ACLs are read-only and the review
model rejects direct decision-field writes. Live publications are scoped and
versioned per match day. Publication replacement uses a dedicated wizard,
requires a replacement reason, locks the match day during version allocation,
and rejects stale confirmations.

Match-Day Control exposes readiness, the exact live publication, published
matches, court state, incidents, immutable sessions and operational deviations.
Opening a day freezes the publication digest in a session. Live moves, delays,
postponements and cancellations update only operational match fields; the
approved publication and `published_slot_id` remain immutable. Every deviation
records actor, reason, old/new slot, session and publication, and emits an audit
event.
