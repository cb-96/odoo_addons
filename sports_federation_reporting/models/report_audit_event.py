from odoo import fields, models, tools


class FederationReportAuditEvent(models.Model):
    _name = "federation.report.audit.event"
    _description = "Federation Audit Event Report"
    _auto = False
    _order = "event_on desc, audit_event_id desc"

    EVENT_FAMILY_SELECTION = [
        ("portal_privilege", "Portal Privilege"),
        ("integration_token", "Integration Token"),
    ]

    audit_event_id = fields.Many2one(
        "federation.audit.event", string="Audit Event", readonly=True
    )
    event_on = fields.Datetime(string="Event On", readonly=True)
    event_family = fields.Selection(
        EVENT_FAMILY_SELECTION, string="Event Family", readonly=True
    )
    event_type = fields.Char(string="Event Type", readonly=True)
    action_name = fields.Char(string="Action", readonly=True)
    actor_user_id = fields.Many2one("res.users", string="Actor", readonly=True)
    target_model = fields.Char(string="Target Model", readonly=True)
    target_res_id = fields.Integer(string="Target Record ID", readonly=True)
    target_display_name = fields.Char(string="Target", readonly=True)
    changed_fields = fields.Text(string="Changed Fields", readonly=True)
    description = fields.Text(string="Description", readonly=True)
    age_days = fields.Integer(string="Age (Days)", readonly=True)

    def init(self):
        """Create the SQL view that exposes audit events to reporting actions."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_audit_event AS (
                SELECT
                    event.id AS id,
                    event.id AS audit_event_id,
                    event.event_on,
                    event.event_family,
                    event.event_type,
                    event.action_name,
                    event.actor_user_id,
                    event.target_model,
                    event.target_res_id,
                    event.target_display_name,
                    event.changed_fields,
                    event.description,
                    (CURRENT_DATE - COALESCE(event.event_on::date, CURRENT_DATE))::int AS age_days
                FROM federation_audit_event event
            )
            """)
