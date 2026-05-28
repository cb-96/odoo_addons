Sports Federation Standings
===========================

Computes and stores league-style standings tables for tournament stages and
groups. Aggregates match results into a ranked table with points, wins,
losses, goal differences, and configurable tie-break ordering.

Purpose
-------

Provides a snapshot of competition standings that can be published, audited,
and used by downstream modules such as the public site, reporting, and
qualification logic. Standings are linked to rule sets to ensure consistent
scoring and tie resolution.

Dependencies
------------

- ``sports_federation_tournament``: Tournaments, stages, groups, and matches.
- ``sports_federation_rules``: Rule sets for scoring and tie-breaks.
- ``mail``: Chatter integration.

Models
------

``federation.standing``
~~~~~~~~~~~~~~~~~~~~~~~

A standings table for a specific scope such as a tournament, stage, or group.

Fields:

- ``name`` (Char): Standings title.
- ``tournament_id`` (Many2one): Tournament.
- ``stage_id`` (Many2one): Optional stage scope.
- ``group_id`` (Many2one): Optional group scope.
- ``competition_id`` (Many2one): Competition context.
- ``rule_set_id`` (Many2one): Scoring and tie-break rules.
- ``state`` (Selection): ``draft``, ``computed``, or ``frozen``.
- ``line_ids`` (One2many): Ranked team entries.
- ``line_count`` (Integer): Stat-button counter.
- ``computed_on`` (Datetime): When the table was last computed.
- ``notes`` (Text): Additional notes.

State machine:

- ``draft -> computed -> frozen``.

``federation.standing.line``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

One row per participant in the standings table.

Fields:

- ``standing_id`` (Many2one): Parent standings.
- ``participant_id`` (Many2one): The team.
- ``rank`` (Integer): Position in the standings table (1 = first).
- ``played`` (Integer): Total matches played.
- ``won`` / ``drawn`` / ``lost`` (Integer): Results breakdown.
- ``score_for`` / ``score_against`` (Integer): Goals/points scored and conceded.
- ``score_diff`` (Integer, computed): ``score_for - score_against``.
- ``points`` (Integer): Total points per rule set.
- ``note`` (Char): Short free-text remark for this line.
- ``tiebreak_notes`` (Text, readonly): Auto-generated explanation of the tie-break criterion used to order this participant.

Key Behaviours
--------------

- **Rule-set driven scoring**: points are calculated using the attached rule
   set and its configured win, draw, and loss values.
- **Tie-break resolution**: when teams have equal points, tie-break rules from
   the rule set are applied in sequence order.
- **Snapshot model**: each standings record is a point-in-time computation,
   allowing historical comparison.
- **Official-result filtering**: when ``sports_federation_result_control`` is
   installed, only matches with ``include_in_official_standings = True`` are
   counted.
- **Freeze behavior**: frozen standings reject recomputation unless
   ``force_recompute`` is provided in context.
- **Auto-advance hook**: freezing a standing can trigger pending
   ``federation.stage.progression`` rules with ``auto_advance = True``.
- **Publication is separate**: public visibility is handled by
   ``sports_federation_public_site`` through ``website_published``, not by a
   dedicated published standings state.
