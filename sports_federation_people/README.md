# Sports Federation People

Player master data and license management for the federation. Tracks every
registered player's personal information, club affiliation, and maintains a
complete licensing history across seasons.

## Purpose

Provides the **player** and **player license** models that underpin roster
management, eligibility checks, discipline tracking, and compliance workflows.
Every module that deals with individual athletes depends on People.

## Dependencies

- `sports_federation_base`: Clubs, teams, and seasons.

## Models

### `federation.player`

Master record for every registered individual. Names are split into first/last
for sorting and flexible display.

- `name`: Char (computed), stored as `last_name, first_name`.
- `first_name` / `last_name`: Char, legal name parts and both required.
- `birth_date`: Date of birth.
- `gender`: Selection with `male`, `female`, or `other`.
- `nationality_id`: Many2one to the nationality country.
- `club_id`: Many2one to the current club affiliation.
- `team_ids`: Many2many teams the player belongs to.
- `email` / `phone` / `mobile`: Contact channels.
- `photo`: Binary player photograph.
- `state`: Selection with `draft`, `active`, `suspended`, or `retired`.
- `license_ids`: One2many historical license records.
- `license_count`: Integer stat-button counter.
- `notes`: Free-form notes.

- **State machine**: draft → active → suspended / retired.
- **Stat button** navigates to license history.

### `federation.player.license`

Season-scoped license that proves a player's right to compete. A player may hold
multiple licenses across seasons, but only one active license per season applies.

- `name`: Char, auto-generated license number from a sequence.
- `player_id`: Many2one to the licensed player.
- `season_id`: Many2one to the covered season.
- `club_id`: Many2one to the club at time of issue.
- `issue_date` / `expiry_date`: Date validity window.
- `state`: Selection with `draft`, `active`, `expired`, or `revoked`.
- `category`: Selection for license category such as amateur or professional.
- `eligibility_notes`: Text eligibility remarks.
- `notes`: Additional notes.

- License numbers generated via `ir.sequence`.

## Data Files

- `data/ir_sequence.xml`: `FED-LIC-` sequence for license numbers.
- `security/ir.model.access.csv`: CRUD rights for federation groups.

## Key Behaviours

1. **Name computation** — `name` is automatically composed from `last_name` and
   `first_name` and kept in sync.
2. **License numbering** — Every new license receives an auto-incremented
   `FED-LIC-XXXXX` reference via `ir.sequence`.
3. **Club ↔ Player link** — `club_id` on the player is the *current* affiliation;
   the license records preserve the historical club at time of issue.
