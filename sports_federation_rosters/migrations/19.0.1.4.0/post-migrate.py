"""
Migration 19.0.1.4.0 — partial unique index: one active roster per team/season/competition

Enforces at the DB level that a team cannot have more than one active roster for
the same (team_id, season_id, competition_id) scope.  The Python-layer constraint
added to the model is authoritative during normal ORM operations; this index
provides a hard guarantee against concurrent writes or direct SQL access.

Two variants of the index are required because competition_id is nullable:
  - competition_id IS NULL  →  season-scoped rosters with no specific competition
  - competition_id IS NOT NULL  →  competition-scoped rosters
"""


def migrate(cr, version):
    # Drop pre-existing indexes in case this migration is re-run.
    cr.execute("""
        DROP INDEX IF EXISTS federation_team_roster_unique_active_no_comp;
        DROP INDEX IF EXISTS federation_team_roster_unique_active_with_comp;
        """)

    # Partial unique index: active rosters without a competition scope.
    cr.execute("""
        CREATE UNIQUE INDEX federation_team_roster_unique_active_no_comp
            ON federation_team_roster (team_id, season_id)
            WHERE status = 'active' AND competition_id IS NULL;
        """)

    # Partial unique index: active rosters with a specific competition scope.
    cr.execute("""
        CREATE UNIQUE INDEX federation_team_roster_unique_active_with_comp
            ON federation_team_roster (team_id, season_id, competition_id)
            WHERE status = 'active' AND competition_id IS NOT NULL;
        """)
