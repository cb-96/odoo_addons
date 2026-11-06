"""Give participants of running seasons their roster.

A roster is created when a team becomes a tournament participant, and is now
linked to the team's confirmed season registration. Teams that took part in a
division without participant records (finalised registration lists produced
only a participant set) never got one, and rosters that exist were not linked
to the registration, so the portal could not find them. Each participant is
handled in its own savepoint so one problem cannot block the upgrade; skipped
participants are logged. Seasons that are closed, cancelled, archived or already
over are left alone.
"""

import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    today = fields.Date.context_today(env["federation.season"])
    participants = env["federation.tournament.participant"].search(
        [
            ("state", "!=", "withdrawn"),
            ("tournament_id.season_id.state", "in", ("draft", "open")),
            "|",
            ("tournament_id.season_id.date_end", "=", False),
            ("tournament_id.season_id.date_end", ">=", today),
        ]
    )
    prepared = 0
    for participant in participants:
        try:
            with cr.savepoint():
                participant._ensure_linked_roster()
                prepared += 1
        except Exception:  # noqa: BLE001 - upgrade must continue; logged for review
            _logger.exception("No roster prepared for participant %s", participant.id)
    _logger.info(
        "Rosters checked for %s of %s participants.", prepared, len(participants)
    )
