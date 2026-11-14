from odoo import _, fields, models
from odoo.exceptions import ValidationError

from ..planning_tokens import (
    PUBLISHED_PLANNING_CONTEXT_KEY,
    PUBLISHED_PLANNING_TOKEN,
)


class MatchJourney(models.Model):
    _inherit = "federation.match"

    def write(self, vals):
        self.check_access("write")
        protected = {
            "date_scheduled",
            "scheduled_date",
            "scheduled_time",
            "published_slot_id",
            "schedule_publication_id",
            "venue_id",
            "playing_area_id",
            "round_id",
        }
        if (
            protected.intersection(vals)
            and self.env.context.get(PUBLISHED_PLANNING_CONTEXT_KEY)
            is not PUBLISHED_PLANNING_TOKEN
        ):
            if self.filtered("schedule_publication_id"):
                raise ValidationError(
                    _(
                        "Published match planning is schedule-owned. Use the match workspace to amend the schedule."
                    )
                )
        return super().write(vals)

    def action_open_match_workspace(self):
        self.ensure_one()
        self.check_access("read")
        return (
            self.logical_fixture_id.action_open_match_workspace()
            if self.logical_fixture_id
            else self.get_formview_action()
        )


class FixtureJourney(models.Model):
    _inherit = "federation.fixture"

    journey_match_state = fields.Selection(
        related="operational_match_id.state", readonly=True
    )
    journey_publication_id = fields.Many2one(
        related="operational_match_id.schedule_publication_id", readonly=True
    )
    journey_assignment_ids = fields.One2many(
        "federation.schedule.assignment", "fixture_id", string="Schedule history"
    )

    def action_open_match_workspace(self):
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.act_window",
            "name": _("Match workspace"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "sports_federation_schedule_approval.match_workspace_form"
                    ).id,
                    "form",
                )
            ],
        }

    def action_open_operational_match(self):
        self.ensure_one()
        self.check_access("read")
        if not self.operational_match_id:
            raise ValidationError(
                _(
                    "The pairing has no operational match yet. Resolve teams and publish its schedule first."
                )
            )
        return self.operational_match_id.get_formview_action()

    def action_reschedule_from_workspace(self):
        self.ensure_one()
        self.check_access("read")
        assignment = self.env["federation.schedule.assignment"].search(
            [
                ("fixture_id", "=", self.id),
                ("schedule_id.state", "=", "published"),
            ],
            limit=1,
        )
        if not assignment:
            raise ValidationError(
                _("Use the competition planner to allocate this unpublished fixture.")
            )
        schedule = assignment.schedule_id
        self.env["federation.competition.role.assignment"].assert_role(
            schedule.edition_id, "schedule_planner", "competition_director"
        )
        wizard = self.env["federation.match.reschedule.wizard"].create(
            {
                "fixture_id": self.id,
                "schedule_id": schedule.id,
                "expected_publication_id": schedule.matchday_id.current_publication_id.id,
                "slot_id": assignment.slot_id.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }


class MatchRescheduleWizard(models.TransientModel):
    _name = "federation.match.reschedule.wizard"
    _description = "Review Match Rescheduling"

    fixture_id = fields.Many2one("federation.fixture", required=True, readonly=True)
    schedule_id = fields.Many2one("federation.schedule", required=True, readonly=True)
    matchday_id = fields.Many2one(related="schedule_id.matchday_id", readonly=True)
    expected_publication_id = fields.Integer(required=True, readonly=True)
    slot_id = fields.Many2one("federation.schedule.slot", required=True)
    reason = fields.Text(required=True)

    def action_prepare_amendment(self):
        self.ensure_one()
        schedule = self.schedule_id
        self.env["federation.competition.role.assignment"].assert_role(
            schedule.edition_id, "schedule_planner", "competition_director"
        )
        if not (self.reason or "").strip():
            raise ValidationError(_("A rescheduling reason is required."))
        schedule.check_access("read")
        self.env.cr.execute(
            "SELECT id FROM federation_matchday WHERE id = %s FOR UPDATE",
            [schedule.matchday_id.id],
        )
        schedule.matchday_id.invalidate_recordset()
        current = schedule.matchday_id.current_publication_id
        if (
            current.id != self.expected_publication_id
            or current.state != "live"
            or current.schedule_id != schedule
        ):
            raise ValidationError(
                _("The published schedule changed. Refresh the match workspace.")
            )
        if self.slot_id.matchday_id != schedule.matchday_id:
            raise ValidationError(
                _(
                    "This command moves within a game day. Cross-day changes require a coordinated competition amendment."
                )
            )
        assignment = schedule.assignment_ids.filtered(
            lambda row: row.fixture_id == self.fixture_id
        )
        if len(assignment) != 1:
            raise ValidationError(
                _("The fixture is no longer uniquely allocated in this schedule.")
            )
        if schedule.assignment_ids.filtered(
            lambda row: row.slot_id == self.slot_id
            and row.fixture_id != self.fixture_id
        ):
            raise ValidationError(
                _(
                    "The target slot is occupied. Use the planner to prepare a reviewed swap."
                )
            )
        if assignment.slot_id == self.slot_id:
            raise ValidationError(_("Choose a different slot; no amendment is needed."))
        if self.fixture_id.operational_match_id.state not in (
            False,
            "draft",
            "scheduled",
        ):
            raise ValidationError(
                _(
                    "Started or completed matches cannot be rescheduled as planning changes."
                )
            )
        with self.env.cr.savepoint():
            replacement = schedule.action_create_revision(self.reason.strip())
            target = replacement.assignment_ids.filtered(
                lambda row: row.fixture_id == self.fixture_id
            )
            target.write(
                {
                    "slot_id": self.slot_id.id,
                    "method": "manual",
                    "assigned_by_id": self.env.user.id,
                }
            )
            result = self.env["federation.schedule.validator"].validate_map(
                replacement,
                {
                    row.fixture_id.id: row.slot_id.id
                    for row in replacement.assignment_ids
                },
            )
            if not result["valid"]:
                raise ValidationError(
                    _(
                        "The proposed schedule fails capacity, conflict or rest validation. Review the competition planner."
                    )
                )
            replacement.message_post(
                body=_(
                    "Rescheduling prepared: %(reason)s. The live publication is unchanged until review and publication.",
                    reason=self.reason.strip(),
                )
            )
            return replacement.get_formview_action()
