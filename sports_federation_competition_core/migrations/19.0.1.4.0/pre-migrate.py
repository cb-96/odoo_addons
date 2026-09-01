def migrate(cr, version):
    cr.execute("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'federation_competition_edition'
           AND column_name = 'engine_state'
        """)
    if not cr.fetchone():
        return

    cr.execute("""
        UPDATE federation_competition_edition edition
           SET state = CASE edition.engine_state
               WHEN 'active' THEN CASE
                   WHEN EXISTS (
                       SELECT 1
                         FROM federation_matchday matchday
                        WHERE matchday.edition_id = edition.id
                          AND matchday.state IN ('open', 'closed')
                   ) THEN 'in_progress'
                   ELSE 'open'
               END
               WHEN 'finished' THEN 'closed'
               WHEN 'archived' THEN 'closed'
               WHEN 'cancelled' THEN 'cancelled'
               ELSE edition.state
           END
         WHERE edition.engine_state IS NOT NULL
        """)
    cr.execute("ALTER TABLE federation_competition_edition DROP COLUMN engine_state")
