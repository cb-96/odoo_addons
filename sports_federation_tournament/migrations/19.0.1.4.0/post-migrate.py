import logging

from psycopg2 import sql

_logger = logging.getLogger(__name__)


def _column_exists(cr, table, column):
    cr.execute(
        """SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s AND column_name = %s""",
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    """Remove test-only standalone matches after verifying historical schema."""
    if not _column_exists(cr, "federation_match", "logical_fixture_id"):
        _logger.warning(
            "Legacy match cleanup skipped: logical_fixture_id is absent"
        )
        return
    cr.execute(
        "SELECT id FROM federation_match WHERE logical_fixture_id IS NULL ORDER BY id"
    )
    legacy_ids = [row[0] for row in cr.fetchall()]
    if not legacy_ids:
        _logger.info("Legacy match cleanup: no standalone matches found")
        return
    _logger.warning("Legacy match cleanup found %s matches", len(legacy_ids))
    cr.execute("""
        SELECT ns.nspname, rel.relname, att.attname
          FROM pg_constraint con
          JOIN pg_class rel ON rel.oid = con.conrelid
          JOIN pg_namespace ns ON ns.oid = rel.relnamespace
          JOIN pg_attribute att ON att.attrelid = con.conrelid
                               AND att.attnum = ANY(con.conkey)
         WHERE con.contype = 'f'
           AND con.confrelid = 'federation_match'::regclass
           AND rel.relname != 'federation_match'
    """)
    removed = {}
    for schema, table, column in cr.fetchall():
        statement = sql.SQL("DELETE FROM {}.{} WHERE {} = ANY(%s)").format(
            sql.Identifier(schema), sql.Identifier(table), sql.Identifier(column)
        )
        cr.execute(statement, (legacy_ids,))
        if cr.rowcount:
            removed[table] = removed.get(table, 0) + cr.rowcount
    cr.execute("DELETE FROM federation_match WHERE id = ANY(%s)", (legacy_ids,))
    if cr.rowcount != len(legacy_ids):
        raise RuntimeError(
            "Legacy match cleanup count mismatch: "
            f"expected {len(legacy_ids)}, removed {cr.rowcount}"
        )
    _logger.warning(
        "Legacy match cleanup removed %s matches and dependants %s",
        len(legacy_ids), removed,
    )
