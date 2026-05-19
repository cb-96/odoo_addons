Sports Federation Rosters
=========================

Season and competition-bound team rosters plus match-day squad sheets. Controls
which players are eligible and available for each match, enforces squad-size
limits from the applicable rule set, and surfaces operator-readable readiness
feedback before rosters, participants, or match sheets move forward.

Purpose
-------

Provides a formal roster, which is the pool of players a team may select from
for a season or competition, and match sheets, which are the specific squad and
starting lineup for an individual match. The module links to rule sets for
squad-size validation and to the shared eligibility service for license,
registration, and suspension checks.

Dependencies
------------

- ``sports_federation_base``: Clubs, teams, and seasons.
- ``sports_federation_people``: Players.
- ``sports_federation_tournament``: Tournaments and matches.
- ``sports_federation_rules``: Squad-size limits and player eligibility checks.
- ``mail``: Chatter integration.

Models
------

``federation.team.roster``
~~~~~~~~~~~~~~~~~~~~~~~~~~

A pool of eligible players for a team within a season or competition scope.

Fields:

- ``name`` (Char): Generated roster label.
- ``team_id`` (Many2one): Team.
- ``season_id`` (Many2one): Season scope.
- ``season_registration_id`` (Many2one): Linked registration.
- ``competition_id`` (Many2one): Optional competition scope.
- ``rule_set_id`` (Many2one): Squad-size rules.
- ``status`` (Selection): ``draft``, ``active``, or ``closed``.
- ``valid_from`` / ``valid_to`` (Date): Validity window.
- ``line_ids`` (One2many): Rostered players.
- ``line_count`` (Integer): Player count.
- ``club_id`` (Many2one, computed): Derived from the team.
- ``min_players_required`` / ``max_players_allowed`` (Integer): Limits pulled
   from the rule set.
- ``ready_for_activation`` (Boolean, computed): Whether activation checks pass.
- ``readiness_feedback`` (Text, computed): Aggregated activation blockers.
- ``match_sheet_count`` (Integer, computed): Linked match sheets using this
   roster.
- ``match_day_locked`` (Boolean, computed): Whether live match sheets now lock
   roster scope changes.
- ``match_day_lock_feedback`` (Text, computed): Why the roster scope is locked.
- ``audit_event_ids`` (One2many): Participation audit events for this roster.

``federation.team.roster.line``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A single player entry on a roster.

Fields:

- ``roster_id`` (Many2one): Parent roster.
- ``player_id`` (Many2one): The player.
- ``status`` (Selection): ``active``, ``inactive``, ``suspended``, or
   ``removed``.
- ``date_from`` / ``date_to`` (Date): Availability window.
- ``jersey_number`` (Char): Squad number.
- ``is_captain`` / ``is_vice_captain`` (Boolean): Leadership flags.
- ``license_id`` (Many2one): Explicit season license to validate.
- ``eligible`` (Boolean, computed): Current eligibility status.
- ``eligibility_feedback`` (Text, computed): Human-readable failure reasons.
- ``notes`` (Text): Remarks.

Key behaviour:

- Once a submitted, approved, or locked match sheet references a roster line,
   that referenced line cannot be structurally changed or removed.

``federation.match.sheet``
~~~~~~~~~~~~~~~~~~~~~~~~~~

The squad list submitted for a specific match.

Fields:

- ``name`` (Char): Sheet title.
- ``match_id`` (Many2one): The match.
- ``team_id`` (Many2one): Which team the sheet belongs to.
- ``roster_id`` (Many2one): Source roster.
- ``side`` (Selection): ``home`` or ``away``.
- ``state`` (Selection): ``draft``, ``submitted``, ``approved``, or ``locked``.
- ``line_ids`` (One2many): Player entries.
- ``line_count`` (Integer): Squad size.
- ``ready_for_submission`` (Boolean, computed): Whether submission checks pass.
- ``readiness_feedback`` (Text, computed): Aggregated submission blockers.
- ``substitution_count`` (Integer, computed): Number of recorded substitution
   entries.
- ``locked_on`` / ``locked_by_id`` (Datetime / Many2one): Final lock metadata.
- ``audit_event_ids`` (One2many): Participation audit events for this sheet.
- ``coach_name`` / ``manager_name`` (Char): Team staff.
- ``notes`` (Text): Remarks.

State machine:

- ``draft -> submitted -> approved -> locked``.
- Submitted sheets may return to draft for operator corrections before
   approval.

``federation.match.sheet.line``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A player on a match sheet.

Fields:

- ``match_sheet_id`` (Many2one): Parent sheet.
- ``player_id`` (Many2one): The player.
- ``roster_line_id`` (Many2one): Source roster line.
- ``is_starter`` (Boolean): In the starting lineup.
- ``is_substitute`` (Boolean): Bench selection.
- ``is_captain`` (Boolean): Match captain.
- ``jersey_number`` (Char): Shirt number.
- ``entered_minute`` / ``left_minute`` (Integer): Substitution timeline
   tracking.
- ``eligible`` (Boolean, computed): Current eligibility status.
- ``eligibility_feedback`` (Text, computed): Human-readable failure reasons.
- ``notes`` (Text): Remarks.

``federation.participation.audit``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Immutable operational log for roster and match-sheet activity.

Fields:

- ``event_type`` (Selection): Created, updated, submitted, approved, locked,
   and substitution events.
- ``team_id`` (Many2one): Team owning the event.
- ``roster_id`` (Many2one): Related season roster when applicable.
- ``match_sheet_id`` (Many2one): Related match sheet when applicable.
- ``match_id`` (Many2one): Related match when applicable.
- ``player_id`` (Many2one): Player affected by the event.
- ``description`` (Text): Human-readable audit detail.
- ``author_id`` / ``event_on`` (Many2one / Datetime): Attribution and
   timestamp.

``federation.tournament.participant`` Extension
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module extends tournament participants with team-linked roster readiness
checks. Tournament registration auto-provisions a team roster for the relevant
season and competition scope. Participants can still be confirmed and assigned
without a ready roster before the roster deadline, but once that deadline is
reached both participant confirmation and scheduled matches require an active
ready roster: one week before the first scheduled match, or one week before the
tournament start if no match has been scheduled yet.

Fields:

- ``ready_for_confirmation`` (Boolean, computed): Whether the linked team
   currently satisfies the roster deadline rule.
- ``roster_deadline_date`` (Date, computed): Deadline for having an active
   ready roster.
- ``readiness_roster_id`` (Many2one, computed): Preferred team roster used for
   readiness checks.
- ``confirmation_feedback`` (Text, computed): Warning or blocking message about
   the roster deadline.

Key Behaviours
--------------

- **Roster scoping**: rosters are tied to a season and optionally a
   competition, preventing cross-competition player sharing.
- **Eligibility-aware activation**: roster activation is blocked until active
   lines satisfy date windows, squad-size bounds, and shared eligibility rules.
- **Readable operator feedback**: roster lines and match-sheet lines expose
   ``eligibility_feedback``, while rosters and match sheets aggregate blockers
   into readiness summaries.
- **Match sheet from roster**: match sheets validate against explicit roster
   lines so team, date-window, and license mismatches are caught early.
- **Match-day locking**: submitted and approved sheet activity locks roster
   scope changes and the referenced roster lines so historical lineups remain
   defensible.
- **Substitution governance**: approved sheets can record ``entered_minute``
   and ``left_minute`` values while still blocking lineup changes after
   approval.
- **Participation audit trail**: roster lifecycle changes, lineup changes,
   submissions, submitted-sheet resets, approvals, locks, and substitutions are
   captured in ``federation.participation.audit``.
- **Participant roster readiness**: tournament registration creates or reuses
   the relevant team roster automatically so roster maintenance stays attached
   to the participating team instead of requiring a separately named setup step.
- **Operational roster deadline**: tournament participants can still be
   confirmed and grouped without a ready roster before the deadline, but once
   the one-week deadline is reached operators cannot confirm participants or
   schedule matches until an active ready roster exists.
- **Team-linked roster checks**: team roster lookup and tournament deadline
   assessment are owned by the team model so roster compliance follows the team
   rather than being treated as a separate participant-only concern.
- **State locking**: approved match sheets can be locked once match-day
   operations are complete.
