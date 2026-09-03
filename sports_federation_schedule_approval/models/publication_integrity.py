import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_REVIEW_DECISION_TOKEN = object()
_REVIEW_WITHDRAWAL_TOKEN = object()


class FederationScheduleReviewIntegrity(models.Model):
    _inherit = "federation.schedule.review"

    snapshot_digest = fields.Char(required=True, readonly=True, index=True)
    submitted_by_id = fields.Many2one(
        "res.users", required=True, readonly=True, ondelete="restrict"
    )
    reviewed_at = fields.Datetime(readonly=True)

    def write(self, vals):
        """Protect submitted evidence and command-owned decision fields."""
        self.check_access("write")
        evidence_fields = {
            "schedule_id",
            "submitted_revision",
            "assignment_snapshot",
            "snapshot_digest",
            "submitted_by_id",
        }
        decision_fields = {"state", "reviewer_id", "review_note", "reviewed_at"}
        if evidence_fields.intersection(vals) and self:
            raise ValidationError(_("Submitted review evidence is immutable."))
        decision_token = self.env.context.get("schedule_review_decision_token")
        if decision_fields.intersection(vals) and decision_token not in (
            _REVIEW_DECISION_TOKEN,
            _REVIEW_WITHDRAWAL_TOKEN,
        ):
            if set(vals) == {"review_note"} and all(
                review.state == "pending" for review in self
            ):
                return super().write(vals)
            raise ValidationError(
                _("Review decisions must be made through the approval command service.")
            )
        return super().write(vals)

    def _write_decision(self, vals):
        """Apply one authorized decision without bypassing record ACLs."""
        self.ensure_one()
        self.check_access("write")
        if self.state != "pending":
            raise ValidationError(_("Only pending reviews can be decided."))
        self.env["federation.competition.role.assignment"].assert_role(
            self.edition_id, "schedule_approver", "competition_director"
        )
        allowed_fields = {"state", "reviewer_id", "review_note", "reviewed_at"}
        if not vals or set(vals) - allowed_fields:
            raise ValidationError(_("The review decision contains protected fields."))
        if vals.get("state") not in {"approved", "changes_requested"}:
            raise ValidationError(_("Select a valid review decision."))
        if vals.get("reviewer_id") != self.env.user.id:
            raise ValidationError(_("The reviewer must be the current user."))
        return self.with_context(
            schedule_review_decision_token=_REVIEW_DECISION_TOKEN
        ).write(vals)

    def _write_withdrawal(self, reason):
        self.ensure_one()
        if self.state != "pending":
            raise ValidationError(_("Only a pending review can be withdrawn."))
        return (
            self.sudo()
            .with_context(schedule_review_decision_token=_REVIEW_WITHDRAWAL_TOKEN)
            .write(
                {
                    "state": "withdrawn",
                    "review_note": reason,
                    "reviewed_at": fields.Datetime.now(),
                }
            )
        )

    def unlink(self):
        raise ValidationError("Schedule reviews are retained as audit evidence.")


class FederationSchedulePublicationIntegrity(models.Model):
    _inherit = "federation.schedule.publication"

    snapshot_digest = fields.Char(required=True, readonly=True, index=True)
    source_revision = fields.Integer(required=True, readonly=True)
    review_id = fields.Many2one(
        "federation.schedule.review", required=True, readonly=True, ondelete="restrict"
    )

    def init(self):
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                federation_schedule_publication_one_live_matchday
            ON federation_schedule_publication (matchday_id)
            WHERE state = 'live' AND matchday_id IS NOT NULL
            """)

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
