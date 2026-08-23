def migrate(cr, version):
    # V1 registration tasks are projections, not business records. Close them
    # so the next sync can create V2 competition-entry tasks without ambiguity.
    cr.execute("""
        UPDATE federation_operation_task
           SET state = 'done', completed_on = NOW()
         WHERE source_model = 'federation.tournament.registration'
           AND state != 'done'
        """)
