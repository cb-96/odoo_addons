"""Give existing ranked stages their live league table.

Before this version, competitions built in the Competition Hub had no
``federation.standing`` and therefore no table on the website. Each stage is
handled in its own savepoint so one problem cannot block the upgrade; skipped
stages are logged for review.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    engine = env["federation.stage.graph.engine"]
    stages = env["federation.structure.stage"].search(
        [
            ("format_type", "in", ("single_round_robin", "double_round_robin")),
            ("stage_participant_ids", "!=", False),
        ]
    )
    for stage in stages:
        try:
            with cr.savepoint():
                engine._ensure_linked_standing(stage)
        except Exception:  # noqa: BLE001 - upgrade must continue; logged for review
            _logger.exception("No league table created for stage %s", stage.id)
