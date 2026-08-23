import hashlib
import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationScheduleReviewIntegrity(models.Model):
    _inherit = "federation.schedule.review"

    snapshot_digest = fields.Char(required=True, readonly=True, index=True)
    submitted_by_id = fields.Many2one(
        "res.users", required=True, readonly=True, ondelete="restrict"
    )
    reviewed_at = fields.Datetime(readonly=True)

    def write(self, vals):
        protected = {
            "schedule_id",
            "submitted_revision",
            "assignment_snapshot",
            "snapshot_digest",
            "submitted_by_id",
        }
        if protected.intersection(vals) and any(record.id for record in self):
            raise ValidationError("Submitted review evidence is immutable.")
        return super().write(vals)

    def unlink(self):
        raise ValidationError("Schedule reviews are retained as audit evidence.")


class FederationSchedulePublicationIntegrity(models.Model):
    _inherit = "federation.schedule.publication"

    snapshot_digest = fields.Char(required=True, readonly=True, index=True)
    source_revision = fields.Integer(required=True, readonly=True)
    review_id = fields.Many2one(
        "federation.schedule.review", required=True, readonly=True, ondelete="restrict"
    )

    @api.model
    def digest_snapshot(self, snapshot):
        payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def write(self, vals):
        if set(vals) - {"state"}:
            raise ValidationError("Published schedule snapshots are immutable.")
        if "state" in vals and vals["state"] not in ("live", "superseded"):
            raise ValidationError("Invalid publication state.")
        return super().write(vals)

    def unlink(self):
        raise ValidationError("Published schedules are retained as audit evidence.")


class FederationMatchdayPublication(models.Model):
    _inherit = "federation.matchday"

    current_publication_id = fields.Many2one(
        "federation.schedule.publication",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )


class FederationMatchPublishedSlot(models.Model):
    _inherit = "federation.match"

    published_slot_id = fields.Many2one(
        "federation.schedule.slot",
        readonly=True,
        copy=False,
        ondelete="restrict",
        index=True,
    )
    schedule_publication_id = fields.Many2one(
        "federation.schedule.publication",
        readonly=True,
        copy=False,
        ondelete="restrict",
        index=True,
    )
