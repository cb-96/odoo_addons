"""Pre-migration: add mail.thread column to base federation models.

The UX pass added ``mail.thread`` (and ``mail.activity.mixin``) to
federation.club, federation.season, federation.team, and
federation.season.registration.  Odoo's ORM will emit ``ALTER TABLE … ADD
COLUMN`` automatically, but running the column addition explicitly here
guarantees that:

1. The upgrade cannot silently skip the column if the module had previously
   been partially upgraded.
2. Any future migration that relies on the column being present can safely
   depend on this version.
"""

import logging

_logger = logging.getLogger(__name__)

_MAIL_COLUMN = "message_main_attachment_id"

_TABLES = [
    "federation_club",
    "federation_season",
    "federation_team",
    "federation_season_registration",
]


def migrate(cr, version):
    """Ensure the mail.thread attachment column exists on all affected tables."""
    for table in _TABLES:
        cr.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s
              AND column_name = %s
            """,
            [table, _MAIL_COLUMN],
        )
        if not cr.fetchone():
            cr.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS"
                f" {_MAIL_COLUMN} INTEGER"
            )
            _logger.info("pre-migrate: added column %s to %s", _MAIL_COLUMN, table)
