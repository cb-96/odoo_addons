# Competition model

Owner: Federation Competition Operations
Last reviewed: 2026-11-06
Review cadence: Every release

This document describes the records behind a competition, which addon owns
each step, and the explicit handoffs between them. Operators never need these
records directly: the ordinary journey is
**Competition -> Teams -> Format -> Game days -> Schedule -> Publish -> Play -> Finish**
(see the [competition workflow](../user-guide/competition-workflow.md)).
Internal engine records remain available to advanced operators but do not
define the normal workflow.

## Authoritative entities

- **Competition**: recurring competition identity. Master data, closed/archived administratively.
- **Edition**: one season's competition lifecycle and roles. Derived from competition + season; finish/archive owns closure.
- **Division**: playing group and division rules. Derived from edition and follows its lifecycle.
- **Registration Window**: application round. Finalization owns the handoff to participants.
- **Participant Set**: finalized team list used by format. Derived from approved entries; replacements supersede history.
- **Participant**: team's confirmed place in a division. Derived from the participant set; withdrawn rather than reinterpreted.
- **Structure**: versioned playing format. Derived from participant set; freeze makes it authoritative for fixtures.
- **Stage**: one phase of a structure. Derived from structure and progression rules.
- **Fixture**: logical who-plays-whom pairing. Derived from stages/results; cannot disappear once operationalized.
- **Game Day**: date, venue, capacity and live operational state. Derived from edition planning.
- **Slot**: playable court/time on a game day. Derived from game-day capacity.
- **Schedule**: working fixture-to-slot plan. Derived from frozen fixtures and slots; publication closes a revision.
- **Publication**: immutable reviewed snapshot of a schedule. Superseded, never rewritten.
- **Match**: the game actually played, including live state and result. Materialized from a resolved fixture and linked to publication.

Every lifecycle handoff has explicit postconditions in
`federation.lifecycle.postconditions` (`sports_federation_setup_flow/models/lifecycle_postconditions.py`):
registration finalized, format frozen, schedule generated, schedule
published, match day opened, match day closed, competition finished and
competition archived.

## Capability ownership

| Capability | Addon | Owns |
| --- | --- | --- |
| Competition core | `sports_federation_competition_core` | Edition lifecycle, role assignments, domain events, archive and permanent deletion |
| Registration | `sports_federation_registration` | Registration windows, competition entries, versioned finalized participant sets |
| Format | `sports_federation_format` | Structures, stage topology, logical fixtures, stage standings snapshots and progression |
| Calendar | `sports_federation_calendar` | Physical game days, courts, allocations and availability slots |
| Scheduling | `sports_federation_scheduling` | Fixture-to-slot assignments, validation and fairness proposals |
| Schedule approval | `sports_federation_schedule_approval` | Independent review and immutable publications |
| Match day | `sports_federation_matchday` | Live execution, sessions, operational deviations and incidents |
| Result control | `sports_federation_result_control` | The complete result lifecycle |
| Guided setup | `sports_federation_setup_flow` | The Competition Hub planner and readiness projection; it calls the owners' commands and owns no competition state |

## Required handoffs

1. Registration finalizes a participant set.
2. Format builds a structure from that set and freezes it.
3. Calendar prepares physical capacity (game days and slots).
4. Scheduling submits a complete schedule for the frozen fixtures.
5. Approval publishes an immutable snapshot.
6. Match-day operations execute only a published snapshot.

Each step is explicit and the server remains authoritative for validation
and publication. Format creates no physical slots; calendar creates no
fixtures; match-day commands reject unpublished or superseded schedules.

## Domain events

Events are past-tense facts in `federation.competition.event`. Producers emit
only after a successful state change. Consumers must be idempotent and must
not mutate the producer aggregate. Payloads contain stable record IDs,
version or revision, actor, and reason where applicable.

Required events: `participant_set_finalized`, `structure_frozen`,
`stage_standings_frozen`, `stage_progression_applied`,
`matchday_capacity_ready`, `schedule_submitted`, `schedule_approved`,
`schedule_published`, `matchday_opened`, `result_approved`,
`result_contested`, `result_corrected`, `matchday_closed`.

## Registration chain

`federation.registration.window` → `federation.competition.entry` →
`federation.participant.set`. Public and portal registration resolve the open
window for the selected division and call the same validated submission
command, which enforces club ownership, eligibility, duplicate-entry and
capacity rules. Federation staff review entries from the competition; the raw
**Registration Desk** remains under **Competitions > Planning Tools** for
recovery and specialist work.

## Schedule review and publication

The Schedule Planner submits a validated revision. Submission creates its
pending review atomically when the approval addon is installed; there is no
separate "start review" action. The Schedule Review Queue records
request-changes or approval decisions. **Publishing** lists approved schedules
and the immutable publication history, and match-day operations consume only
the current live publication.

Review decisions are command-only: ACLs are read-only and the review model
rejects direct writes to decision fields. Live publications are scoped and
versioned per game day. Replacing a publication uses a dedicated wizard,
requires a reason, locks the game day while allocating the version, and
rejects stale confirmations.

## Live operations

Match-Day Control shows readiness, the exact live publication, published
matches, court state, incidents, immutable sessions and operational
deviations. Opening a game day freezes the publication digest in a session.
Live moves, delays, postponements and cancellations change only operational
match fields; the approved publication and `published_slot_id` stay
immutable. Every deviation records actor, reason, old and new slot, session
and publication, and emits an audit event.

## Matches and officiating

`federation.match` is the operational execution and result record. A valid
operational match is backed one-to-one by `federation.fixture` through
`logical_fixture_id`. Referee assignments, club duties, match sheets and
result control attach to `federation.match`.

New official assignments and club duties reject matches without a fixture.
Match-day bulk planning resolves matches only through the game day's current
live publication. Official history stays attached to retained publications,
while pending and upcoming portal views show only the current live
publication.

## Portal projection

The portal is a projection of these records. It owns no second competition
lifecycle and does not fall back to legacy tournament workspaces.

| Portal concern | Authoritative model |
| --- | --- |
| Competition | `federation.competition.edition` |
| Registration | `federation.competition.entry` |
| Participation | `federation.participant.set` |
| Fixture | `federation.fixture` |
| Physical day | `federation.matchday` |
| Schedule visibility | current live `federation.schedule.publication` |
| Live execution | `federation.matchday.session` |
| Result | fixture-linked `federation.match` |
| Standings | `federation.standing` |

Draft schedules, review evidence, approval notes and superseded publications
are never portal schedule sources. Portal access is scoped through represented
clubs and teams, and mutations go through `federation.portal.privilege`.
`ci/check_portal_competition_ownership.py` and
`ci/contracts/portal_competition_ownership.json` enforce this mapping.

## Guided setup boundary

The season competition is the only ordinary operator entry. The canonical
setup steps are: define divisions, add teams, define game days, generate the
schedule, publish the schedule, setup complete. Technical lifecycle states
remain authoritative in their owning models; the setup steps are a projection,
not a second state machine.

`federation.competition.setup.readiness.evaluate(edition)` decides the next
step, progress, blocker hint and counts. The edition form and the Competition
Hub use the same assessment. `action_open_next_workspace` remains available
for existing bookmarks and server actions and delegates to
`action_continue_setup`; `action_open_advanced_workspace` opens the technical
workspaces for advanced users and recovery work.

The setup flow is the integration owner until the competition addons can be
physically consolidated with a rehearsed migration. Model names, table names,
XML IDs, security groups, publications and audit history must stay stable
during any such move.

## Legacy competition engine

The former monolithic competition engine has been removed from the source
tree. Databases that once installed it must follow the retirement procedure
in the [release runbook](../operations/release-runbook.md#retiring-the-legacy-competition-engine)
before an upgrade can be called clean.

## Annual club player pool

A club season registration groups the club's annual player licences for approval
and billing. The licence is the canonical player-season registration. Team-level
season enrolment remains an internal team participation record, not a player
registration. Team roster and match-day eligibility require an active licence for
the same club and competition season, valid on the relevant date. See the
[annual player workflow](../workflows/club-season-player-registration.md).
