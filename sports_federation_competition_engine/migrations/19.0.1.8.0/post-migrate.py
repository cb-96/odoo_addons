"""Create competition workspace indexes when their real columns are available."""

import logging

_logger = logging.getLogger(__name__)

INDEXES = (
    (
        "sf_match_tournament_stage_state_idx",
        "federation_match",
        ("tournament_id", "stage_id", "state"),
    ),
    ("sf_match_round_slot_idx", "federation_match", ("round_id", "slot_id")),
    (
        "sf_round_tournament_stage_number_idx",
        "federation_tournament_round",
        ("tournament_id", "stage_id", "round_number"),
    ),
    ("sf_slot_round_match_idx", "federation_match_slot", ("round_id", "match_id")),
    (
        "sf_stage_tournament_sequence_idx",
        "federation_tournament_stage",
        ("tournament_id", "sequence"),
    ),
    (
        "sf_progression_tournament_source_target_idx",
        "federation_stage_progression",
        ("tournament_id", "source_stage_id", "target_stage_id"),
    ),
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
