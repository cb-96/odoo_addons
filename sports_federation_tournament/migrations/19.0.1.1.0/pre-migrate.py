"""
Migration 19.0.1.1.0 (pre) — normalize persisted match scheduling fields.

This migration prepares historical match rows for the new index pack by
backfilling persisted schedule fields that may be null in older databases.
"""


def migrate(cr, version):
    # Ensure persisted date snapshots exist for older rows that predate
    # scheduled_date storage and round/date normalization.
    cr.execute("""
        UPDATE federation_match
           SET scheduled_date = DATE(date_scheduled)
         WHERE date_scheduled IS NOT NULL
           AND scheduled_date IS NULL;
        """)

    # Keep round_number consistent with the owning round sequence when
    # historical rows missed that denormalized value.
    cr.execute("""
        UPDATE federation_match match
           SET round_number = round.sequence
          FROM federation_tournament_round round
         WHERE match.round_id = round.id
           AND match.round_number IS NULL;
        """)
