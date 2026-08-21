from odoo import _, api, models
from odoo.exceptions import ValidationError


class FederationScheduleApprovalCommands(models.AbstractModel):
    _name = "federation.schedule.approval.commands"
    _description = "Schedule Approval Commands"

    def _snapshot(self, s):
        return [
            {"fixture_id": a.fixture_id.id, "slot_id": a.slot_id.id}
            for a in s.assignment_ids.sorted(
                lambda a: (a.slot_id.start_datetime, a.slot_id.id)
            )
        ]

    @api.model
    def start_review(self, schedule_id):
        s = self.env["federation.schedule"].browse(int(schedule_id)).exists()
        if s.state != "ready_for_review":
            raise ValidationError(_("Only submitted schedules can enter review."))
        return self.env["federation.schedule.review"].create(
            {
                "schedule_id": s.id,
                "submitted_revision": s.revision,
                "assignment_snapshot": self._snapshot(s),
            }
        )

    @api.model
    def request_changes(self, review_id, note):
        r = self.env["federation.schedule.review"].browse(int(review_id)).exists()
        self.env["federation.competition.role.assignment"].assert_role(
            r.edition_id, "schedule_approver", "competition_director"
        )
        r.write(
            {
                "state": "changes_requested",
                "reviewer_id": self.env.user.id,
                "review_note": note,
            }
        )
        r.schedule_id.state = "changes_requested"
        return True

    @api.model
    def approve(self, review_id, note=False):
        r = self.env["federation.schedule.review"].browse(int(review_id)).exists()
        self.env["federation.competition.role.assignment"].assert_role(
            r.edition_id, "schedule_approver", "competition_director"
        )
        if r.schedule_id.revision != r.submitted_revision:
            raise ValidationError(_("The working schedule changed after submission."))
        r.write(
            {"state": "approved", "reviewer_id": self.env.user.id, "review_note": note}
        )
        r.schedule_id.state = "approved"
        self.env["federation.competition.event"].emit(
            r.schedule_id, "schedule_approved", {"review_id": r.id}
        )
        return True

    @api.model
    def publish(self, schedule_id, reason=False):
        s = self.env["federation.schedule"].browse(int(schedule_id)).exists()
        self.env["federation.competition.role.assignment"].assert_role(
            s.edition_id, "schedule_approver", "competition_director"
        )
        if s.state != "approved":
            raise ValidationError(_("Approve the schedule before publication."))
        live = self.env["federation.schedule.publication"].search(
            [("schedule_id", "=", s.id), ("state", "=", "live")]
        )
        version = max(live.mapped("version") or [0]) + 1
        if live and not (reason or "").strip():
            raise ValidationError(
                _("Enter a reason when replacing a live publication.")
            )
        live.write({"state": "superseded"})
        p = self.env["federation.schedule.publication"].create(
            {
                "schedule_id": s.id,
                "version": version,
                "reason": reason,
                "assignment_snapshot": self._snapshot(s),
            }
        )
        s.state = "published"
        s.matchday_id.state = "scheduled"
        self.env["federation.competition.event"].emit(
            s, "schedule_published", {"publication_id": p.id, "version": version}
        )
        return p
