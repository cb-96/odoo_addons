from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationScheduleApprovalCommands(models.AbstractModel):
    _name = "federation.schedule.approval.commands"
    _description = "Schedule Approval Commands"

    def _snapshot(self, schedule):
        snapshot = [
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
        # Preserve explicit JSON evidence for an assignment-free review.
        return snapshot or [{"_empty": True}]

    def _digest(self, snapshot):
        return self.env["federation.schedule.publication"].digest_snapshot(snapshot)

    @staticmethod
    def _snapshot_without_operational_match(snapshot):
        """Return schedule facts independent of derived match materialization."""
        return [
            {key: value for key, value in item.items() if key != "match_id"}
            for item in snapshot
        ]

    def _ensure_operational_matches(self, schedule):
        fixtures = schedule.assignment_ids.mapped("fixture_id")
        missing = fixtures.filtered(lambda fixture: not fixture.operational_match_id)
        if missing:
            # Publication is already protected by the edition-role check.  The
            # materializer is the single authoritative path for creating the
            # derived operational matches, and the elevated section is limited
            # to these fixtures assigned to this schedule.
            self.env["federation.fixture.materializer"].sudo().materialize(missing)

    @api.model
    def start_review(self, schedule_id):
        schedule = self.env["federation.schedule"].browse(int(schedule_id)).exists()
        if not schedule or schedule.state != "ready_for_review":
            raise ValidationError(_("Only submitted schedules can enter review."))
        self.env["federation.competition.role.assignment"].assert_role(
            schedule.edition_id, "schedule_planner", "competition_director"
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
        return (
            self.env["federation.schedule.review"]
            .sudo()
            .create(
                {
                    "schedule_id": schedule.id,
                    "submitted_revision": schedule.revision,
                    "assignment_snapshot": snapshot,
                    "snapshot_digest": self._digest(snapshot),
                    "submitted_by_id": self.env.user.id,
                }
            )
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
        # Approval revalidation is a read-only operation over the complete
        # submitted schedule, including calendar and venue records.  The caller
        # has already passed the edition-role check above, so use controlled
        # elevation for these internal reads instead of granting approvers broad
        # access to every scheduling input model.
        schedule = review.schedule_id.sudo()
        if schedule.revision != review.submitted_revision:
            raise ValidationError(_("The working schedule changed after submission."))
        snapshot = self._snapshot(schedule)
        if self._digest(snapshot) != review.snapshot_digest:
            raise ValidationError(
                _(
                    "The submitted schedule snapshot no longer matches the working schedule."
                )
            )
        return review

    @api.model
    def withdraw(self, review_id, reason):
        if not (reason or "").strip():
            raise ValidationError(_("Explain why the schedule submission is withdrawn."))
        review = self.env["federation.schedule.review"].browse(int(review_id)).exists()
        if not review or review.state != "pending":
            raise ValidationError(_("Only a pending review can be withdrawn."))
        self.env["federation.competition.role.assignment"].assert_role(review.edition_id, "schedule_planner", "competition_director")
        if review.submitted_by_id != self.env.user and not self.env.user.has_group("sports_federation_base.group_federation_manager"):
            raise ValidationError(_("Only the submitting planner can withdraw this review."))
        review._write_withdrawal(reason)
        review.schedule_id.sudo().write({"state": "changes_requested"})
        return True

    @api.model
    def request_changes(self, review_id, note):
        if not (note or "").strip():
            raise ValidationError(_("Explain the requested schedule changes."))
        review = self._resolve_pending(review_id)
        review._write_decision(
            {
                "state": "changes_requested",
                "reviewer_id": self.env.user.id,
                "review_note": note,
                "reviewed_at": fields.Datetime.now(),
            }
        )
        review.schedule_id.sudo().state = "changes_requested"
        return True

    @api.model
    def approve(self, review_id, note=False):
        review = self._resolve_pending(review_id)
        schedule = review.schedule_id.sudo()
        validation = self.env["federation.schedule.validator"].validate_map(
            schedule,
            {a.fixture_id.id: a.slot_id.id for a in schedule.assignment_ids},
        )
        if not validation["valid"]:
            raise ValidationError(
                _("The schedule no longer satisfies publication constraints.")
            )
        review._write_decision(
            {
                "state": "approved",
                "reviewer_id": self.env.user.id,
                "review_note": note,
                "reviewed_at": fields.Datetime.now(),
            }
        )
        review.schedule_id.sudo().state = "approved"
        self.env["federation.competition.event"].emit(
            schedule,
            "schedule_approved",
            {"review_id": review.id, "snapshot_digest": review.snapshot_digest},
        )
        return True

    @api.model
    def publish(self, schedule_id, reason=False, expected_publication_id=None):
        schedule = self.env["federation.schedule"].browse(int(schedule_id)).exists()
        if not schedule:
            raise ValidationError(_("The schedule no longer exists."))
        self.env["federation.competition.role.assignment"].assert_role(
            schedule.edition_id, "schedule_approver", "competition_director"
        )
        # Publication also reads the full schedule, match day and fixture
        # graph.  Keep those internal reads controlled and read-only after the
        # caller has passed the edition-role check above.
        schedule = schedule.sudo()
        if schedule.state != "approved":
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
        self._ensure_operational_matches(schedule)
        snapshot = self._snapshot(schedule)
        digest = self._digest(snapshot)
        snapshot_matches_review = digest == review.snapshot_digest or (
            self._snapshot_without_operational_match(snapshot)
            == self._snapshot_without_operational_match(review.assignment_snapshot)
        )
        if not snapshot_matches_review:
            raise ValidationError(
                _("The approved snapshot no longer matches the schedule.")
            )
        # Serialize publication replacement and version allocation per match day.
        self.env.cr.execute(
            "SELECT id FROM federation_matchday WHERE id=%s FOR UPDATE",
            (schedule.matchday_id.id,),
        )
        live = self.env["federation.schedule.publication"].search(
            [
                ("matchday_id", "=", schedule.matchday_id.id),
                ("state", "=", "live"),
            ],
            limit=1,
        )
        live_id = live.id if live else 0
        if expected_publication_id is not None and live_id != int(
            expected_publication_id or 0
        ):
            raise ValidationError(
                _("The live publication changed in another session. Refresh and retry.")
            )
        if live and not (reason or "").strip():
            raise ValidationError(
                _("Enter a reason when replacing a live publication.")
            )
        version = (
            max(
                self.env["federation.schedule.publication"]
                .search([("matchday_id", "=", schedule.matchday_id.id)])
                .mapped("version")
                or [0]
            )
            + 1
        )
        live.sudo().write({"state": "superseded"})
        publication = (
            self.env["federation.schedule.publication"]
            .sudo()
            .create(
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
        )
        for assignment in schedule.assignment_ids:
            match = assignment.fixture_id.operational_match_id
            if not match:
                raise ValidationError(
                    _("Every scheduled fixture must have an operational match.")
                )
            match_values = {
                "published_slot_id": assignment.slot_id.id,
                "schedule_publication_id": publication.id,
                "date_scheduled": assignment.slot_id.start_datetime,
            }
            if "operational_slot_id" in match._fields:
                match_values.update(
                    {
                        "operational_slot_id": assignment.slot_id.id,
                        "operational_status": "as_published",
                    }
                )
            match.sudo().write(match_values)
        schedule.sudo().state = "published"
        schedule.matchday_id.sudo().write(
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
