Sports Federation Base
======================

Foundation module for the entire Sports Federation suite. Provides the core data
models that every other federation module depends on: **clubs**, **teams**,
**seasons**, and **season registrations**.

Purpose
-------

This module establishes the organisational hierarchy of the federation and acts as
the single source of truth for master data. All downstream modules
(people, tournaments, compliance, etc.) reference these entities.

Dependencies
------------

- `base`
- `mail`

Models
------

federation.club
~~~~~~~~~~~~~~~

Central record for each affiliated club. Stores contact details, full postal
address, logo, and founding date. Each club owns one or more teams.

Fields:

- `name` (Char): Club name (required).
- `code` (Char): Unique short code.
- `email` / `phone` / `mobile` (Char): Contact channels.
- `street` through `country_id` (Address): Full postal address.
- `founded_date` (Date): Date the club was founded.
- `logo` (Binary): Club emblem shown as the avatar.
- `team_ids` (One2many): Teams belonging to this club.

- **Mail thread** enabled for audit & chatter.
- **Unique code** constraint.
- **Stat button** to navigate to child teams.

federation.team
~~~~~~~~~~~~~~~

Represents a single squad within a club, classified by age category and gender.

Fields:

- `name` (Char): Team name (required).
- `code` (Char): Unique short code.
- `club_id` (Many2one): Parent club (required).
- `category` (Selection): `senior`, `youth`, `junior`, `cadet`, or `mini`.
- `gender` (Selection): `male`, `female`, or `mixed`.

- `name_search()` also matches on `code`.

federation.season
~~~~~~~~~~~~~~~~~

A time-bounded period during which competitions take place.

Fields:

- `name` / `code` (Char): Season label and unique code.
- `date_start` / `date_end` (Date): Season boundaries with `date_end >= date_start`.
- `state` (Selection): `draft -> open -> closed / cancelled`.
- `target_club_count` / `target_team_count` (Integer): Planned federation participation baseline.
- `target_tournament_count` / `target_participant_count` (Integer): Planned delivery targets for the season.

**Workflow:** active `draft` seasons can be opened, `open` seasons can be closed,
`draft` or `open` seasons can be cancelled, and only `cancelled` seasons can be
reset to `draft`.

Planning target values are validated as zero-or-greater so downstream reporting
and budgeting can safely compare actual activity against the season plan.

federation.season.registration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Enrols a team into a season. Auto-generates a sequence-based reference number on
creation (`FED/REG/YYYY/00001`).

Fields:

- `name` (Char): Auto-generated reference (readonly).
- `season_id` (Many2one): Target season.
- `team_id` (Many2one): Registering team.
- `club_id` (Many2one): Derived from the team and stored.
- `division` (Char): Optional division label.
- `state` (Selection): `draft -> confirmed / cancelled`.

**Constraint:** a team can register for a given season only once.

Lifecycle guardrails
--------------------

- Clubs can only be archived after their active teams are archived.
- Teams can only be archived when linked season registrations are cancelled.
- Open seasons must be closed or cancelled before archiving.
- The module exposes explicit archive and restore actions so lifecycle changes stay auditable in the backend UI.

Security
--------

Groups:

- **Federation User** (`group_federation_user`): Standard back-office users with read-only access on all models.
- **Federation Manager** (`group_federation_manager`): Administrators with full CRUD access on all models.

Both groups belong to the *Federation* app category (`module_category_federation`).

Menu Structure
--------------

Menu structure::

		Federation (root)
			Master Data
				Clubs
				Teams
			Seasons
			Registrations

Data Files
----------

- `data/ir_sequence.xml` – auto-numbering sequence for season registrations.

Extension Points
----------------

Other modules extend the base models:

- **Tournament** adds `competition_id` and `rule_set_id` to registrations.
- **Portal** adds `submitted` state and portal-user tracking.
- **Venues** adds `venue_id` to tournaments and matches.
- **Rosters**, **Result Control**, **Officiating** all extend `federation.match`.
