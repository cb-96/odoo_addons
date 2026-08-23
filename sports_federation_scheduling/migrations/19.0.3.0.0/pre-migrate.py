def migrate(cr, version):
    cr.execute(
        "ALTER TABLE federation_schedule DROP CONSTRAINT IF EXISTS federation_schedule_unique_matchday"
    )
    cr.execute(
        "ALTER TABLE federation_schedule DROP CONSTRAINT IF EXISTS federation_schedule__unique_matchday"
    )
