# Sports Federation Competition Engine

Version: 19.0.1.8.0
Owner: Federation Platform Team
Last reviewed: 2026-08-20
Review cadence: Every release

Guided competition planning, fixture generation, gameday scheduling, validation, revisioned publication, and concurrency-safe planner operations.

## Normal operator journey

1. Select or create a season competition.
2. Create a division and choose a standard format.
3. Add and confirm teams.
4. Lock entries and generate the match structure.
5. Create match days and their court/time slots.
6. Assign or auto-schedule matches.
7. Resolve blocking issues.
8. Validate and publish.

Use simple defaults for normal leagues, tournament days, and cups. Custom stage graphs, progression mappings, fairness tuning, revisions, and shared match days are advanced tools.

## Supported formats

- single round robin
- double round robin
- knockout
- pool then bracket
- manual structure

## Core safeguards

- one match per planner slot
- hard overlap prevention
- configurable rest and consecutive-match warnings
- optimistic planner revision checks
- idempotent assignment and unassignment paths
- undo, redo, and safe swaps
- validated and live schedule snapshots
- manager-only warning overrides and publication
- collaboration presence and stale-write feedback
- extension contract normalization and fault isolation

## Architecture

The public workspace facade delegates to dedicated access, auto-schedule configuration, extension, planner-state, read-model, and validation seams. Further decomposition of stage, gameday, planner-write, publication, and fairness orchestration remains desirable.

## Tests

Contract suites cover read models, write guards, extensions, concurrency, and ACLs. Additional suites cover auto-scheduling, performance smoke, production-like simulations, and tournament tours.

## Change guidance

Do not add a new user-visible state or planner issue shape without updating workflow contracts, frontend behavior, and regression tests. Do not expose internal revisions or state-machine details in the normal workflow unless the operator must act on them.
