def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        INSERT INTO federation_club_season_registration
            (club_id, season_id, state, company_id, create_uid, write_uid, create_date, write_date)
        SELECT club_id, season_id,
               CASE WHEN bool_or(state = 'active') THEN 'confirmed' ELSE 'draft' END,
               (SELECT res_id FROM ir_model_data WHERE module = 'base' AND name = 'main_company'),
               1, 1, now(), now()
        FROM federation_player_license
        GROUP BY club_id, season_id
        ON CONFLICT (club_id, season_id) DO NOTHING
    """)
    cr.execute("""
        UPDATE federation_player_license license
        SET club_registration_id = registration.id
        FROM federation_club_season_registration registration
        WHERE license.club_registration_id IS NULL
          AND license.club_id = registration.club_id
          AND license.season_id = registration.season_id
    """)
    cr.execute("""
        UPDATE federation_club_season_registration registration
        SET name = club.name || ' / ' || season.name
        FROM federation_club club, federation_season season
        WHERE registration.club_id = club.id AND registration.season_id = season.id
    """)
