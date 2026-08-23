from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationScheduleApprovalCommands(models.AbstractModel):
    _name = "federation.schedule.approval.commands"
    _description = "Schedule Approval Commands"

    def _snapshot(self, schedule):
        return [
            {
                "fixture_id": assignment.fixture_id.id,
                "match_id": assignment.fixture_id.operational_match_id.id,
                "slot_id": assignment.slot_id.id,
                "court_id": assignment.slot_id.court_id.id,
                "start": fields.Datetime.to_string(assignment.slot_id.start_datetime),
                "end": fields.Datetime.to_string(assignment.slot_id.end_datetime),
            }
            for assignment in schedule.assignment_ids.sorted(
                lambda item: (item.slot_id.start_datetime, item.slot_id.id)
            )
        ]

    def _digest(self, snapshot):
        return self.env["federation.schedule.publication"].digest_snapshot(snapshot)

    @api.model
    def start_review(self, schedule_id):
        schedule = self.env["federation.schedule"].browse(int(schedule_id)).exists()
        if not schedule or schedule.state != "ready_for_review":
            raise ValidationError(_("Only submitted schedules can enter review."))
        self.env["federation.competition.role.assignment"].assert_role(
            schedule.edition_id, "schedule_approver", "competition_director"
        )
        pending = self.env["federation.schedule.review"].search(
            [
                ("schedule_id", "=", schedule.id),
                ("submitted_revision", "=", schedule.revision),
                ("state", "=", "pending"),
            ],
            limit=1,
        )
        if pending:
            return pending
        snapshot = self._snapshot(schedule)
        return self.env["federation.schedule.review"].create(
            {
                "schedule_id": schedule.id,
                "submitted_revision": schedule.revision,
                "assignment_snapshot": snapshot,
                "snapshot_digest": self._digest(snapshot),
                "submitted_by_id": schedule.write_uid.id,
            }
        )

    def _resolve_pending(self, review_id):
        review = self.env["federation.schedule.review"].browse(int(review_id)).exists()
        if not review or review.state != "pending":
            raise ValidationError(_("Only pending reviews can be decided."))
        self.env["federation.competition.role.assignment"].assert_role(
            review.edition_id, "schedule_approver", "competition_director"
        )
        if review.submitted_by_id == self.env.user:
            raise ValidationError(
                _("The submitting planner cannot approve their own schedule.")
            )
        if review.schedule_id.revision != review.submitted_revision:
            raise ValidationError(_("The working schedule changed after submission."))
        snapshot = self._snapshot(review.schedule_id)
        if self._digest(snapshot) != review.snapshot_digest:
            raise ValidationError(
                _(
                    "The submitted schedule snapshot no longer matches the working schedule."
                )
            )
        return review

    @api.model
    def request_changes(self, review_id, note):
        if not (note or "").strip():
            raise ValidationError(_("Explain the requested schedule changes."))
        review = self._resolve_pending(review_id)
        review.write(
            {
                "state": "changes_requested",
                "reviewer_id": self.env.user.id,
                "review_note": note,
                "reviewed_at": fields.Datetime.now(),
            }
        )
        review.schedule_id.state = "changes_requested"
        return True

    @api.model
    def approve(self, review_id, note=False):
        review = self._resolve_pending(review_id)
        validation = self.env["federation.schedule.validator"].validate_map(
            review.schedule_id,
            {a.fixture_id.id: a.slot_id.id for a in review.schedule_id.assignment_ids},
        )
        if not validation["valid"]:
            raise ValidationError(
                _("The schedule no longer satisfies publication constraints.")
            )
        review.write(
            {
                "state": "approved",
                "reviewer_id": self.env.user.id,
                "review_note": note,
                "reviewed_at": fields.Datetime.now(),
            }
        )
        review.schedule_id.state = "approved"
        self.env["federation.competition.event"].emit(
            review.schedule_id,
            "schedule_approved",
            {"review_id": review.id, "snapshot_digest": review.snapshot_digest},
        )
        return True

    @api.model
    def publish(self, schedule_id, reason=False):
        schedule = self.env["federation.schedule"].browse(int(schedule_id)).exists()
        self.env["federation.competition.role.assignment"].assert_role(
            schedule.edition_id, "schedule_approver", "competition_director"
        )
        if not schedule or schedule.state != "approved":
            raise ValidationError(_("Approve the schedule before publication."))
        if schedule.matchday_id.state == "open":
            raise ValidationError(
                _("Close live match-day operations before replacing publication.")
            )
        review = self.env["federation.schedule.review"].search(
            [
                ("schedule_id", "=", schedule.id),
                ("submitted_revision", "=", schedule.revision),
                ("state", "=", "approved"),
            ],
            order="id desc",
            limit=1,
        )
        if not review:
            raise ValidationError(
                _("No approved review exists for this schedule revision.")
            )
        snapshot = self._snapshot(schedule)
        digest = self._digest(snapshot)
        if digest != review.snapshot_digest:
            raise ValidationError(
                _("The approved snapshot no longer matches the schedule.")
            )
        live = self.env["federation.schedule.publication"].search(
            [("edition_id", "=", schedule.edition_id.id), ("state", "=", "live")]
        )
        if live and not (reason or "").strip():
            raise ValidationError(
                _("Enter a reason when replacing a live publication.")
            )
        version = (
            max(
                self.env["federation.schedule.publication"]
                .search([("edition_id", "=", schedule.edition_id.id)])
                .mapped("version")
                or [0]
            )
            + 1
        )
        live.write({"state": "superseded"})
        publication = self.env["federation.schedule.publication"].create(
            {
                "schedule_id": schedule.id,
                "version": version,
                "reason": reason,
                "assignment_snapshot": snapshot,
                "snapshot_digest": digest,
                "source_revision": schedule.revision,
                "review_id": review.id,
            }
        )
        for assignment in schedule.assignment_ids:
            match = assignment.fixture_id.operational_match_id
            if not match:
                raise ValidationError(
                    _("Every scheduled fixture must have an operational match.")
                )
            match.write(
                {
                    "published_slot_id": assignment.slot_id.id,
                    "schedule_publication_id": publication.id,
                    "date_scheduled": assignment.slot_id.start_datetime,
                }
            )
        schedule.state = "published"
        schedule.matchday_id.write(
            {"state": "scheduled", "current_publication_id": publication.id}
        )
        self.env["federation.competition.event"].emit(
            schedule,
            "schedule_published",
            {
                "publication_id": publication.id,
                "version": version,
                "snapshot_digest": digest,
            },
        )
        return publication
