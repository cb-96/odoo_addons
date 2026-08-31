# Deterministic Release Pilot Scenario

Owner: Federation Platform Team
Review cadence: Every release candidate

This scenario is the P3 operational acceptance path. It complements module tests
by proving that one federation storyline can be followed across ownership
boundaries without hidden setup or direct database edits.

## Automated gate

Run the complete release-focus verification:

```bash
python3 ci/check_release_focus_contract.py
scripts/ci/run_rc_validation.sh focus
```

The focus lane runs the lifecycle, finance, and public browser tours together
with the schedule-amendment, approval immutability, officiating, governance,
portal-security, compliance, and pilot-readiness tests.

## Pilot storyline

1. Create a season and competition edition.
2. Open registration and finalize the participant set.
3. Freeze the competition structure and generate fixtures.
4. Prepare match-day capacity and assign every fixture to a slot.
5. Submit the schedule for independent review and publish the approved revision.
6. Assign named officials or a club officiating duty and resolve shortages.
7. Open match-day control, record results, and approve official results.
8. Recompute and publish standings.
9. Confirm the public competition, schedule, format, and standings pages.
10. Confirm finance-event creation, settlement, export readiness, and traceability.
11. Amend one published schedule through a replacement revision and verify that
    the original publication and audit evidence remain immutable.
12. Verify that an unrelated portal user cannot read or mutate another club's
    registration, roster, officiating, result, or compliance records.

## Acceptance evidence

Record the release-candidate commit, database name, commands, start/end time,
all automated results, and any manual observations in the release runbook. A
release candidate is not accepted while any focus-lane test is skipped, flaky,
or dependent on manual data repair.
