from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FederationMatchReferee(models.Model):
    _name = "federation.match.referee"
    _description = "Match Referee Assignment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "match_id, role"

    match_id = fields.Many2one(
        "federation.match", string="Match", required=True, ondelete="cascade"
    )
    referee_id = fields.Many2one(
        "federation.referee", string="Referee", required=True, ondelete="restrict"
    )
    tournament_id = fields.Many2one(
        "federation.tournament",
        string="Tournament",
        related="match_id.tournament_id",
        store=True,
    )
    role = fields.Selection(
        [
            ("head", "Head Referee"),
            ("assistant_1", "Assistant Referee 1"),
            ("assistant_2", "Assistant Referee 2"),
            ("fourth", "Fourth Official"),
            ("table", "Table Official"),
        ],
        string="Role",
        required=True,
        default="head",
    )
    state = fields.Selection(
        [
            ("draft", "Assigned"),
            ("confirmed", "Confirmed"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
    )
    assigned_on = fields.Datetime(
        string="Assigned On",
        default=fields.Datetime.now,
        readonly=True,
    )
    confirmed_on = fields.Datetime(string="Confirmed On", readonly=True)
    completed_on = fields.Datetime(string="Completed On", readonly=True)
    cancelled_on = fields.Datetime(string="Cancelled On", readonly=True)
    confirmation_deadline = fields.Datetime(
        compute="_compute_assignment_readiness",
        string="Confirmation Deadline",
    )
    is_confirmation_overdue = fields.Boolean(
        compute="_compute_assignment_readiness",
        string="Confirmation Overdue",
    )
    assignment_ready = fields.Boolean(
        compute="_compute_assignment_readiness",
        string="Assignment Ready",
    )
    readiness_feedback = fields.Text(
        compute="_compute_assignment_readiness",
        string="Readiness Feedback",
    )
    assignment_has_warning = fields.Boolean(
        compute="_compute_assignment_readiness",
        string="Has Warning",
    )
    assignment_warning_feedback = fields.Text(
        compute="_compute_assignment_readiness",
        string="Assignment Warnings",
    )
    notes = fields.Text(string="Notes")

    _match_referee_role_unique = models.Constraint(
        "unique (match_id, referee_id, role)",
        "A referee can only be assigned once per role per match.",
    )

    def _assignment_window(self, match=False, start_dt=False, end_dt=False):
        self.ensure_one()
        if start_dt:
            return (
                fields.Datetime.to_datetime(start_dt),
                (
                    fields.Datetime.to_datetime(end_dt)
                    if end_dt
                    else fields.Datetime.to_datetime(start_dt)
                ),
            )

        match = match or self.match_id
        if not match:
            return False, False

        slot = match.slot_id if "slot_id" in match._fields else False
        start_value = (
            slot.start_datetime
            if slot and slot.start_datetime
            else match.date_scheduled
        )
        if not start_value:
            return False, False
        end_value = (
            slot.end_datetime
            if slot and slot.end_datetime
            else fields.Datetime.to_datetime(start_value) + timedelta(minutes=1)
        )
        return (
            fields.Datetime.to_datetime(start_value),
            (
                fields.Datetime.to_datetime(end_value)
                if end_value
                else fields.Datetime.to_datetime(start_value)
            ),
        )

    @staticmethod
    def _windows_overlap(start_a, end_a, start_b, end_b):
        if not start_a or not start_b:
            return False
        end_a = end_a or start_a
        end_b = end_b or start_b
        return not (end_a <= start_b or end_b <= start_a)

    def _get_overlapping_assignments(self, start_dt=False, end_dt=False):
        self.ensure_one()
        target_start, target_end = self._assignment_window(
            start_dt=start_dt,
            end_dt=end_dt,
        )
        if not target_start or not self.referee_id:
            return self.browse([])

        other_assignments = self.search(
            [
                ("referee_id", "=", self.referee_id.id),
                ("match_id", "!=", self.match_id.id),
                ("state", "!=", "cancelled"),
                ("id", "!=", self.id),
            ]
        )
        return other_assignments.filtered(
            lambda other: self._windows_overlap(
                target_start,
                target_end,
                *other._assignment_window(),
            )
        )

    def _window_is_covered_by_availability(self, start_dt=False, end_dt=False):
        self.ensure_one()
        availability_records = self.referee_id.availability_ids.filtered("active")
        if not availability_records:
            return True
        target_start, target_end = self._assignment_window(
            start_dt=start_dt,
            end_dt=end_dt,
        )
        if not target_start:
            return True
        return bool(
            availability_records.filtered(
                lambda availability: availability.date_start <= target_start
                and availability.date_end >= (target_end or target_start)
            )
        )

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        records = super().create(vals_list)
        Dispatcher = self.env.get("federation.notification.dispatcher")
        if Dispatcher is not None:
            for record in records:
                Dispatcher.send_referee_assigned(record)
        return records

    @api.depends(
        "match_id.date_scheduled",
        "match_id.state",
        "referee_id.active",
        "referee_id.certification_level",
        "referee_id.certification_ids.active",
        "referee_id.certification_ids.issue_date",
        "referee_id.certification_ids.expiry_date",
        "referee_id.availability_ids.active",
        "referee_id.availability_ids.date_start",
        "referee_id.availability_ids.date_end",
        "referee_id.match_assignment_ids.state",
        "referee_id.match_assignment_ids.match_id.date_scheduled",
        "state",
    )
    def _compute_assignment_readiness(self):
        """Compute assignment readiness."""
        for record in self:
            issues = record._get_readiness_issues()
            warnings = record._get_assignment_warnings()
            record.assignment_ready = not bool(issues)
            record.readiness_feedback = "\n".join(issues) if issues else False
            record.assignment_has_warning = bool(warnings)
            record.assignment_warning_feedback = (
                "\n".join(warnings) if warnings else False
            )

            if record.match_id.date_scheduled:
                scheduled_at = fields.Datetime.to_datetime(
                    record.match_id.date_scheduled
                )
                record.confirmation_deadline = scheduled_at - timedelta(hours=48)
            else:
                record.confirmation_deadline = False

            record.is_confirmation_overdue = bool(
                record.state == "draft"
                and record.confirmation_deadline
                and fields.Datetime.now() > record.confirmation_deadline
                and record.match_id.state not in ("done", "cancelled")
            )

    def _has_valid_certification_for_match(self):
        """Return whether the record has valid certification for match."""
        self.ensure_one()
        if not self.referee_id:
            return False
        if not self.referee_id.certification_ids:
            return bool(self.referee_id.certification_level)

        reference_date = (
            fields.Datetime.to_datetime(self.match_id.date_scheduled).date()
            if self.match_id.date_scheduled
            else fields.Date.context_today(self)
        )
        valid_certifications = self.referee_id.certification_ids.filtered(
            lambda cert: cert.active
            and (not cert.issue_date or cert.issue_date <= reference_date)
            and (not cert.expiry_date or cert.expiry_date >= reference_date)
        )
        return bool(valid_certifications)

    def _get_readiness_issues(self):
        """Return readiness issues."""
        self.ensure_one()
        issues = []
        if not self.referee_id.active:
            issues.append(_("Referee is inactive."))
        if not self._has_valid_certification_for_match():
            issues.append(
                _(
                    "Referee certification is missing or expired for the scheduled match date."
                )
            )
        overlaps = self._get_overlapping_assignments()
        if overlaps:
            issues.append(
                _(
                    "Referee is already assigned to %(count)s overlapping match(es).",
                    count=len(overlaps),
                )
            )
        return issues

    def _get_assignment_warnings(self, start_dt=False, end_dt=False):
        """Return non-blocking assignment warnings."""
        self.ensure_one()
        warnings = []
        if not self._window_is_covered_by_availability(
            start_dt=start_dt,
            end_dt=end_dt,
        ):
            warnings.append(_("No availability record covers this match slot."))
        return warnings

    def action_confirm(self):
        """Execute the confirm action."""
        for rec in self:
            issues = rec._get_readiness_issues()
            if issues:
                raise ValidationError("\n".join(issues))
            rec.write(
                {
                    "state": "confirmed",
                    "confirmed_on": fields.Datetime.now(),
                    "cancelled_on": False,
                }
            )

    def action_done(self):
        """Execute the done action."""
        for rec in self:
            rec.write(
                {
                    "state": "done",
                    "completed_on": fields.Datetime.now(),
                }
            )

    def action_cancel(self):
        """Execute the cancel action."""
        for rec in self:
            rec.write(
                {
                    "state": "cancelled",
                    "cancelled_on": fields.Datetime.now(),
                }
            )

    def action_draft(self):
        """Execute the draft action."""
        for rec in self:
            rec.write(
                {
                    "state": "draft",
                    "confirmed_on": False,
                    "completed_on": False,
                    "cancelled_on": False,
                }
            )


class FederationMatchRefereeExtension(models.Model):
    _inherit = "federation.match"

    referee_assignment_ids = fields.One2many(
        "federation.match.referee", "match_id", string="Referee Assignments"
    )
    referee_assignment_count = fields.Integer(
        compute="_compute_referee_assignment_count",
        string="Referee Assignment Count",
    )
    club_referee_duty_ids = fields.One2many(
        "federation.match.club.referee.duty", "match_id", string="Club Referee Duties"
    )
    club_duty_pending_count = fields.Integer(
        compute="_compute_club_duty_pending_count",
        string="Pending Club Duties",
    )
    required_referee_count = fields.Integer(
        compute="_compute_officiating_readiness",
        string="Required Referees",
    )
    confirmed_referee_count = fields.Integer(
        compute="_compute_officiating_readiness",
        string="Confirmed Referees",
    )
    overdue_referee_confirmation_count = fields.Integer(
        compute="_compute_officiating_readiness",
        string="Overdue Confirmations",
    )
    missing_referees_count = fields.Integer(
        compute="_compute_officiating_readiness",
        string="Missing Referees",
    )
    is_officially_ready = fields.Boolean(
        compute="_compute_officiating_readiness",
        string="Officials Ready",
    )
    official_readiness_issues = fields.Text(
        compute="_compute_officiating_readiness",
        string="Official Readiness Issues",
    )

    @api.depends("referee_assignment_ids")
    def _compute_referee_assignment_count(self):
        """Compute referee assignment count."""
        for record in self:
            record.referee_assignment_count = len(record.referee_assignment_ids)

    @api.depends("club_referee_duty_ids.state")
    def _compute_club_duty_pending_count(self):
        """Compute number of club duties not yet confirmed."""
        for record in self:
            record.club_duty_pending_count = sum(
                1
                for duty in record.club_referee_duty_ids
                if duty.state not in ("confirmed",)
            )

    @api.depends(
        "date_scheduled",
        "state",
        "tournament_id.rule_set_id.referee_required_count",
        "tournament_id.competition_id.rule_set_id.referee_required_count",
        "referee_assignment_ids.state",
        "referee_assignment_ids.role",
        "referee_assignment_ids.is_confirmation_overdue",
        "referee_assignment_ids.assignment_ready",
        "referee_assignment_ids.readiness_feedback",
        "referee_assignment_ids.assignment_has_warning",
        "referee_assignment_ids.assignment_warning_feedback",
    )
    def _compute_officiating_readiness(self):
        """Compute officiating readiness."""
        for record in self:
            issues = record._get_officiating_issues()
            confirmed_assignments = record.referee_assignment_ids.filtered(
                lambda assignment: assignment.state in ("confirmed", "done")
            )
            overdue_assignments = record.referee_assignment_ids.filtered(
                lambda assignment: assignment.is_confirmation_overdue
            )
            required_count = record._get_required_referee_count()
            record.required_referee_count = required_count
            record.confirmed_referee_count = len(confirmed_assignments)
            record.overdue_referee_confirmation_count = len(overdue_assignments)
            record.missing_referees_count = max(
                required_count - len(confirmed_assignments), 0
            )
            record.is_officially_ready = not bool(issues)
            record.official_readiness_issues = "\n".join(issues) if issues else False

    def _get_effective_officiating_rule_set(self):
        """Return effective officiating rule set."""
        self.ensure_one()
        if self.tournament_id and self.tournament_id.rule_set_id:
            return self.tournament_id.rule_set_id
        if (
            self.tournament_id
            and self.tournament_id.competition_id
            and self.tournament_id.competition_id.rule_set_id
        ):
            return self.tournament_id.competition_id.rule_set_id
        return self.env["federation.rule.set"].browse([])

    def _get_required_referee_count(self):
        """Return required referee count."""
        self.ensure_one()
        rule_set = self._get_effective_officiating_rule_set()
        return rule_set.referee_required_count if rule_set else 0

    def _get_officiating_issues(self):
        """Return officiating issues."""
        self.ensure_one()
        issues = []
        confirmed_assignments = self.referee_assignment_ids.filtered(
            lambda assignment: assignment.state in ("confirmed", "done")
        )
        required_count = self._get_required_referee_count()
        if required_count and len(confirmed_assignments) < required_count:
            issues.append(
                _(
                    "Confirmed officials (%(actual)s) are below the required count of %(required)s."
                )
                % {
                    "actual": len(confirmed_assignments),
                    "required": required_count,
                }
            )

        if required_count and not confirmed_assignments.filtered(
            lambda assignment: assignment.role == "head"
        ):
            issues.append(_("A confirmed head referee is required."))

        overdue_assignments = self.referee_assignment_ids.filtered(
            lambda assignment: assignment.is_confirmation_overdue
        )
        if overdue_assignments:
            issues.append(
                _("%(count)s referee confirmation(s) are overdue.")
                % {"count": len(overdue_assignments)}
            )

        invalid_assignments = self.referee_assignment_ids.filtered(
            lambda assignment: assignment.state != "cancelled"
            and not assignment.assignment_ready
        )
        role_labels = dict(
            self.env["federation.match.referee"]._fields["role"].selection
        )
        for assignment in invalid_assignments:
            issues.append(
                _("%(role)s: %(issues)s")
                % {
                    "role": role_labels.get(assignment.role, assignment.role),
                    "issues": assignment.readiness_feedback,
                }
            )

        return issues

    def _get_officiating_warnings(self):
        """Return non-blocking officiating warnings."""
        self.ensure_one()
        warnings = []
        role_labels = dict(
            self.env["federation.match.referee"]._fields["role"].selection
        )
        warning_assignments = self.referee_assignment_ids.filtered(
            lambda assignment: assignment.state != "cancelled"
            and assignment.assignment_has_warning
        )
        for assignment in warning_assignments:
            warnings.append(
                _("%(role)s: %(issues)s")
                % {
                    "role": role_labels.get(assignment.role, assignment.role),
                    "issues": assignment.assignment_warning_feedback,
                }
            )
        return warnings

    def action_view_referee_assignments(self):
        """Execute the view referee assignments action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_officiating.federation_match_referee_action"
        )
        action["domain"] = [("match_id", "=", self.id)]
        action["context"] = {"default_match_id": self.id}
        return action

    def action_view_club_referee_duties(self):
        """Execute the view club referee duties action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_officiating.federation_match_club_referee_duty_action"
        )
        action["domain"] = [("match_id", "=", self.id)]
        action["context"] = {"default_match_id": self.id}
        return action
