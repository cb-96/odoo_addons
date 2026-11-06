# Workflows

Owner: Federation Competition Operations
Last reviewed: 2026-11-06
Review cadence: Every release

The authoritative business processes, one file per subject. Each workflow
describes actors, owning addons, states, steps, decision points and related
workflows. When a state transition, ownership rule or operator journey
changes, update the matching workflow in the same change.

Workflows link to each other instead of repeating rules. The operator
walkthrough of the back office is in the [user guide](../user-guide/competition-workflow.md);
the canonical states of the core records are in
[state and ownership](../architecture/state-and-ownership.md).

## Competition

| Workflow | Covers |
| --- | --- |
| [Tournament lifecycle](tournament-lifecycle.md) | Season competition and divisions from setup, entries and format to schedule, play, standings, progression and finish |
| [Match-day operations](match-day-operations.md) | Game-day rosters, match sheets, officials, venue checks, live operations and controlled deviations |
| [Result pipeline](result-pipeline.md) | Score submission, verification, approval, contest and correction |
| [Standings lifecycle](standings-lifecycle.md) | Recompute, freeze, publication and the effect of result changes |
| [Public publication](public-publication.md) | Publishing competitions, schedules, standings and editorial content |

## Clubs, teams and people

| Workflow | Covers |
| --- | --- |
| [Club onboarding](club-onboarding.md) | New club, compliance intake, bank details, first season registration, portal access |
| [Season registration](season-registration.md) | Season creation, club and team registration, player licensing |
| [Player licence](player-license.md) | Licence creation, activation, expiry, suspension checks and reinstatement |
| [Roster management](roster-management.md) | Season rosters, eligibility, game-day rosters, locking and closure |
| [Officiating](officiating.md) | Referee registry, certification, assignment, confirmation and shortages |
| [Compliance management](compliance-management.md) | Document requirements, submissions, review and expiry |

## Exceptions, finance and data

| Workflow | Covers |
| --- | --- |
| [Governance override](governance-override.md) | The single exception engine for disputes, waivers and overrides |
| [Appeal and dispute](appeal-dispute.md) | Club-facing wrapper around governance overrides for result and standings disputes |
| [Discipline pipeline](discipline-pipeline.md) | Incidents, cases, sanctions and suspensions |
| [Financial tracking](financial-tracking.md) | Fee types, finance events, confirmation, settlement and handoff |
| [Data import](data-import.md) | CSV import wizards with dry run and governed live import |

## Workflow contracts

`ci/contracts/workflow_state_contracts.json` maps workflows to the model
states and required actions they document. `ci/check_workflow_state_contracts.py`
fails when:

- a model declares a state that the contract does not list (add it to the
  workflow and the contract, or remove it from the code);
- the contract lists a state the model no longer has;
- a required action method is missing.

Contracts currently exist for the tournament lifecycle, result pipeline and
standings lifecycle. Keep the contract, the workflow document and the model
selection in sync in the same change.

## Writing a workflow

Use the existing structure: overview, addons involved, models and states,
step-by-step flow with actor and addon per step, state diagram, decision
points, related workflows. Use menu paths exactly as they appear in
[backend navigation](../user-guide/backend-navigation.md), written as
**Federation > Area > Menu**.
