from odoo import fields, models, tools

from .report_operational import FederationReportOperational


class FederationReportComplianceRemediation(models.Model):
    _name = "federation.report.compliance.remediation"
    _description = "Federation Compliance Remediation Report"
    _auto = False
    _order = "sla_status desc, age_days desc, created_on asc"

    STATUS_SELECTION = [
        ("submitted", "Submitted"),
        ("rejected", "Rejected"),
        ("replacement_requested", "Replacement Requested"),
        ("expired", "Expired"),
    ]

    submission_id = fields.Many2one(
        "federation.document.submission", string="Submission", readonly=True
    )
    requirement_id = fields.Many2one(
        "federation.document.requirement", string="Requirement", readonly=True
    )
    target_model = fields.Char(string="Target Model", readonly=True)
    target_display = fields.Char(string="Target", readonly=True)
    status = fields.Selection(STATUS_SELECTION, string="Status", readonly=True)
    reviewer_id = fields.Many2one("res.users", string="Reviewer", readonly=True)
    queue_owner_display = fields.Char(string="Queue Owner", readonly=True)
    created_on = fields.Datetime(string="Created On", readonly=True)
    reviewed_on = fields.Datetime(string="Reviewed On", readonly=True)
    age_days = fields.Integer(string="Age (Days)", readonly=True)
    sla_due_on = fields.Datetime(string="SLA Due On", readonly=True)
    sla_status = fields.Selection(
        FederationReportOperational.SLA_STATUS_SELECTION,
        string="SLA Status",
        readonly=True,
    )
    remediation_note = fields.Text(string="Remediation Note", readonly=True)

    def init(self):
        """Rebuild the SQL view so remediation queue fields track the query output."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_compliance_remediation AS (
                -- block: queue
                WITH queue AS (
                    SELECT
                        sub.id AS submission_id,
                        sub.requirement_id,
                        sub.target_model,
                        sub.target_display,
                        CASE
                            WHEN sub.status = 'approved'
                              AND sub.expiry_date IS NOT NULL
                              AND sub.expiry_date < CURRENT_DATE THEN 'expired'
                            ELSE sub.status
                        END AS status,
                        sub.reviewer_id,
                        sub.create_date AS created_on,
                        sub.reviewed_on,
                        COALESCE(sub.reviewed_on, sub.create_date, NOW()) AS reference_dt,
                        CASE
                            WHEN (
                                CASE
                                    WHEN sub.status = 'approved'
                                      AND sub.expiry_date IS NOT NULL
                                      AND sub.expiry_date < CURRENT_DATE THEN 'expired'
                                    ELSE sub.status
                                END
                            ) IN ('rejected', 'expired') THEN COALESCE(sub.reviewed_on, sub.create_date, NOW()) + INTERVAL '1 day'
                            ELSE COALESCE(sub.create_date, NOW()) + INTERVAL '3 day'
                        END AS sla_due_on,
                        CASE
                            WHEN (
                                CASE
                                    WHEN sub.status = 'approved'
                                      AND sub.expiry_date IS NOT NULL
                                      AND sub.expiry_date < CURRENT_DATE THEN 'expired'
                                    ELSE sub.status
                                END
                            ) = 'submitted' THEN 'Submission is waiting for compliance review.'
                            WHEN (
                                CASE
                                    WHEN sub.status = 'approved'
                                      AND sub.expiry_date IS NOT NULL
                                      AND sub.expiry_date < CURRENT_DATE THEN 'expired'
                                    ELSE sub.status
                                END
                            ) = 'replacement_requested' THEN 'Replacement documentation is still outstanding.'
                            WHEN (
                                CASE
                                    WHEN sub.status = 'approved'
                                      AND sub.expiry_date IS NOT NULL
                                      AND sub.expiry_date < CURRENT_DATE THEN 'expired'
                                    ELSE sub.status
                                END
                            ) = 'rejected' THEN 'Rejected documentation still needs remediation.'
                            ELSE 'Approved documentation has expired and needs renewal.'
                        END AS remediation_note
                    FROM federation_document_submission sub
                    WHERE sub.status IN ('submitted', 'replacement_requested', 'rejected', 'expired')
                       OR (
                            sub.status = 'approved'
                            AND sub.expiry_date IS NOT NULL
                            AND sub.expiry_date < CURRENT_DATE
                        )
                )
                -- block: report_rows
                SELECT
                    row_number() OVER (
                        ORDER BY queue.sla_due_on ASC, queue.reference_dt ASC, queue.submission_id ASC
                    ) AS id,
                    queue.submission_id,
                    queue.requirement_id,
                    queue.target_model,
                    queue.target_display,
                    queue.status,
                    queue.reviewer_id,
                    COALESCE(rp.name, 'Compliance Review Queue') AS queue_owner_display,
                    queue.created_on,
                    queue.reviewed_on,
                    (CURRENT_DATE - COALESCE(queue.reference_dt::date, CURRENT_DATE))::int AS age_days,
                    queue.sla_due_on,
                    CASE
                        WHEN CURRENT_TIMESTAMP < queue.sla_due_on THEN 'within_sla'
                        WHEN CURRENT_DATE = queue.sla_due_on::date THEN 'due_today'
                        WHEN CURRENT_TIMESTAMP < (queue.sla_due_on + INTERVAL '2 day') THEN 'overdue'
                        ELSE 'escalated'
                    END AS sla_status,
                    queue.remediation_note
                FROM queue
                LEFT JOIN res_users ru ON ru.id = queue.reviewer_id
                LEFT JOIN res_partner rp ON rp.id = ru.partner_id
            )
            """)
