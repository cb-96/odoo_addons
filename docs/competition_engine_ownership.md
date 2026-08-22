# V2 Competition Workflow Ownership

The V2 ownership chain is the supported competition-planning architecture. No
production data migration is required solely for this ownership clarification.

## Capability ownership

- Competition Core owns edition lifecycle and role assignments.
- Registration owns entries and versioned finalized participant sets.
- Format Studio owns stage topology, logical fixtures, standings snapshots, and progression.
- Calendar owns physical match days, courts, and availability slots.
- Scheduling owns fixture-to-slot assignments and fairness proposals.
- Schedule Approval owns independent review and immutable publications.
- Result Control owns the complete result lifecycle.
- Match-Day Operations owns live execution and incidents.

## Domain event contract

Events are past-tense facts. Producers emit only after a successful state change. Consumers must be idempotent and may not mutate the producer aggregate. Event payloads contain stable record IDs, version/revision, actor, and reason where applicable.

Required events: participant_set_finalized, structure_frozen, stage_standings_frozen, stage_progression_applied, matchday_capacity_ready, schedule_submitted, schedule_approved, schedule_published, matchday_opened, result_approved, result_contested, result_corrected, matchday_closed.
