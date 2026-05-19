from odoo import SUPERUSER_ID, api
from odoo.addons.sports_federation_base.models.failure_feedback import (
    build_failure_feedback,
)


def migrate(cr, version):
    """Backfill typed report-schedule failure feedback for existing failed rows."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    schedules = (
        env["federation.report.schedule"]
        .sudo()
        .search(
            [
                ("last_run_status", "=", "failed"),
                ("last_operator_message", "=", False),
                ("last_error_message", "!=", False),
            ]
        )
    )
    for schedule in schedules:
        failure_category, operator_message = build_failure_feedback(
            detail=schedule.last_error_message,
        )
        schedule.write(
            {
                "last_failure_category": failure_category,
                "last_operator_message": operator_message,
                "last_error_message": False,
            }
        )
