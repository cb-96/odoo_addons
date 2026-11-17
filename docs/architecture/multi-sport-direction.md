# Multi-sport and multi-federation direction

Owner: Federation Platform Team
Last reviewed: 2026-11-09
Review cadence: Before starting this work
Status: Proposal, not scheduled

The platform was built for one sport (dodgeball, played under the WDBF cloth
rules) and one federation (Dodgeball Belgium). Most of it already works for any
team sport: registration, rosters, eligibility, formats, scheduling, officials,
results, standings, discipline and the portal. This document records how the
remaining sport- and federation-specific parts could become configuration, so
that another federation or another sport can use the platform later.

Nothing here is planned for a release. It is archived so that contributors know
the direction, and so that new work does not make the transition harder. When
someone starts on it, review this document first: the code will have moved on.

## Contents

- [Goals and non-goals](#goals-and-non-goals)
- [What is specific today](#what-is-specific-today)
- [Design principles](#design-principles)
- [Proposed data model](#proposed-data-model)
- [Migration path](#migration-path)
- [Guidance for work done before then](#guidance-for-work-done-before-then)
- [Open questions](#open-questions)

## Goals and non-goals

There are three separate goals with very different costs:

| Goal | What changes | Cost | Pursued |
| --- | --- | --- | --- |
| Another federation, same sport | Name, logo, colours, policy defaults | Small | Yes |
| Another sport | Scoring, score sheet, cards, official roles, court app | Medium to large | Yes |
| Several federations in one database | Data separation in every model, rule and report | Large | No |

One database per federation is how Odoo is normally run, and it keeps every
existing access rule valid. Multi-tenancy is therefore out of scope.

Also out of scope until a federation needs them: per-player statistics, player
positions, and a plug-in framework for scoring. Four built-in scoring types
cover most team sports; a new type is a small change to the core, not an
extension point.

## What is specific today

Reviewed on 2026-11-09. Use this as a starting point, not as a complete list.

| Area | Where | What is specific |
| --- | --- | --- |
| Federation identity | Portal templates, `sports_federation_portal/static/src/scss/federation_portal.scss` | "Dodgeball Belgium" text and the `--dbb-…` brand colours are hard-coded. |
| Parental approval age | Portal approval overview, task projection, roster eligibility | The age 16 is fixed in code; rule sets already have an `age_limit` field. |
| Team categories | `category` selection on `federation.team` | Senior, youth, junior, cadet and mini are fixed values; eligibility checks "senior". |
| Scoring | `sports_federation_live_workspace` (`court.py`, `policy.py`, court app) | Sets with WDBF set points (2 for a won set, 1 for a drawn set); the classic sets-won score is also supported. |
| Score sheet | `sports_federation_rosters/report/` | WDBF rule references, blue cards and the players-per-match limit in labels. |
| Official roles | Referee assignments, club duties, coverage requirements | Fixed selection: head, assistant 1, assistant 2, fourth, table. |
| Rules | `sports_federation_rules` | Already generic: points for win, draw and loss, line-up sizes, age limits, tie-breaks. |

No time zone is hard-coded; game days carry their own event time zone.

## Design principles

- **One federation per database.** Federation identity comes from the Odoo
  company and website.
- **Sport rules are data, not code.** A sport is a set of records: scoring
  profile, card types, official roles, labels. Only the small, closed list of
  scoring types lives in code.
- **Legal rules are not sport rules.** The parental approval age depends on
  country and federation policy, so it belongs in federation settings, not on
  the sport.
- **Invisible for single-sport federations.** The sport defaults from settings
  and is hidden when only one sport exists.
- **Sport words are translatable record fields** (period name, card names,
  role names), so the Dutch and French translations carry over.
- **Today's behaviour is the default.** Every change ships with data that
  reproduces the current dodgeball behaviour exactly.

## Proposed data model

### New models

| Model | Key fields | Replaces |
| --- | --- | --- |
| `federation.sport` | `name`, `code`, `scoring_profile_id`, `default_match_player_max`, `default_gameday_roster_max`, `period_label` (translatable: "Set", "Half", "Period") | Dodgeball assumptions in code and comments |
| `federation.scoring.profile` | `scoring_type` (closed list: `sets_with_points`, `sets_won`, `running_score`, `periods_summed`), `period_count_max`, `period_win_points`, `period_draw_points`, `period_draw_allowed`, `score_sheet_layout` | WDBF set points in the live workspace and court app; the score sheet layout |
| `federation.match.period` | `match_id`, `sequence`, `home_score`, `away_score`, `outcome` (home, away, draw), `home_points`, `away_points` | Sport-specific set storage in the live workspace |
| `federation.card.type` | `sport_id`, `name` (translatable), `color`, `effect` (warning, temporary, ejection), `duration_minutes`, `counts_toward_suspension` | Card handling on the score sheet and in discipline |
| `federation.official.role` | `sport_id`, `code`, `name` (translatable), `sequence`, `club_nominated` | The fixed role selection on referee assignments and club duties |
| `federation.age.category` | `name` (translatable), `min_age`, `max_age`, `is_adult` | The team category selection and "senior" checks in eligibility |

### Changes to existing models

| Model | Change |
| --- | --- |
| `res.company` and settings | Federation name, logo and brand colours; `parental_approval_age` (default 16); `default_sport_id` |
| `federation.competition` | `sport_id`, defaulting from settings, required |
| `federation.rule.set` | Optional `scoring_profile_id` override; points, line-up sizes and `age_limit` stay as they are |
| `federation.team` | `age_category_id` replaces `category` |
| `federation.match` | Keeps `home_score` and `away_score` as the aggregate result; `period_ids` holds the details |
| `federation.match.referee`, `federation.match.club.referee.duty` | The `role` selection becomes `role_id`; role codes stay stable for the court app and the API |

### Packaging

- **Core addons** contain no dodgeball terms, rule references or brand colours.
- **A new `sports_federation_dodgeball` addon** holds the dodgeball sport, the
  WDBF scoring profile, card types (yellow, red, blue), official roles, the WDBF
  score sheet layout and its own translations. It contains data and the score
  sheet template only, no business logic. That keeps a sport package cheap and
  avoids a plug-in framework.

## Migration path

Ordered from lowest to highest risk. Each change ships on its own, changes
nothing for Dodgeball Belgium, and keeps every existing dodgeball test green;
those tests are the regression net. The first two changes are useful on their
own: they already let another dodgeball federation install the platform.

### Federation identity from settings

- Name, logo and colours come from the company and website; the portal
  stylesheet uses theme variables instead of `--dbb-…`.
- Data: fill the company fields with today's name and colours.
- Effort: small. Risk: low.

### Policy values as configuration

- Parental approval age in federation settings.
- Age categories as records with an `is_adult` flag; eligibility reads
  `is_adult` instead of the "senior" value.
- Data: create the five current categories, map `category` to
  `age_category_id`, keep the old field read-only for one release.
- Effort: small to medium. Risk: low.

### Sport and scoring profile

- Add `federation.sport` and `federation.scoring.profile`, `sport_id` on
  competitions, and the optional profile override on rule sets.
- Data: create the dodgeball sport and the WDBF profile and assign them to all
  competitions.
- Effort: medium. Risk: low.

### Official roles and card types as records

- Selections become many2one fields on referee assignments, club duties,
  coverage requirements and discipline.
- Data: one role record per current selection value, with the same code.
- Effort: medium. Risk: medium; this touches duty coverage, the portal and the
  court app.

### Generic match periods

- The live workspace, court app, standings and result control read and write
  `federation.match.period` and follow the scoring profile.
- Data: copy existing set scores into periods; recompute standings and compare
  them before and after on a copy of production.
- Effort: large, about as much as all previous changes together.
- Risk: **high**. It touches scoring, standings and the offline court app. Do it
  outside the competition season, after a full staging rehearsal.

### Score sheet and court app per scoring type

- The score sheet layout and the court app scoring mode follow the profile;
  WDBF texts move to the dodgeball addon.
- Data: none. Effort: medium. Risk: medium.

### Dodgeball as a data addon

- Move the dodgeball records and score sheet into `sports_federation_dodgeball`.
- Data: reassign the XML ids to the new addon in `ir.model.data`.
- Effort: small to medium. Risk: medium; XML id moves need care during upgrade.

### Proof with a second sport

- Add a second sport using `running_score` as a test fixture and demo data.
- Add a CI check that fails on sport-specific terms in core addons.
- Effort: small. Risk: low.

## Guidance for work done before then

These cost nothing extra and keep the transition cheap:

- Prefer sport-neutral words in new code and core texts: match, court or
  field, player, official. Put dodgeball-specific wording in labels that can
  later move to the sport record.
- Do not add new hard-coded rule numbers, card colours or WDBF references to
  core addons; put new sport rules on the rule set.
- Read limits and ages from the rule set or settings, not from constants.
- Keep selection values that might become records (roles, categories) stable,
  so they can be mapped one-to-one later.

## Open questions

- **Which second sport?** It decides whether `running_score` and
  `periods_summed` are enough (handball, basketball, korfball) or whether
  another scoring type is needed (tennis-style scoring, timed rounds).
- **Current set storage and standings.** How the live workspace stores sets and
  how standings compute set-based points were not reviewed in detail. The design
  of generic match periods starts with that review.
- **Federation demand.** Confirm interest from at least one other federation
  before starting the larger changes; the first two are worth doing regardless.
