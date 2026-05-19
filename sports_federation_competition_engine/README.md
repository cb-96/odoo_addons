Sports Federation Competition Engine
====================================

Schedule generation wizards for round-robin and knockout formats. Given a
tournament with participants, the engine creates matches, assigns venues, and
sets kickoff times automatically.

Purpose
-------

Automates fixture creation. Instead of manually entering dozens or hundreds of
matches, federation staff run a wizard that generates a complete schedule for
the chosen format, seeding mode, and time intervals.

Dependencies
------------

Depends on sports_federation_tournament for tournaments, stages, groups,
participants, and matches.

Wizards
-------

Round-robin wizard
~~~~~~~~~~~~~~~~~~

Generates a full round-robin schedule where every participant plays every other
participant once, or twice in a double round-robin.

Main fields:

- `tournament_id`
- `stage_id`
- `group_id`
- `participant_ids`
- `use_all_participants`
- `round_type`
- `start_datetime`
- `interval_hours`
- `venue`
- `overwrite`
- computed `summary` preview

Algorithm details: the wizard uses the circle method with deterministic
ordering, ensures no team plays itself, schedules each pairing once or twice,
and inserts bye rounds automatically when participant counts are odd.

Knockout wizard
~~~~~~~~~~~~~~~

Generates a single-elimination bracket.

Main fields:

- `tournament_id`
- `stage_id`
- `participant_source`
- `participant_ids`
- `source_stage_id`
- `seeding`
- `bracket_size`
- `start_datetime`
- `interval_hours`
- `venue`
- `overwrite`
- computed `summary` preview

Algorithm details: the wizard builds seeded single-elimination brackets,
inserts byes when the participant count is not a power of two, and keeps top
seeds separated when power-of-two placement is selected.

Key Behaviours
--------------

- Overwrite protection keeps existing matches unless overwrite is explicitly
	checked.
- Tournament state checks require the tournament to be open or in_progress
	before either wizard generates fixtures.
- Rule-set requirements force an effective rule set on the tournament or linked
	competition before matches are created.
- Preview-first UI shows a computed summary before confirmation, and the
	knockout overwrite warning uses an explicit alert role so Odoo 19 view
	validation stays clean.
- At least 2 teams are required before schedule generation can proceed.
- Tournament templates let `federation.tournament.template.action_apply()`
	scaffold stages, groups, and progression rules with regression coverage.
- Stage progression clears any stale source-group assignment when advancing an
	existing participant into a target stage that has no explicit target group.
- Wizard launch buttons are added to the tournament form view.

Validation and safeguards
-------------------------

- Round-robin generation rejects stages or groups that do not belong to the
	selected tournament.
- Knockout generation validates source-stage ownership before it seeds a
	bracket from prior standings.
- Both wizards require an effective rule set from the tournament or linked
	competition before persisting matches.
- Preview summaries are intended to be reviewed before confirmation, and
	overwrite mode warns that existing matches in the selected scope will be
	replaced.
