"""Do not infer a historical event timezone from the upgrading user's profile."""
def migrate(cr, version):
    cr.execute("ALTER TABLE federation_matchday ADD COLUMN IF NOT EXISTS event_timezone varchar")
    cr.execute("UPDATE federation_matchday SET event_timezone = 'UTC' WHERE event_timezone IS NULL")
