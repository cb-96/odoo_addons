from odoo import SUPERUSER_ID, api
from odoo.addons.sports_federation_base.models.failure_feedback import (
    build_failure_feedback,
)
from odoo.addons.sports_federation_import_tools.workflow_states import (
    IMPORT_JOB_ERROR_STATES,
    INBOUND_DELIVERY_FAILURE_REVIEW_STATES,
    delivery_uses_validation_feedback,
    is_import_job_rejected,
)


def _delivery_default_category(delivery):
    if delivery_uses_validation_feedback(delivery.state) and delivery.error_count:
        return "data_validation"
    return "unexpected_bug"


def _job_default_category(job):
    if is_import_job_rejected(job.state):
        return "operator_input"
    if job.error_count:
        return "data_validation"
    return "unexpected_bug"


def migrate(cr, version):
    """Backfill typed failure metadata for deliveries and import jobs."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    deliveries = (
        env["federation.integration.delivery"]
        .sudo()
        .search(
            [
                ("failure_category", "=", False),
                ("result_message", "!=", False),
                ("state", "in", INBOUND_DELIVERY_FAILURE_REVIEW_STATES),
            ]
        )
    )
    for delivery in deliveries:
        failure_category, operator_message = build_failure_feedback(
            detail=delivery.result_message,
            default_category=_delivery_default_category(delivery),
        )
        delivery.write(
            {
                "failure_category": failure_category,
                "operator_message": operator_message,
            }
        )

    jobs = (
        env["federation.import.job"]
        .sudo()
        .search(
            [
                ("failure_category", "=", False),
                ("state", "in", IMPORT_JOB_ERROR_STATES),
            ]
        )
    )
    for job in jobs:
        detail = (
            job.rejection_reason
            or job.execution_result_message
            or job.preview_result_message
        )
        if not detail:
            continue
        failure_category, operator_message = build_failure_feedback(
            detail=detail,
            default_category=_job_default_category(job),
        )
        job.write(
            {
                "failure_category": failure_category,
                "operator_message": operator_message,
            }
        )
