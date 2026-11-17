def migrate(cr, version):
    if not version:
        return
    # Link only an unambiguous approved entry in a current finalized snapshot.
    # No new participants, approvals, snapshots or events are fabricated.
    cr.execute("""
        WITH candidates AS (
            SELECT participant.id AS participant_id, entry.id AS entry_id,
                   registration_window.participant_set_id AS set_id,
                   count(*) OVER (PARTITION BY participant.id) AS matches
            FROM federation_tournament_participant participant
            JOIN federation_registration_window registration_window
              ON registration_window.division_id = participant.tournament_id AND registration_window.state = 'finalized'
            JOIN federation_participant_set snapshot
              ON snapshot.id = registration_window.participant_set_id AND snapshot.state = 'finalized'
            JOIN federation_competition_entry entry
              ON entry.window_id = registration_window.id AND entry.team_id = participant.team_id AND entry.state = 'approved'
            JOIN federation_participant_set_line line
              ON line.participant_set_id = snapshot.id AND line.team_id = participant.team_id
            WHERE participant.state = 'confirmed' AND participant.source_entry_id IS NULL
        )
        UPDATE federation_tournament_participant participant
        SET source_entry_id = candidates.entry_id, source_participant_set_id = candidates.set_id
        FROM candidates WHERE participant.id = candidates.participant_id AND candidates.matches = 1
    """)
