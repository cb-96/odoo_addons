"""
Migration 19.0.1.1.0 (post) — add federation.match operational indexes.

These indexes harden read performance for portal operations, standings
reconciliation, and tournament workspace filtering at larger data volumes.
"""


def migrate(cr, version):
    cr.execute("""
        DROP INDEX IF EXISTS federation_match_tournament_state_idx;
        DROP INDEX IF EXISTS federation_match_stage_state_idx;
        DROP INDEX IF EXISTS federation_match_group_state_idx;
        DROP INDEX IF EXISTS federation_match_scheduled_date_state_idx;
        DROP INDEX IF EXISTS federation_match_date_scheduled_state_idx;
        """)

    cr.execute("""
        CREATE INDEX federation_match_tournament_state_idx
            ON federation_match (tournament_id, state);
        """)
    cr.execute("""
        CREATE INDEX federation_match_stage_state_idx
            ON federation_match (stage_id, state);
        """)
    cr.execute("""
        CREATE INDEX federation_match_group_state_idx
            ON federation_match (group_id, state);
        """)
    cr.execute("""
        CREATE INDEX federation_match_scheduled_date_state_idx
            ON federation_match (scheduled_date, state);
        """)
    cr.execute("""
        CREATE INDEX federation_match_date_scheduled_state_idx
            ON federation_match (date_scheduled, state);
        """)
