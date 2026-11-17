# Glossary

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Use these terms in menus, help text, workflows and user guides. Model names
belong in technical sections only. The [competition model](../architecture/competition-model.md)
describes how the competition records relate to each other. The translated
terms per language live in the [translation glossary](../../i18n/glossary/glossary.pot)
(see [Translations](../development/translations.md)).

## Competition terms

| Term | Meaning | Model |
| --- | --- | --- |
| Competition template | Reusable competition definition shared across seasons ("National League"). | `federation.competition` |
| Season competition (edition) | One season's run of a competition, with its roles, policy and lifecycle. Say *season competition* or *competition* to operators; *edition* is the technical name. | `federation.competition.edition` |
| Division | A playing group inside a season competition, planned, staffed and published on its own. The public website may call a published division a *tournament page*. | `federation.tournament` |
| Competition Hub | The visual planner opened from **Federation > Competitions > Competitions** (**Open Competition Hub** / **Open Workspace**). It promotes one next action per competition. | `sports_federation_setup_flow` client action |
| Registration | An enrolment request. Qualify it: *season registration* (team for a season) or *competition entry* (team for a division). | `federation.season.registration`, `federation.competition.entry` |
| Participant set | The finalized team list of a division that the format is built from. | `federation.participant.set` |
| Participant | A team's confirmed place in a division. | `federation.tournament.participant` |
| Format / structure | The versioned playing format (stages, groups, progression) of a division. Freezing it makes its fixtures authoritative. | `federation.competition.structure` |
| Stage | One part of a format, such as a pool round or a knockout bracket. | `federation.structure.stage` |
| Fixture | A logical "who plays whom" pairing, possibly with placeholders ("Winner R1 M2"). | `federation.fixture` |
| Round | A logical pairing or bracket round. Not a date. | `federation.tournament.round` |
| Game day (match day) | A dated event at a venue with courts, capacity and live state. Operator copy says *game day*. | `federation.matchday` |
| Slot | A playable court and time on a game day. | `federation.schedule.slot` |
| Schedule | The working plan that assigns fixtures to slots. | `federation.schedule` |
| Publication | An immutable, reviewed snapshot of a schedule. Replaced, never edited. | `federation.schedule.publication` |
| Match | The game actually played, with live state and result. | `federation.match` |
| Game-day roster / line-up | The players a team brings to one game day; shared by all its matches that day. Players not playing a given match are crossed out per match. | `federation.match.sheet` |
| Standings | The table computed from approved results; can be frozen. | `federation.standing` |

## Workflow and status terms

| Term | Meaning |
| --- | --- |
| Streamlined | Competition workflow mode in which one operator may complete routine checkpoints once validation passes. Commands, snapshots and audit events still run. |
| Independent Review | Workflow mode in which another responsible person approves protected work (schedules, line-ups, results). |
| Advanced / Custom | Workflow mode in which an advanced user configures each checkpoint. |
| Draft, Ready, Live, Finished | The presentation states of a season competition. Detailed states stay on the owning records. |
| Readiness words | The six shared words shown for "is this fine?". See [readiness vocabulary](../architecture/readiness-vocabulary.md). |
| Blocking vs warning-only | A blocking issue stops the current step. A warning lets the step proceed but requires follow-up; where configured, a manager must record a reason. |
| Publication (visibility) | Public visibility controlled by `website_published` and the relevant visibility toggles. Not every public surface has its own *published* state. |
| Advanced Federation Tools | Security group that makes raw, specialist and recovery menus visible. It controls discoverability only, not permissions. |

## Result and lifecycle states

| Record | States | Source |
| --- | --- | --- |
| Result | `draft → submitted → verified → approved`, with `contested` and `corrected` removing the result from official standings until it is approved again | [Result pipeline](../workflows/result-pipeline.md) |
| Standings | `draft → computed → frozen`; public visibility is separate | [Standings lifecycle](../workflows/standings-lifecycle.md) |
| Player licence | `draft → active → expired` or `cancelled` (older *revoked* wording is compatibility-only) | [Player licence](../workflows/player-license.md) |
| Division | `draft → open → in_progress → closed`, or `cancelled` | [Tournament lifecycle](../workflows/tournament-lifecycle.md) |
| Match | `draft → scheduled → in_progress → done`, or `cancelled` | [Match-day operations](../workflows/match-day-operations.md) |

The full list of canonical states and their owners is in
[state and ownership](../architecture/state-and-ownership.md).
