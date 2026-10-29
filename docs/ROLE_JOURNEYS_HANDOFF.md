# Complete role-based journeys: implementation and acceptance status

The role-journey implementation is present in `sports_federation_portal`; the source-specific
implementation brief, machine-readable acceptance contract and evidence gate remain useful
for review. The code has focused automated coverage, but this document does NOT claim staging,
full browser, novice, or release-confidence acceptance has passed.

## Files

- docs/ROLE_BASED_JOURNEYS_AGENT.md: implementation order, source findings, scope, tests,
  safe navigation, state handoffs and concrete completion criteria.
- ci/role_journeys/acceptance.json: five role journeys, 39 automated outcome checks, a
  partial mapping to executed tests, and five novice tasks with an 80% unassisted completion
  gate.
- ci/verify_role_journeys.py: validates per-check evidence, artifact checksums, final commit,
  novice observations and a fresh release-confidence summary for that same candidate.
- ci/test_role_journey_gate.py: synthetic gate unit tests, NOT application evidence.

## Implementation and validation status

The focused portal run passed 20 post-tests, including ordinary-role HTTP cases for club,
team manager, official, planner, reviewer, and manager accounts. The full
`sports_federation_portal` module run passed 161 tests with 61 post-tests. Python/frontend
helper and static checks passed. These results do not cover all acceptance checks. No
authorized staging configuration, approved sanitized fixture, browser operator, or novice
participants were provided. No production or staging service was used or changed.

Automated test mappings are intentionally partial and are listed in
`ci/role_journeys/acceptance.json`. Synthetic gate-verifier tests validate evidence format
only; they are not product or novice evidence. The role-journey gate remains blocked pending
complete application/browser checks, real novice observations, and fresh release confidence
for the final candidate.

## Use

Do not reapply the implementation patch or replace current addon files. Continue from the
actual checkout and use the acceptance contract to close the remaining gates:

> Complete the remaining role-journey acceptance checks against authorized staging,
> capture browser evidence and real novice sessions, map only actual assertions, then rerun
> release confidence for the final candidate. Do not deploy as part of this acceptance run.

Run the gate's own tests with:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_role_journey_gate.py -v
```

The verifier requires actual journey-execution.json evidence. Missing novice sessions
remain blocked, even if all automated tests pass. Evidence claims need human review.
The Odoo runs used disposable CI resources. No real-browser or novice sessions were
performed. The source review identifies targets to verify, not defects guaranteed to remain.
