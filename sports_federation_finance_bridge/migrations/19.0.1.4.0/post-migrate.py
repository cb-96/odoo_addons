def migrate(cr, version):
    if not version:
        return
    # Preserve old annual team fee policy on existing seasons. New seasons default
    # to player-only fees. Never create retrospective player charges on upgrade.
    cr.execute("UPDATE federation_season SET team_registration_fee_enabled = TRUE")
