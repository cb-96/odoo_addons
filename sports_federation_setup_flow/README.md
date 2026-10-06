# Competition Setup Flow

This addon provides the guided backend setup journey for a season competition.
The Competition Planner is a read model and router: registration, format,
calendar, scheduling, approval, and publication commands remain in their
respective owner addons.

## Planner readiness

The planner and the season-competition form use the same readiness projection.
For every division it requires a finalized participant set containing at least
two teams and a latest frozen structure with at least one playable fixture,
built from that set. Across the competition it requires every playable fixture
to be allocated; each allocated match day must have usable capacity, a complete
working schedule, and a current live publication matching that schedule
revision. The first unresolved blocker is shown as the current setup step.

## Ownership boundary

Federation competition roles own edition-wide setup, division format freeze,
calendar and schedule planning, independent schedule review, and publication.
Club representatives use the portal for only their scoped team entries and club
operations; they cannot finalize participants or alter edition-wide setup.

For operator routes, recovery instructions, and the full lifecycle see
[`../docs/COMPETITION_UI_WORKFLOW.md`](../docs/COMPETITION_UI_WORKFLOW.md) and
[`../_workflows/WORKFLOW_TOURNAMENT_LIFECYCLE.md`](../_workflows/WORKFLOW_TOURNAMENT_LIFECYCLE.md).

Focused tests run through the repository's `ci/run_tests.sh` harness for
`sports_federation_setup_flow`.

## Operator-facing labels

Planner actions name the concrete work area, such as team entries and participants, competition stages and fixtures, match-day capacity, stage and match-day allocation, and independent review and publication.

## Actionable planner guidance

The planner exposes short business-language areas: Competition, Teams, Format,
Dates & venues, Schedule, and Review & publish. Waiting areas remain inspectable
and are labelled **Not ready**, rather than appearing locked.

Every current blocker is returned with its responsible role and a direct action.
The server resolves the blocker key again before opening anything, then routes to
the exact registration window, format, match day, schedule, or review when one
unambiguous record exists. The broader filtered workspace remains available as a
secondary action. Resolved or stale blocker keys are rejected and require a
planner refresh.

After the live schedule is ready, the planner switches from setup guidance to an
operational handoff with scoped links to match days and schedules. The creation
wizard explains the practical effect of Simple, Controlled, and Custom workflow
policies before the competition is created.

The `competition_planner_intent` browser tour qualifies discoverability of the
current action, direct blocker routing affordance, waiting-step terminology, and
keyboard focus. Model tests cover exact-target routing and competition scoping.
