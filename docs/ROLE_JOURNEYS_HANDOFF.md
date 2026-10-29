# Complete role-based journeys: implementation handoff

This package advances roadmap step 2 with a source-specific agent implementation brief,
a machine-readable acceptance contract and a tested evidence gate. It does NOT claim the
production journeys have already been implemented or live-tested.

## Files

- docs/ROLE_BASED_JOURNEYS_AGENT.md: implementation order, source findings, scope, tests,
  safe navigation, state handoffs and concrete completion criteria.
- ci/role_journeys/acceptance.json: five role journeys, 39 automated outcome checks and
  five novice tasks with an 80% unassisted completion gate.
- ci/verify_role_journeys.py: validates per-check evidence, artifact checksums, final commit,
  novice observations and a fresh release-confidence summary for that same candidate.
- ci/test_role_journey_gate.py: synthetic gate unit tests, NOT application evidence.

## Why a handoff rather than replacing addons

The supplied source metadata still names the earlier baseline commit. The user reports
executing release-confidence work, but the actual post-execution checkout and its evidence
are not supplied. Replacing whole addons would risk overwriting those changes. The agent
must inspect the actual checkout, preserve existing work and implement the brief there.
This package adds documentation/CI only; it does not reapply earlier patches or change
business models, roles, routes or approval policies.

## Use

Copy these files into the repository or apply the included role_journey_handoff.patch.
Do not do both. Give the agent this instruction:

> Implement docs/ROLE_BASED_JOURNEYS_AGENT.md in the actual checkout. Preserve step 1,
> reuse the existing task/query/command boundaries, implement and test all five role
> journeys, run real novice validation when available, rerun release confidence for the
> final candidate, and deliver the code patch plus evidence. Do not stop at a plan or deploy.

Run the gate's own tests with:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_role_journey_gate.py -v
```

The verifier requires actual journey-execution.json evidence. Missing novice sessions
remain blocked, even if all automated tests pass. Evidence claims need human review.
No Docker/Odoo/browser execution or novice sessions were performed while authoring this
handoff. The source review identifies targets to verify, not defects guaranteed to remain.
