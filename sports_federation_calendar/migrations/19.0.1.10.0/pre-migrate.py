"""Historical timezone evidence must be reviewed, not inferred from an administrator."""
def migrate(cr, version):
    cr.execute('ALTER TABLE federation_matchday ADD COLUMN IF NOT EXISTS event_timezone_reviewed boolean')
    cr.execute('UPDATE federation_matchday SET event_timezone_reviewed = false WHERE event_timezone_reviewed IS NULL')
