# Acceptance suites

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Human and staging acceptance scenarios, grouped by capability. Automated
release lanes are described in [release qualification](../README.md); these
suites cover what automation cannot prove on its own: real browsers,
independent transactions, restored data and novice users.

| Suite | Covers |
| --- | --- |
| [Competition acceptance](competition-acceptance.md) | Release-level competition lifecycle sign-off (checked by `ci/check_release_qualification.py`) |
| [Human acceptance test](human-acceptance-test.md) | Full federation walkthrough with realistic roles, data and devices before tagging a candidate |
| [Novice usability](novice-usability.md) | Protocol for first-time users across the main journeys |
| [Performance qualification](performance-qualification.md) | Competition performance measurements |
| [Role journeys](role-journeys.md) | Portal overview (`/my`), task projection and return navigation |
| [Duty coverage and restored-database](duty-coverage.md) | Official coverage, plus restored-database, concurrency, recovery and role-journey validation |
| [Communications](communications.md) | Participant inbox, preferences, digests and delivery recovery |
| [Mobile match day](mobile-match-day.md) | Court capture, interruption recovery, official and manager mobile pages |
| [Visual scheduling](visual-scheduling.md) | Visual planner, candidate comparison and progression impact |
| [Workspace UX](workspace-ux.md) | Role home, context continuity, empty and error states, event time zones |
| [Member lifecycle](member-lifecycle.md) | Optional member and family services |
| [Platform hardening](platform-hardening.md) | Court cache, document revisions, job retry, finance boundaries |

## Rules for evidence

- Record the exact candidate commit with every observation.
- Use staging data and test accounts only; never real guardian documents or
  production credentials.
- Record failures, assistance and blocked scenarios, not only successes. Use
  `pass`, `fail`, `blocked` or `not_run`; a blank is never a pass.
- Synthetic fixtures for the evaluators (`ci/evaluate_*.py`) test the
  evaluators, not the product.
- Keep evidence files outside the repository.

## Adding a suite

Add scenarios to the suite of the capability they test. Create a new suite only
for a new capability, link it from the table above, and describe current
behaviour and gates, not the delivery of a change.
