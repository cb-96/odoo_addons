def migrate(cr, version):
    """Backfill remembered workspace presets for existing competition editions."""
    cr.execute(
        """
        UPDATE federation_competition_edition edition
           SET setup_preset = CASE competition.competition_type
               WHEN 'cup' THEN 'cup'
               ELSE 'league'
           END
          FROM federation_competition competition
         WHERE competition.id = edition.competition_id
           AND (edition.setup_preset IS NULL OR edition.setup_preset = '')
        """
    )
    cr.execute(
        """
        UPDATE federation_competition_edition
           SET setup_default_format_type = CASE setup_preset
               WHEN 'cup' THEN 'knockout'
               ELSE 'single_round_robin'
           END
         WHERE setup_default_format_type IS NULL
            OR setup_default_format_type = ''
        """
    )
    cr.execute(
        """
        UPDATE federation_competition_edition
           SET setup_default_start_hour = COALESCE(setup_default_start_hour, 9.0),
               setup_default_end_hour = COALESCE(setup_default_end_hour, 18.0),
               setup_default_slot_duration_minutes =
                   COALESCE(setup_default_slot_duration_minutes, 40)
        """
    )
