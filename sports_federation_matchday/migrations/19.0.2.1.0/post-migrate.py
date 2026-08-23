def migrate(cr, version):
    cr.execute("""
        UPDATE federation_match
           SET operational_slot_id = published_slot_id,
               operational_status = 'as_published'
         WHERE schedule_publication_id IS NOT NULL
           AND published_slot_id IS NOT NULL
           AND operational_slot_id IS NULL
        """)
