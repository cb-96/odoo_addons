def migrate(cr, version):
    """Preserve fixture subsets created by the competition schedule wizard."""
    if not version:
        return
    cr.execute(
        "SELECT to_regclass('federation_schedule'), "
        "to_regclass('federation_schedule_publication')"
    )
    has_schedules, has_publications = cr.fetchone()
    if not has_schedules:
        return
    publication_guard = ""
    if has_publications:
        publication_guard = """
            AND NOT EXISTS (
                SELECT 1
                  FROM federation_schedule_publication AS publication
                 WHERE publication.matchday_id = allocation.matchday_id
                   AND publication.state = 'live'
            )
        """
    cr.execute(
      """
        UPDATE federation_matchday_allocation AS allocation
           SET manual_only = TRUE
         WHERE COALESCE(allocation.stage_id, 0) = 0
           AND COALESCE(allocation.round_number, 0) = 0
           AND EXISTS (
               SELECT 1
                 FROM federation_matchday_allocation_manual_fixture_rel AS relation
                WHERE relation.allocation_id = allocation.id
           )
           AND EXISTS (
               SELECT 1
                 FROM federation_schedule AS schedule
                WHERE schedule.matchday_id = allocation.matchday_id
                  AND schedule.state IN ('draft', 'changes_requested')
           )
              """ + publication_guard
    )