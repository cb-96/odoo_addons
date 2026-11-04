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
incomplete count as zero. Availability probes use model-level `check_access`
and treat `AccessError` as unavailable without broadening the caller's rights.
Calendar Planners can create and edit the guided game-day setup wizard. A
Competition Designer can read finalized participant sets and their lines, but
cannot change registration data; this is the read-only input needed to review
format choices.

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

The format picker supports **Groups then knockout** for tournament-day and
season competitions. Operators choose the group count; the preview uses the
same feasibility estimate as format generation. The generated structure seeds
teams into groups, creates the knockout placeholders for the initial schedule,
and advances the top two from each group when that group's standings are frozen.

The former owner-module router remains callable as `action_open_advanced_workspace`. Exact records, audit data, and recovery actions are retained; only ordinary menu discoverability changes.

## Walkthrough usability findings

The end-to-end setup walkthrough found and corrected the following friction:

- The creation form labels its basic fields explicitly. Changing the season
	realigns a start date that falls outside the newly selected season, while
	preserving a start date already inside its range.
- The Competition Hub has one **Next Action** column. Planner guidance
	distinguishes the responsible competition role from the required
	federation-wide access groups and per-competition responsibility assignment.
	It names Registration Manager, Calendar Planner, Schedule Planner, and
	Schedule Approver as distinct access grants for their respective work areas.
- Newly added game days inherit active courts from their default venue, and the
	court selector is limited to that venue. Reopened game-day forms keep the
	business title.
- Schedule preview tabs and immutable review/publication snapshots use readable
	tables and summaries instead of compact JSON. The preview retains its action
	title, and the first-publication note no longer implies a replacement.
- Publication blockers open the review for the current schedule revision, not
	an unrelated historical review. The planner's glance label says
	**Earliest active game day** to distinguish it from the next setup action.
- Generated allocations preserve the exact fixture subset assigned to each
	game day. Partial runs skip fixtures allocated elsewhere, and existing
	cross-day duplicates block generation rather than becoming duplicate live
	schedules.

The game-day wizard opens in a dialog so its **Save & Plan Schedule**, **Save
and Close**, and **Discard** footer actions stay visible. A full-page form hid
those controls in the browser walkthrough. The supported continuation remains
the wizard's save-and-continue command.
