# Post-Cutover Implementation Phases

Package 7 is a release-qualification gate. Do not begin the next structural phase until its automated gates pass and the acceptance record has no unresolved critical or high defect.

## Decision gate

Use the Package 7 result to select the next work:

1. Route, publication, access, migration, or end-to-end handoff failure: create a focused stabilization package first.
2. Correctness passes but performance budgets fail: profile and address measured hotspots before refactoring.
3. Correctness and performance pass: continue with Phase 8.

## Phase 8: Public projection consolidation

Make `federation.public.competition.queries` the single publication-aware query boundary. Legacy tournament page controllers become redirect-only adapters. Consolidate edition, division, match-day, schedule, format, result, standings, and bracket projections. Add runtime tests for foreign division IDs, unpublished children, archived editions, stale publications, and canonical redirects.

Success means no compatibility controller renders current domain data and every anonymous query applies the same publication boundary.

## Phase 9: Format-engine modularization

Split graph validation, round-robin generation, knockout and placement generation, bye resolution, progression, and fixture materialization into focused services behind the current orchestration facade. Preserve deterministic outputs and existing model and XML identities.

Success means each generator has focused tests, preview performs no hidden writes, repeated materialization is idempotent, and all existing stage-graph tests remain green.

## Phase 10: Match and schedule ownership cleanup

Create one authoritative schedule-normalization path across round, match day, slot, venue, playing area, publication slot, and operational slot. Keep tournament, calendar, scheduling, approval, match-day, venues, format, and finance responsibilities separated.

Success means create, write, onchange, compute, and inverse paths no longer implement competing normalization rules.

## Phase 11: Concurrency and idempotency hardening

Add independent-cursor tests and database authority for result approval versus contest, standings freeze versus recompute, schedule publication versus amendment, referee overlap, portal resubmission, integration replay, finance-event creation, and match-day command replay.

Success means each consequential command defines locking, idempotency, audit ordering, and retry semantics.

## Phase 12: Performance qualification

Benchmark small, medium, and large competition datasets. Measure graph generation, materialization, fairness scheduling, validation, standings recompute, portal queries, public match-day latency, memory, and deterministic repeatability. Set CI budgets only after collecting stable baselines.

Success means budgets represent real federation scale and regressions fail with actionable diagnostics.

## Phase 13: UX consolidation

Guide administrators through Overview, Registration, Format, Calendar, Scheduling, Approval, Match Days, Results, and Standings. Present prerequisites, blockers, ownership, and the next valid action without exposing addon boundaries or migration terminology.

Success means federation administrators, club representatives, officials, and visitors can complete their workflows without knowing the internal module architecture.
