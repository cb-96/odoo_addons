def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'federation_competition_edition'
           AND column_name = 'engine_state'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE federation_competition_edition
           SET state = CASE engine_state
               WHEN 'active' THEN CASE WHEN state = 'draft' THEN 'open' ELSE state END
               WHEN 'finished' THEN 'closed'
               WHEN 'archived' THEN 'closed'
               WHEN 'cancelled' THEN 'cancelled'
               ELSE state END
         WHERE engine_state IS NOT NULL
    """)
    cr.execute("ALTER TABLE federation_competition_edition DROP COLUMN engine_state")
