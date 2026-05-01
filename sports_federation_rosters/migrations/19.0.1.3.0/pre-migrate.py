"""
Migration 19.0.1.3.0 — participation_audit FK fixes

Two FK constraint changes on federation_participation_audit:

1. match_sheet_id: CASCADE → SET NULL
   The old CASCADE caused a ForeignKeyViolation when federation_match rows were
   deleted. Postgres cascade-deletes match_sheet rows first, then tries to
   SET NULL on audit.match_id — but that UPDATE re-validates match_sheet_id_fkey
   which now points to already-deleted sheets → FK violation.
   SET NULL preserves audit history when a sheet is deleted.

2. match_id: SET NULL → CASCADE
   With CASCADE, audit rows are deleted immediately when their match is deleted.
   This eliminates the ordering problem entirely: audit rows are gone before
   the match_sheet cascade runs, so the match_sheet_id FK is never re-validated
   against deleted sheets.
"""


def migrate(cr, version):
    # 1. match_sheet_id: CASCADE → SET NULL
    cr.execute("""
        ALTER TABLE federation_participation_audit
        DROP CONSTRAINT IF EXISTS federation_participation_audit_match_sheet_id_fkey;
    """)
    cr.execute("""
        ALTER TABLE federation_participation_audit
        ADD CONSTRAINT federation_participation_audit_match_sheet_id_fkey
            FOREIGN KEY (match_sheet_id)
            REFERENCES federation_match_sheet(id)
            ON DELETE SET NULL;
    """)

    # 2. match_id: SET NULL → CASCADE
    cr.execute("""
        ALTER TABLE federation_participation_audit
        DROP CONSTRAINT IF EXISTS federation_participation_audit_match_id_fkey;
    """)
    cr.execute("""
        ALTER TABLE federation_participation_audit
        ADD CONSTRAINT federation_participation_audit_match_id_fkey
            FOREIGN KEY (match_id)
            REFERENCES federation_match(id)
            ON DELETE CASCADE;
    """)
