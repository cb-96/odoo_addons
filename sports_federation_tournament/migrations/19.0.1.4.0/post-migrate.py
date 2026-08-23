import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Remove test-only standalone matches left by the pre-V2 implementation.

    V2 operational matches are identified by logical_fixture_id. All records
    referencing standalone matches are deleted first by discovering real
    foreign keys, which keeps this migration aligned with installed optional
    modules. Shared master data is never removed.
    """
    cr.execute("SELECT id FROM federation_match WHERE logical_fixture_id IS NULL")
    legacy_ids = [row[0] for row in cr.fetchall()]
    if not legacy_ids:
        _logger.info("V2 cleanup: no standalone legacy matches found")
        return

    cr.execute("""
        SELECT ns.nspname, rel.relname, att.attname
          FROM pg_constraint con
          JOIN pg_class rel ON rel.oid = con.conrelid
          JOIN pg_namespace ns ON ns.oid = rel.relnamespace
          JOIN pg_attribute att
            ON att.attrelid = con.conrelid
           AND att.attnum = ANY(con.conkey)
         WHERE con.contype = 'f'
           AND con.confrelid = 'federation_match'::regclass
           AND rel.relname != 'federation_match'
        """)
    references = cr.fetchall()
    removed = {}
    for schema, table, column in references:
        cr.execute(
            'DELETE FROM "%s"."%s" WHERE "%s" = ANY(%%s)' % (schema, table, column),
            (legacy_ids,),
        )
        if cr.rowcount:
            removed[table] = removed.get(table, 0) + cr.rowcount

    cr.execute(
        "DELETE FROM federation_match WHERE id = ANY(%s)",
        (legacy_ids,),
    )
    _logger.warning(
        "V2 cleanup removed %s standalone legacy matches and dependants %s",
        cr.rowcount,
        removed,
    )
