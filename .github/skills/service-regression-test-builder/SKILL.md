---
name: service-regression-test-builder
description: 'Builds compact regression tests for services, wizards, and workflow entrypoints in this repo. Use when changing scheduling, progression, standings, result control, roster checks, or other cross-record business logic.'
argument-hint: 'Describe the business rule or service behavior that changed'
user-invocable: true
---

# Service Regression Test Builder

## What This Skill Produces

This skill creates compact, deterministic regression tests around the smallest public behavior that proves a service or workflow rule works in this repository.

Use it when:
- changing scheduling or generation logic in `sports_federation_format` or `sports_federation_scheduling`
- changing standings or stage progression behavior
- changing result approval or official standings behavior
- changing roster deadlines, eligibility, or readiness checks
- fixing a bug in a shared service and needing proof it stays fixed

## Repo Examples

Good anchors in this repo:
- `sports_federation_format/tests/test_stage_graph_engine.py`
- `sports_federation_scheduling/tests/test_fairness_solver.py`
- `sports_federation_result_control/tests/test_result_control.py`
- `sports_federation_rosters/tests/test_participant_readiness.py`

## Procedure

1. Pick the smallest public entrypoint.
   - wizard `action_generate()`
   - standings `action_freeze()`
   - result `action_approve_result()`
   - model action or helper that exposes the business rule

2. Build only the fixtures the rule truly needs.
   - season
   - club
   - teams
   - tournament
   - stage or group if required
   - participants with the right states
   - rule set only if the flow needs one

3. Keep fixtures deterministic.
   - fixed names and codes
   - explicit dates
   - minimal number of teams or matches
   - stable seeds and ordering

4. Assert observable outcomes, not internals.
   - created matches
   - advanced participants
   - resulting states
   - visible fields or counts
   - raised errors for invalid cases

5. Add one guard path.
   - missing rule set
   - unconfirmed participants
   - optional addon absent
   - invalid schedule precondition

6. Protect optional seams.
   - if code may run without another addon installed, avoid tests that silently depend on that addon unless the module under test depends on it
   - when shared logic checks optional models, add coverage for the guarded path

7. Re-run focused module CI.
   - the regression test should fail before the fix and pass after the fix when possible

## Decision Points

### If the service is called only through a wizard

Test through the wizard action unless the service itself is the stable public seam.

### If a workflow depends on record state transitions

Drive the real actions in order instead of writing final states directly unless the fixture cost becomes unreasonable.

### If multiple addons could own the test

Put the test in the addon that owns the behavior, not the addon that happened to expose the bug first.

### If the bug involved ordering or ranking

Assert the exact order, seeds, or ranks, not just the count of created records.

## Quality Bar

Finish only when the test:
- proves the bug or rule concretely
- uses the smallest realistic fixture set
- is deterministic across runs
- covers at least one negative or guard path when the logic has one
- passes in focused CI for the owning addon

## Example Invocations

- `/service-regression-test-builder add a regression test for round-robin standings freezing into knockout advancement`
- `/service-regression-test-builder build a minimal test for a roster deadline scheduling rule`
- `/service-regression-test-builder cover a wizard validation bug with one happy path and one guard case`