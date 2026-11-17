"""Review club responsibilities against draft slots, without notifying clubs."""

from datetime import datetime
from html import escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..duty_allocation import allocate, fingerprint
from ..wizards.federation_matchday_assign_wizard import ROLE_SELECTION


class ScheduleClubDutyPlan(models.Model):
    _inherit = "federation.schedule"

    club_duty_policy = fields.Json(copy=False, readonly=True)
    club_duty_plan = fields.Json(copy=False, readonly=True)
    club_duty_signature = fields.Char(copy=False, readonly=True)
    club_duty_review_required = fields.Boolean(compute="_compute_club_duty_review")

    @api.model_create_multi
    def create(self, values_list):
        if any(
            {"club_duty_policy", "club_duty_plan", "club_duty_signature"}
            & values.keys()
            for values in values_list
        ):
            if not self.env.user.has_group(
                "sports_federation_base.group_federation_manager"
            ):
                raise AccessError(_("Only federation managers may plan club duties."))
        return super().create(values_list)

    def write(self, values):
        if {
            "club_duty_policy",
            "club_duty_plan",
            "club_duty_signature",
        } & values.keys():
            self._check_duty_planner()
            if any(schedule.state != "draft" for schedule in self):
                raise UserError(
                    _("Club-duty plans may only be changed on draft schedules.")
                )
        return super().write(values)

    def _check_duty_planner(self):
        if not self.env.user.has_group(
            "sports_federation_base.group_federation_manager"
        ):
            raise AccessError(_("Only federation managers may plan club duties."))
        self.check_access("write")

    def _live_duty_publication(self):
        self.ensure_one()
        publication = self.matchday_id.current_publication_id
        if (
            self.state != "published"
            or not publication
            or publication.state != "live"
            or publication.schedule_id != self
        ):
            raise UserError(
                _(
                    "This is not the current published schedule. Open the match "
                    "day's current schedule to plan club duties."
                )
            )
        return publication

    def _reviewable_duty_schedules(self):
        self._check_duty_planner()
        if not self or len(set(self.mapped("state"))) != 1:
            raise UserError(
                _(
                    "Select draft schedules or current published schedules, "
                    "not a mixture."
                )
            )
        for schedule in self:
            if schedule.state == "published":
                schedule._live_duty_publication()
            elif schedule.state != "draft":
                raise UserError(
                    _(
                        "Club duties can be planned on draft or current published "
                        "schedules only."
                    )
                )

    def _live_duty_geometry(self):
        publication = self._live_duty_publication()
        matches = self.env["federation.match"].search(
            [
                ("schedule_publication_id", "=", publication.id),
                ("logical_fixture_id", "!=", False),
                ("state", "!=", "cancelled"),
            ],
            order="id",
        )
        if not matches:
            raise UserError(
                _("The current publication contains no assignable matches.")
            )
        rows = []
        for match in matches:
            fixture = match.logical_fixture_id
            slot = match.operational_slot_id or match.published_slot_id
            if (
                not slot
                or not slot.start_datetime
                or not slot.end_datetime
                or slot.end_datetime <= slot.start_datetime
            ):
                raise UserError(
                    _(
                        "Every published match needs a valid time slot before "
                        "club-duty planning."
                    )
                )
            rule = match._get_effective_officiating_rule_set()
            rows.append(
                {
                    "assignment": match.id,
                    "match": match.id,
                    "publication": publication.id,
                    "fixture": fixture.id,
                    "start": str(slot.start_datetime),
                    "end": str(slot.end_datetime),
                    "slot": slot.id,
                    "teams": [fixture.home_team_id.id, fixture.away_team_id.id],
                    "resolved": bool(
                        fixture.home_team_id.club_id and fixture.away_team_id.club_id
                    ),
                    "opponents": sorted(
                        (
                            fixture.home_team_id.club_id | fixture.away_team_id.club_id
                        ).ids
                    ),
                    "rule": rule.id,
                    "required": rule.referee_required_count if rule else 0,
                }
            )
        return rows

    def _duty_geometry(self):
        self.ensure_one()
        if self.state == "published":
            return self._live_duty_geometry()
        return self._draft_duty_geometry()

    def _draft_duty_geometry(self):
        self.ensure_one()
        rows = []
        for assignment in self.assignment_ids.sorted("id"):
            fixture, slot = assignment.fixture_id, assignment.slot_id
            division = fixture.division_id
            rule = division.rule_set_id or division.competition_id.rule_set_id
            rows.append(
                {
                    "assignment": assignment.id,
                    "fixture": fixture.id,
                    "start": str(slot.start_datetime),
                    "end": str(slot.end_datetime),
                    "slot": slot.id,
                    "teams": [fixture.home_team_id.id, fixture.away_team_id.id],
                    "resolved": bool(
                        fixture.home_team_id.club_id and fixture.away_team_id.club_id
                    ),
                    "opponents": sorted(
                        (
                            fixture.home_team_id.club_id | fixture.away_team_id.club_id
                        ).ids
                    ),
                    "rule": rule.id,
                    "required": rule.referee_required_count if rule else 0,
                }
            )
        return rows

    def _duty_fingerprint(self, policy):
        return fingerprint(
            {
                "geometry": self._draft_duty_geometry(),
                "policy": policy,
                "capacities": self._club_duty_capacity_policy(),
                "pins": self._club_duty_pins(),
            }
        )

    @api.depends(
        "club_duty_policy",
        "club_duty_signature",
        "assignment_ids",
        "assignment_ids.slot_id.start_datetime",
        "assignment_ids.slot_id.end_datetime",
        "assignment_ids.fixture_id.home_team_id.club_id",
        "assignment_ids.fixture_id.away_team_id.club_id",
        "assignment_ids.fixture_id.division_id.rule_set_id.referee_required_count",
        "assignment_ids.fixture_id.division_id.competition_id.rule_set_id."
        "referee_required_count",
        "club_duty_pin_ids.club_id",
        "club_duty_pin_ids.fixture_id",
    )
    def _compute_club_duty_review(self):
        for schedule in self:
            schedule.club_duty_review_required = bool(
                schedule.club_duty_policy
                and schedule.club_duty_signature
                != schedule._duty_fingerprint(schedule.club_duty_policy)
            )

    def _duty_proposal(self, policy):
        self.ensure_one()
        geometry = self._duty_geometry()
        matches = self.env["federation.match"].search(
            [
                ("logical_fixture_id", "in", [row["fixture"] for row in geometry]),
                ("state", "!=", "cancelled"),
            ]
        )
        if self.state == "published":
            matches = matches.filtered(
                lambda match: match.id in [row["match"] for row in geometry]
            )
        all_duties = self.env["federation.match.club.referee.duty"].search(
            [("match_id", "in", matches.ids)]
        )
        duties = all_duties.filtered(lambda duty: duty.state != "rejected")
        officials = self.env["federation.match.referee"].search(
            [("match_id", "in", matches.ids), ("state", "!=", "cancelled")]
        )
        issues = []
        if not policy["preserve"] and (duties or officials):
            issues.append(
                _(
                    "Existing duties or officials must be preserved; use Resolve / "
                    "replace to change them."
                )
            )
        rows = []
        for row in geometry:
            count = policy["count"] or row["required"]
            if not 0 <= count <= len(ROLE_SELECTION):
                raise ValidationError(
                    _("Officials per match must be between zero and five.")
                )
            relevant = duties.filtered(
                lambda duty: duty.fixture_id.id == row["fixture"]
            )
            existing = set(relevant.mapped("role"))
            existing.update(
                officials.filtered(
                    lambda official: official.match_id.logical_fixture_id.id
                    == row["fixture"]
                ).mapped("role")
            )
            roles = [
                role for role, label in ROLE_SELECTION[:count] if role not in existing
            ]
            playing = set().union(
                *(
                    set(other["opponents"])
                    for other in geometry
                    if row["start"] < other["end"] and other["start"] < row["end"]
                )
            )
            for duty in relevant:
                if duty.club_id.id in row["opponents"] or (
                    policy["avoid"]
                    and not policy["fallback"]
                    and duty.club_id.id in playing
                ):
                    issues.append(
                        _(
                            "Existing club duty conflicts with fixture %s; resolve it "
                            "before applying."
                        )
                        % row["fixture"]
                    )
            rows.append(
                dict(row, roles=roles, existing_clubs=[d.club_id.id for d in relevant])
            )
        for row in rows:
            start = datetime.fromisoformat(row["start"])
            end = datetime.fromisoformat(row["end"])
            row["duration_minutes"] = max(0, int((end - start).total_seconds() // 60))
        proposal = allocate(
            rows,
            policy["avoid"],
            policy["fallback"],
            capacities=self._club_duty_capacity_policy(),
            pins=self._club_duty_pins(),
        )
        for row in proposal["rows"]:
            if all_duties.filtered(
                lambda duty: duty.state == "rejected"
                and duty.fixture_id.id == row["fixture"]
                and duty.club_id.id == row["club"]
                and duty.role in row["roles"]
            ):
                issues.append(
                    _(
                        "A rejected duty conflicts with this allocation. Use Resolve / "
                        "replace first."
                    )
                )
        proposal["issues"] += issues
        proposal.setdefault("issue_details", []).extend(
            {"code": "preserved_conflict", "message": issue} for issue in issues
        )
        proposal["signature"] = self._duty_fingerprint(policy)
        # Acceptance/nomination changes also invalidate an open review dialog.
        proposal["preserved"] = [
            dict(row, club=d.club_id.id, role=d.role, roles=[d.role], state=d.state)
            for row in geometry
            for d in duties
            if d.fixture_id.id == row["fixture"]
        ]
        proposal["review_signature"] = fingerprint(
            {
                "signature": proposal["signature"],
                "geometry": geometry,
                "duties": [
                    (d.id, d.state, d.club_id.id, d.role, d.nominated_player_id.id)
                    for d in all_duties
                ],
                "officials": [
                    (o.id, o.state, o.referee_id.id, o.role) for o in officials
                ],
            }
        )
        return proposal

    def action_review_club_duties(self):
        self._reviewable_duty_schedules()
        wizard = self.env["federation.schedule.club.duty.review"].create(
            {"schedule_ids": [fields.Command.set(self.ids)]}
        )
        if len(self) == 1 and self.club_duty_policy:
            policy = self.club_duty_policy
            wizard.write(
                {
                    "officials_per_match": policy["count"],
                    "avoid_playing": policy["avoid"],
                    "allow_fallback": policy["fallback"],
                    "preserve_existing": policy["preserve"],
                }
            )
        self.filtered(lambda s: s.state == "draft" and not s.club_duty_policy).write(
            {"club_duty_policy": wizard._policy(), "club_duty_signature": False}
        )
        return wizard.action_preview()


class ClubDutyReview(models.TransientModel):
    _name = "federation.schedule.club.duty.review"
    _description = "Review Draft Schedule Club Duties"

    schedule_ids = fields.Many2many("federation.schedule", required=True)
    officials_per_match = fields.Integer(
        default=0, help="Zero uses each division rule set."
    )
    avoid_playing = fields.Boolean(
        default=True, string="Avoid clubs playing at the same time"
    )
    allow_fallback = fields.Boolean(default=False, string="Allow playing-club fallback")
    preserve_existing = fields.Boolean(
        default=True, string="Preserve existing assignments"
    )
    preview = fields.Json(readonly=True)
    preview_html = fields.Html(readonly=True, sanitize=True)
    issue_count = fields.Integer(readonly=True)
    published_mode = fields.Boolean(compute="_compute_published_mode")

    @api.depends("schedule_ids.state")
    def _compute_published_mode(self):
        for wizard in self:
            wizard.published_mode = bool(
                wizard.schedule_ids
                and all(
                    schedule.state == "published" for schedule in wizard.schedule_ids
                )
            )

    def _policy(self):
        self.ensure_one()
        if not 0 <= self.officials_per_match <= len(ROLE_SELECTION):
            raise ValidationError(
                _("Officials per match must be between zero and five.")
            )
        return {
            "count": self.officials_per_match,
            "avoid": self.avoid_playing,
            "fallback": self.allow_fallback,
            "preserve": self.preserve_existing,
        }

    def _current(self):
        self.schedule_ids._reviewable_duty_schedules()
        policy = self._policy()
        return {str(s.id): s._duty_proposal(policy) for s in self.schedule_ids}

    def action_preview(self):
        self.ensure_one()
        preview = self._current()
        html, issues = [], 0
        for schedule in self.schedule_ids:
            proposal = preview[str(schedule.id)]
            issues += len(proposal["issues"])
            html.append(
                '<h4>%s</h4><table class="table"><tr><th>Fixture</th>'
                "<th>Time</th><th>Club</th><th>Roles</th>"
                "<th>Fallback</th></tr>" % escape(schedule.display_name)
            )
            for row in proposal["rows"]:
                fixture = self.env["federation.fixture"].browse(row["fixture"])
                club = self.env["federation.club"].browse(row["club"])
                html.append(
                    "<tr>%s</tr>"
                    % "".join(
                        "<td>%s</td>" % escape(str(value))
                        for value in (
                            fixture.display_name,
                            fields.Datetime.context_timestamp(
                                self, fields.Datetime.to_datetime(row["start"])
                            ).strftime("%Y-%m-%d %H:%M %Z"),
                            club.display_name,
                            ", ".join(
                                dict(ROLE_SELECTION)[role] for role in row["roles"]
                            ),
                            _("Yes") if row["fallback"] else _("No"),
                        )
                    )
                )
            for duty in proposal["preserved"]:
                html.append(
                    "<tr>%s</tr>"
                    % "".join(
                        "<td>%s</td>" % escape(str(value))
                        for value in (
                            self.env["federation.fixture"]
                            .browse(duty["fixture"])
                            .display_name,
                            _("Preserved"),
                            self.env["federation.club"]
                            .browse(duty["club"])
                            .display_name,
                            duty["role"],
                            duty["state"],
                        )
                    )
                )
            html.append(
                "</table><p>%s</p><ul>" % _("Workload totals (roles and duty minutes)")
            )
            for club_id, count in sorted(proposal["load"].items()):
                html.append(
                    "<li>%s: %s</li>"
                    % (
                        escape(
                            self.env["federation.club"]
                            .browse(int(club_id))
                            .display_name
                        ),
                        _("%(roles)s roles / %(minutes)s minutes")
                        % {
                            "roles": count,
                            "minutes": proposal.get("minute_load", {}).get(
                                str(club_id), 0
                            ),
                        },
                    )
                )
            html.append("</ul>")
            if not proposal["rows"] and not proposal["preserved"]:
                html.append(
                    "<p>%s</p>"
                    % _(
                        "No new club duties: the rule set requires none, or existing "
                        "officials cover the roles."
                    )
                )
            html.extend(
                '<p class="text-danger">%s</p>' % escape(issue)
                for issue in proposal["issues"]
            )
        self.write(
            {"preview": preview, "preview_html": "".join(html), "issue_count": issues}
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_apply(self):
        self.ensure_one()
        # Serialize competing allocation dialogs for the same match day.
        self.schedule_ids._reviewable_duty_schedules()
        self.env.cr.execute(
            "SELECT id FROM federation_matchday "
            "WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
            [sorted(self.schedule_ids.mapped("matchday_id").ids)],
        )
        self.env.invalidate_all()
        current = self._current()
        if not self.preview or current != self.preview:
            raise UserError(
                _(
                    "Schedule, policy or assignments changed. Refresh the preview "
                    "before applying."
                )
            )
        if any(proposal["issues"] for proposal in current.values()):
            raise UserError(
                _("Resolve all club-duty allocation issues before applying.")
            )
        for schedule in self.schedule_ids:
            proposal = current[str(schedule.id)]
            if schedule.state == "published":
                self._apply_live_duties(schedule, proposal)
                continue
            schedule.write(
                {
                    "club_duty_policy": self._policy(),
                    "club_duty_plan": proposal["rows"] + proposal["preserved"],
                    "club_duty_signature": proposal["signature"],
                }
            )
        return {
            "type": "ir.actions.act_window",
            "res_model": "federation.schedule",
            "view_mode": "list,form",
            "domain": [("id", "in", self.schedule_ids.ids)],
        }

    def _apply_live_duties(self, schedule, proposal):
        """Add only reviewed missing roles; never alter the published schedule."""
        schedule._live_duty_publication()
        Duty = self.env["federation.match.club.referee.duty"]
        values = [
            {
                "match_id": row["match"],
                "club_id": row["club"],
                "role": role,
                "allocation_snapshot": row,
            }
            for row in proposal["rows"]
            for role in row["roles"]
        ]
        created = Duty.create(values) if values else Duty.browse([])
        created.action_open()
        for duty in created:
            duty.message_post(
                body=_(
                    "Club duty allocated after review of the current published "
                    "schedule."
                )
            )


class MatchdayClubDutyPlanning(models.Model):
    _inherit = "federation.matchday"

    def action_plan_current_club_duties(self):
        self.ensure_one()
        publication = self.current_publication_id
        if not publication or publication.state != "live":
            raise UserError(
                _("Publish a schedule first, or use Review club duties on its draft.")
            )
        return publication.schedule_id.action_review_club_duties()


class CompetitionScheduleClubDuties(models.TransientModel):
    _inherit = "federation.competition.schedule.wizard"

    auto_club_duties = fields.Boolean(
        string="Automatically plan club duties", default=False
    )

    def action_apply(self):
        self.ensure_one()
        result = super().action_apply()
        if not self.auto_club_duties:
            return result
        schedules = self.env["federation.schedule"].search(
            [("matchday_id", "in", self.matchday_ids.ids), ("state", "=", "draft")]
        )
        if not schedules:
            raise UserError(
                _("No draft schedules were generated for club-duty review.")
            )
        schedules.write(
            {
                "club_duty_policy": {
                    "count": 0,
                    "avoid": True,
                    "fallback": False,
                    "preserve": True,
                },
                "club_duty_plan": False,
                "club_duty_signature": False,
            }
        )
        return schedules.action_review_club_duties()


class PlannedPublicationClubDuties(models.AbstractModel):
    _inherit = "federation.schedule.approval.commands"

    def publish(self, schedule_id, reason=False, expected_publication_id=None):
        schedule = self.env["federation.schedule"].browse(schedule_id)
        if schedule.club_duty_policy:
            if schedule.club_duty_signature != schedule._duty_fingerprint(
                schedule.club_duty_policy
            ):
                raise UserError(
                    _("Club duties need review because the schedule or teams changed.")
                )
            proposal = schedule._duty_proposal(schedule.club_duty_policy)
            if proposal["issues"]:
                raise UserError("\n".join(proposal["issues"]))
            planned_roles = {
                (row["fixture"], role)
                for row in schedule.club_duty_plan or []
                for role in row["roles"]
            }
            required_roles = {
                (row["fixture"], role)
                for row in proposal["rows"]
                for role in row["roles"]
            }
            if not required_roles <= planned_roles:
                raise UserError(
                    _("Existing coverage changed. Review club duties again.")
                )
        return super().publish(
            schedule_id, reason=reason, expected_publication_id=expected_publication_id
        )

    def _ensure_club_duties(self, matches):
        matches = matches.sudo().filtered(
            lambda m: m.logical_fixture_id
            and m.schedule_publication_id
            and m.state != "cancelled"
        )
        planned = matches.browse([])
        created = self.env["federation.match.club.referee.duty"].sudo()
        for match in matches:
            schedule = match.schedule_publication_id.schedule_id
            if not schedule.club_duty_policy:
                continue
            planned |= match
            if schedule.club_duty_signature != schedule._duty_fingerprint(
                schedule.club_duty_policy
            ):
                raise UserError(
                    _(
                        "Club-duty plan is stale. Review the draft amendment before "
                        "publishing."
                    )
                )
            existing = self.env["federation.match.club.referee.duty"].search(
                [("match_id", "=", match.id), ("state", "!=", "rejected")]
            )
            officials = self.env["federation.match.referee"].search(
                [("match_id", "=", match.id), ("state", "!=", "cancelled")]
            )
            covered = set(existing.mapped("role")) | set(officials.mapped("role"))
            values = []
            for row in schedule.club_duty_plan or []:
                if row["fixture"] != match.logical_fixture_id.id:
                    continue
                values += [
                    {"match_id": match.id, "club_id": row["club"], "role": role}
                    for role in row["roles"]
                    if role not in covered
                ]
            new_duties = created.create(values) if values else created.browse([])
            new_duties.action_open()
            existing.filtered(lambda duty: duty.state == "draft").action_open()
            created |= new_duties
        return created | super()._ensure_club_duties(matches - planned)


class PlannedDutyScheduleReview(models.Model):
    _inherit = "federation.match.club.referee.duty"

    allocation_snapshot = fields.Json(readonly=True, copy=False)

    planning_review_required = fields.Boolean(
        compute="_compute_planning_review_required"
    )

    def write(self, values):
        if "allocation_snapshot" in values and self:
            raise ValidationError(
                _("The reviewed club-duty allocation snapshot is immutable.")
            )
        return super().write(values)

    @api.depends(
        "allocation_snapshot",
        "match_id.schedule_publication_id.schedule_id.club_duty_plan",
        "match_id.operational_slot_id.start_datetime",
        "match_id.operational_slot_id.end_datetime",
        "match_id.published_slot_id.start_datetime",
        "match_id.published_slot_id.end_datetime",
        "match_id.logical_fixture_id.home_team_id",
        "match_id.logical_fixture_id.away_team_id",
        "match_id.logical_fixture_id.home_team_id.club_id",
        "match_id.logical_fixture_id.away_team_id.club_id",
        "club_id",
        "role",
    )
    def _compute_planning_review_required(self):
        for duty in self:
            match = duty.match_id
            schedule = match.schedule_publication_id.schedule_id
            slot = match.operational_slot_id or match.published_slot_id
            rows = [
                row
                for row in schedule.club_duty_plan or []
                if row["fixture"] == duty.fixture_id.id
                and row["club"] == duty.club_id.id
                and duty.role in row["roles"]
            ]
            if duty.allocation_snapshot:
                rows = [duty.allocation_snapshot]
            opponents = sorted(
                (
                    match.logical_fixture_id.home_team_id.club_id
                    | match.logical_fixture_id.away_team_id.club_id
                ).ids
            )
            duty.planning_review_required = bool(
                rows
                and any(
                    row["start"] != str(slot.start_datetime)
                    or row["end"] != str(slot.end_datetime)
                    or row["opponents"] != opponents
                    or row.get(
                        "teams",
                        [
                            match.logical_fixture_id.home_team_id.id,
                            match.logical_fixture_id.away_team_id.id,
                        ],
                    )
                    != [
                        match.logical_fixture_id.home_team_id.id,
                        match.logical_fixture_id.away_team_id.id,
                    ]
                    for row in rows
                )
            )
