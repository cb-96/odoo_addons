from odoo import api, fields, models


class FederationAuditEvent(models.Model):
    _name = "federation.audit.event"
    _description = "Federation Audit Event"
    _order = "event_on desc, id desc"

    EVENT_FAMILY_SELECTION = [
        ("portal_privilege", "Portal Privilege"),
        ("integration_token", "Integration Token"),
    ]

    event_family = fields.Selection(
        EVENT_FAMILY_SELECTION,
        required=True,
        index=True,
        readonly=True,
    )
    event_type = fields.Char(required=True, index=True, readonly=True)
    action_name = fields.Char(index=True, readonly=True)
    description = fields.Text(required=True, readonly=True)
    target_model = fields.Char(index=True, readonly=True)
    target_res_id = fields.Integer(index=True, readonly=True)
    target_display_name = fields.Char(readonly=True)
    changed_fields = fields.Text(readonly=True)
    actor_user_id = fields.Many2one(
        "res.users",
        string="Actor",
        ondelete="set null",
        readonly=True,
        index=True,
    )
    event_on = fields.Datetime(
        required=True,
        readonly=True,
        default=fields.Datetime.now,
        index=True,
    )

    @api.model
    def log_event(
        self,
        event_family,
        event_type,
        description,
        target=False,
        actor=False,
        action_name=False,
        changed_fields=False,
        event_on=False,
    ):
        """Persist one audit event through a stable cross-module contract."""
        values = {
            "event_family": event_family,
            "event_type": event_type,
            "description": description,
            "action_name": action_name or False,
            "changed_fields": self._normalize_changed_fields(changed_fields),
            "actor_user_id": actor.id if actor else self.env.user.id,
            "event_on": event_on or fields.Datetime.now(),
        }
        if target:
            target = target.sudo().exists()[:1]
            if target:
                values.update(
                    {
                        "target_model": target._name,
                        "target_res_id": target.id,
                        "target_display_name": target.display_name,
                    }
                )
        return self.sudo().create(values)

    @api.model
    def log_record_events(
        self,
        event_family,
        event_type,
        description,
        records,
        actor=False,
        action_name=False,
        changed_fields=False,
        event_on=False,
    ):
        """Create one audit row per target record."""
        records = records.sudo().exists()
        if not records:
            return self.browse()
        return self.browse(
            [
                self.log_event(
                    event_family=event_family,
                    event_type=event_type,
                    description=description,
                    target=record,
                    actor=actor,
                    action_name=action_name,
                    changed_fields=changed_fields,
                    event_on=event_on,
                ).id
                for record in records
            ]
        )

    @api.model
    def _normalize_changed_fields(self, changed_fields):
        """Serialize changed field names into a stable audit payload."""
        if not changed_fields:
            return False
        if isinstance(changed_fields, str):
            return changed_fields
        return ", ".join(sorted({field for field in changed_fields if field})) or False
