"""Bring already published matches in line with their published slot.

Publishing now schedules the match and copies the slot's venue and playing area
to it. Matches published before this version stayed ``draft`` without a venue,
so venue-dependent features (finance, exports, the public schedule location)
never saw them. This is a set-based update of data that publication already
fixed: it does not re-run match constraints and does not create finance events
retroactively. Matches that already have a playing area keep it.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE federation_match m
           SET playing_area_id = a.id,
               venue_id = a.venue_id
          FROM federation_schedule_slot s
          JOIN federation_playing_area a ON a.id = s.court_id
         WHERE s.id = COALESCE(m.operational_slot_id, m.published_slot_id)
           AND m.schedule_publication_id IS NOT NULL
           AND m.playing_area_id IS NULL
        """
    )
    cr.execute(
        """
        UPDATE federation_match
           SET state = 'scheduled'
         WHERE state = 'draft'
           AND schedule_publication_id IS NOT NULL
           AND published_slot_id IS NOT NULL
        """
    )
