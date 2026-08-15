"""Backfill explicit regulation resolution for existing bracket matches."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE federation_match
           SET resolution_type = 'regulation'
         WHERE resolution_type IS NULL
           AND (
                bracket_type IS NOT NULL
                OR source_match_1_id IS NOT NULL
                OR source_match_2_id IS NOT NULL
           )
        """
    )
