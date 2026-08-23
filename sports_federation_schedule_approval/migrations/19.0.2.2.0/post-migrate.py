def migrate(cr, version):
    cr.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
            federation_schedule_publication_one_live_matchday
        ON federation_schedule_publication (matchday_id)
        WHERE state = 'live' AND matchday_id IS NOT NULL
        """)
