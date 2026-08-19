"""Create club and manager queue indexes when their real columns are available."""

import logging

_logger = logging.getLogger(__name__)

INDEXES = (
    (
        "sf_operation_task_queue_idx",
        "federation_operation_task",
        ("audience", "state", "blocking", "priority", "deadline"),
    ),
    (
        "sf_operation_task_owner_idx",
        "federation_operation_task",
        ("assigned_user_id", "state", "deadline"),
    ),
    (
        "sf_operation_task_club_idx",
        "federation_operation_task",
        ("responsible_club_id", "state", "task_type"),
    ),
    (
        "sf_tournament_registration_review_idx",
        "federation_tournament_registration",
        ("tournament_id", "state", "club_id"),
    ),
    ("sf_roster_team_status_idx", "federation_team_roster", ("team_id", "status")),
)


def _table_has_columns(cr, table, columns):
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = %s
           AND column_name = ANY(%s)
        """,
        (table, list(columns)),
    )
    existing = {row[0] for row in cr.fetchall()}
    return existing == set(columns)


def migrate(cr, version):
    for name, table, columns in INDEXES:
        if not _table_has_columns(cr, table, columns):
            _logger.warning(
                "Skipping index %s: %s is missing required columns %s",
                name,
                table,
                columns,
            )
            continue
        quoted_columns = ", ".join('"%s"' % column for column in columns)
        cr.execute(
            'CREATE INDEX IF NOT EXISTS "%s" ON "%s" (%s)'
            % (name, table, quoted_columns)
        )
