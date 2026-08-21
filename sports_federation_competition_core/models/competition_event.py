import json
from odoo import api, fields, models


class FederationCompetitionEvent(models.Model):
    _name = "federation.competition.event"
    _description = "Competition Domain Event"
    _order = "occurred_at desc, id desc"
    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, ondelete="cascade", index=True
    )
    event_type = fields.Char(required=True, index=True, readonly=True)
    aggregate_model = fields.Char(required=True, readonly=True)
    aggregate_id = fields.Integer(required=True, index=True, readonly=True)
    actor_id = fields.Many2one("res.users", readonly=True, ondelete="set null")
    occurred_at = fields.Datetime(
        default=fields.Datetime.now, required=True, readonly=True, index=True
    )
    payload_json = fields.Text(readonly=True)

    @api.model
    def emit(self, aggregate, event_type, payload=None):
        edition = (
            aggregate
            if aggregate._name == "federation.competition.edition"
            else getattr(aggregate, "edition_id", False)
        )
        return self.sudo().create(
            {
                "edition_id": edition.id,
                "event_type": event_type,
                "aggregate_model": aggregate._name,
                "aggregate_id": aggregate.id,
                "actor_id": self.env.user.id,
                "payload_json": json.dumps(payload or {}, sort_keys=True, default=str),
            }
        )
