from odoo import SUPERUSER_ID, api
from odoo.addons.sports_federation_base.models.failure_feedback import (
    build_failure_feedback,
)


def migrate(cr, version):
    """Backfill notification failure categories and operator-safe messages."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    logs = (
        env["federation.notification.log"]
        .sudo()
        .search(
            [
                ("state", "=", "failed"),
                ("operator_message", "=", False),
                ("message", "!=", False),
            ]
        )
    )
    for log in logs:
        failure_category, operator_message = build_failure_feedback(detail=log.message)
        log.write(
            {
                "failure_category": failure_category,
                "operator_message": operator_message,
                "message": False,
            }
        )
