# Competition Engine V2

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

The legacy monolithic engine has been removed from the addon set. New and existing operational flows use the V2 ownership split. Databases upgraded from a release that installed the legacy addon require the normal reviewed upgrade/migration procedure before production rollout; do not silently reinterpret existing production records.
