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
Users who can read an edition may see its readiness summary, but this does not
grant access to registration-window or format-structure records. The planner
limits its internal readiness lookups to that edition and keeps record access
with registration managers and competition designers, respectively.

Operational handoff counts remain role-scoped as well. Roster follow-up is
available only when the caller can read team rosters and finalized participant
sets with their lines; match-day, lineup, official, and result counts require
read access to their source records. An edition reader without those domain
permissions can still use the planner's setup routes; unavailable operations
are marked unavailable instead of bypassing access controls or presenting an
incomplete count as zero.

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
wizard explains the practical effect of Streamlined, Independent Review, and
Advanced / Custom workflow policies before the competition is created.

The `competition_planner_intent` browser tour qualifies discoverability of the
current action, direct blocker routing affordance, waiting-step terminology, and
keyboard focus. Model tests cover exact-target routing and competition scoping.

## Direct action contract

The Owl planner obtains window actions through direct ORM calls and passes the
returned dictionaries to the web action service. Hand-built window actions must
therefore include the ordered `views` pairs required by the browser runtime;
`view_mode` remains present for the conventional server-side action contract.
Model regressions cover step, exact-record blocker, and operational actions.

## Simplified resumable workspace (19.0.4.0.0)

Competition Hub is the ordinary entry and always reopens the visual planner. It promotes one `primary_action` and one unified readiness summary. Direct team selection materializes registration records in the registration addon; the format picker generates and freezes structures through format commands; game-day setup continues directly into the complete competition scheduling wizard. Preset, format, venue, hours, and slot-duration defaults are remembered on the edition and are backfilled by the 19.0.4.0.0 migration.

The former owner-module router remains callable as `action_open_advanced_workspace`. Exact records, audit data, and recovery actions are retained; only ordinary menu discoverability changes.
