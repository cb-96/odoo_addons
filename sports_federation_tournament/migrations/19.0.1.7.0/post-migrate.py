def migrate(cr, version):
    if not version:
        return
    # Correct redundant identity pointers only. Do not reinterpret dates, results,
    # legacy standalone tournaments, participants or fixture history.
    cr.execute("""
        UPDATE federation_tournament division
        SET competition_id = edition.competition_id, season_id = edition.season_id
        FROM federation_competition_edition edition
        WHERE division.edition_id = edition.id
          AND (division.competition_id IS DISTINCT FROM edition.competition_id
               OR division.season_id IS DISTINCT FROM edition.season_id)
    """)
