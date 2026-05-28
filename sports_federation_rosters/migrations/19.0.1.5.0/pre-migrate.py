"""
Migration 19.0.1.5.0 — drop the ineffective name-based roster uniqueness constraint

Removes the constraint:
  UNIQUE(team_id, season_id, competition_id, name)

This constraint was ineffective because roster names are auto-generated.  Two
rosters for the same (team, season, competition) scope could coexist as long as
their auto-generated names differed, bypassing the intended one-active-roster-per-scope
business rule.

The active-scope uniqueness is already correctly enforced by the partial unique
indexes added in migration 19.0.1.4.0:
  - federation_team_roster_unique_active_no_comp
    UNIQUE (team_id, season_id) WHERE status = 'active' AND competition_id IS NULL
  - federation_team_roster_unique_active_with_comp
    UNIQUE (team_id, season_id, competition_id) WHERE status = 'active'

Multiple rosters per scope in non-active statuses (draft, closed) are valid and
support the "close old roster, create new one" workflow.

This migration simply drops the name-based constraint so that:
  - auto-generated names no longer need a collision-avoidance suffix loop, and
  - two draft/closed rosters for the same scope are not blocked by name collision.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Drop the ineffective name-based unique constraint (added before 19.0.1.5.0)
    cr.execute("""
        ALTER TABLE federation_team_roster
        DROP CONSTRAINT IF EXISTS
            federation_team_roster_unique_team_season_competition_name;
    """)
    _logger.info(
        "19.0.1.5.0 migration: dropped name-based roster uniqueness constraint."
    )

    # Also drop the scope-level unique index that may have been created by an
    # earlier (incorrect) iteration of this migration.  Active-roster uniqueness
    # is correctly handled by the partial indexes from 19.0.1.4.0, so a
    # scope-level index blocking draft/closed duplicates must be removed.
    cr.execute("DROP INDEX IF EXISTS federation_team_roster_unique_scope;")
    _logger.info("19.0.1.5.0 migration: dropped scope-level unique index (if present).")
