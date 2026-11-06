# Competition Core

Owner: Federation Competition Operations
Last reviewed: 2026-11-06
Review cadence: Every release

Lifecycle, responsibilities and domain events of a season competition
(`federation.competition.edition`). It is the first addon of the competition
chain described in the [competition model](../docs/architecture/competition-model.md).

## Models

| Model | Purpose |
| --- | --- |
| `federation.competition.edition` (extended) | Canonical lifecycle command, workflow policy, journey state and archive actions |
| `federation.competition.role.assignment` | Per-competition responsibilities: Competition Administrator, Registration Manager, Competition Designer, Calendar Planner, Schedule Planner, Schedule Approver, Match-Day Manager, Results Officer, Competition Director |
| `federation.competition.event` | Immutable past-tense domain events with aggregate, actor, time and JSON payload |
| `federation.competition.force.delete` / `.wizard` | Permanent deletion of test competitions |

## Lifecycle

`transition_competition_state(target, reason)` is the only way to change the
edition state and emits a competition event:

```text
draft → open → in_progress → closed
  ↘        ↘            ↘
   cancelled → draft
```

Closing is refused while close blockers remain; resetting a cancelled
competition to draft is refused while reset blockers remain. The guided finish
in the Competition Hub (`sports_federation_setup_flow`) drives these
transitions.

The edition also exposes a presentation state for operators (`journey_state`:
Draft, Ready, Live, Finished) and a blocker count, computed from the detailed
domain states.

## Workflow policy

`workflow_mode` selects how much independent review the competition needs:

| Mode | Effect |
| --- | --- |
| Streamlined (`simple`) | One operator may complete routine checkpoints after validation; commands, snapshots and audit events still run |
| Independent Review (`controlled`) | Schedule approval, result verification and approval, and similar checkpoints require another person |
| Advanced / Custom (`custom`) | Each checkpoint flag is configured individually |

The individual flags cover registration approval, structure freeze
confirmation, schedule approval and self-approval, automatic publication,
result verification and approval (including self-verification and
self-approval), standings freeze confirmation, automatic standings
recomputation and stage progression, and roster and match-sheet approval.

## Responsibilities and access

Role assignments route work inside one competition. They do not grant model
access: users also need the matching federation-wide groups (Federation User,
Registration Manager, Calendar Planner, Schedule Planner, Schedule Approver,
…). See the [competition workflow](../docs/user-guide/competition-workflow.md#1-create-with-a-meaningful-preset).

## Archive and permanent deletion

- Archiving a competition hides it and its divisions, entries, matches,
  rosters, line-ups, duties, game days and tasks from portal workflows. The
  archived list has an **Archived** filter and a **Restore** button (federation
  managers).
- **Delete permanently** (system administrators only) removes a test
  competition and everything that belongs to it, bypassing the evidence guards
  the same way a module uninstall does. Master data (clubs, teams, players,
  licences, seasons, season registrations, rosters, venues, courts, referees,
  rule sets) is never deleted; the parent competition template is removed only
  on request and only when no other competition uses it. If anything outside
  federation data would block the deletion, nothing is deleted and the blocker
  is reported. Each deletion is logged at WARNING level under
  `sports_federation.force_delete`.

## Navigation

The ordinary entry is **Federation > Competitions > Competitions**. The
advanced **Competition Overview** and **Competition Audit & Recovery > Role
Assignments** menus are defined here and shown to users with Advanced
Federation Tools.

## Tests

`tests/test_competition_core.py` covers lifecycle transitions and events, role
assignment uniqueness and required roles, and read-only edition access. Run with
`bash ci/run_tests.sh --module sports_federation_competition_core`.
