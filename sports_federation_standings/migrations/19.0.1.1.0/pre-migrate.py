"""Pre-migration: add mail.thread column to federation.standing.

The UX pass added ``mail.thread`` to ``federation.standing``.  This script
makes the schema change explicit for production upgrade tracking.
"""

import logging

_logger = logging.getLogger(__name__)

_MAIL_COLUMN = "message_main_attachment_id"
_TABLE = "federation_standing"


def migrate(cr, version):
    """Ensure the mail.thread attachment column exists on federation_standing."""
    cr.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name = %s
        """,
        [_TABLE, _MAIL_COLUMN],
    )
    if not cr.fetchone():
        cr.execute(
            f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS {_MAIL_COLUMN} INTEGER"
        )
        _logger.info("pre-migrate: added column %s to %s", _MAIL_COLUMN, _TABLE)
