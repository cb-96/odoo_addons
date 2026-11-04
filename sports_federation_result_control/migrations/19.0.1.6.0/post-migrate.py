"""Finish matches whose result was approved before approval completed matches.

Only the match state changes. Scores, result audit and publication data are
untouched, so the update is safe to repeat.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE federation_match
           SET state = 'done'
         WHERE result_state = 'approved'
           AND state NOT IN ('done', 'cancelled')
        """
    )
