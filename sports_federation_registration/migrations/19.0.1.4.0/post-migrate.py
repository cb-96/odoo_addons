"""Give finalised divisions their tournament participants.

Finalising registration now creates a confirmed ``federation.tournament.participant``
for every team of the finalised list. Divisions finalised before this version
only have the participant set (and participants for ranked stages), so
knockout divisions had no participants at all. Each set is handled in its own
savepoint and teams that fail the division's eligibility check are skipped;
both are logged for review.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    sets = env["federation.participant.set"].search([("state", "=", "finalized")])
    for participant_set in sets:
        window = env["federation.registration.window"].search(
            [("participant_set_id", "=", participant_set.id)], limit=1
        )
        if not window:
            _logger.info(
                "Participant set %s has no registration window; skipped.",
                participant_set.id,
            )
            continue
        try:
            with cr.savepoint():
                window._sync_tournament_participants(
                    participant_set, skip_ineligible=True
                )
        except Exception:  # noqa: BLE001 - upgrade must continue; logged for review
            _logger.exception(
                "Participants not synchronised for participant set %s",
                participant_set.id,
            )
