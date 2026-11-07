from html import escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionScheduleWizard(models.TransientModel):
    _name = "federation.competition.schedule.wizard"
    _description = "Generate Complete Competition Schedule"

    edition_id = fields.Many2one("federation.competition.edition", required=True)
    matchday_ids = fields.Many2many(
        "federation.matchday",
        relation="federation_comp_schedule_wizard_matchday_rel",
        column1="wizard_id",
        column2="matchday_id",
        required=True,
        string="Game Days",
        domain="[('edition_id', '=', edition_id)]",
    )
    structure_ids = fields.Many2many(
        "federation.competition.structure",
        relation="federation_comp_schedule_wizard_structure_rel",
        column1="wizard_id",
        column2="structure_id",
        required=True,
        string="Competition Formats",
        domain="[('edition_id', '=', edition_id), ('state', 'in', ('draft', 'generated', 'frozen'))]",
    )
    stage_ids = fields.Many2many(
        "federation.structure.stage",
        relation="federation_comp_schedule_wizard_stage_rel",
        column1="wizard_id",
        column2="stage_id",
        string="Competition Stages",
        domain="[('structure_id', 'in', structure_ids)]",
        help="Limit generation to these stages. Leave empty only when every stage in the selected formats belongs in this planning run.",
    )
    stage_window_ids = fields.One2many(
        "federation.competition.schedule.stage.window",
        "wizard_id",
        string="Stage game days",
        help="Competitions with several stages: choose the game days of each "
        "stage. Leave a stage empty to let planning use any day after the "
        "stage it depends on.",
    )
    has_stage_windows = fields.Boolean(compute="_compute_has_stage_windows")
    mode = fields.Selection(
        [
            ("fill", "Fill Missing Planning"),
            ("replace_auto", "Replace Automatic Planning"),
            ("rebuild", "Rebuild Unpublished Planning"),
        ],
        default="fill",
        required=True,
    )
    rebuild_reason = fields.Text()
    generate_missing_fixtures = fields.Boolean(default=True)
    preferred_rest_minutes = fields.Integer(default=40, required=True)
    preview_ready = fields.Boolean(readonly=True)
    preview_signature = fields.Char(readonly=True)
    feasibility_report = fields.Json(readonly=True)
    quality_report = fields.Json(readonly=True)
    rest_shortfall_html = fields.Html(readonly=True, sanitize=True)
    blocking_issue_count = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)
    included_fixture_count = fields.Integer(readonly=True)
    excluded_fixture_count = fields.Integer(readonly=True)
    selected_stage_count = fields.Integer(readonly=True)
    allocation_report = fields.Json(readonly=True)
    allocation_report_html = fields.Html(
        string="Allocation by game day",
        compute="_compute_readable_reports",
        readonly=True,
        sanitize=True,
    )
    feasibility_report_html = fields.Html(
        string="Feasibility details",
        compute="_compute_readable_reports",
        readonly=True,
        sanitize=True,
    )
    quality_report_html = fields.Html(
        string="Quality details",
        compute="_compute_readable_reports",
        readonly=True,
        sanitize=True,
    )

    @api.depends(
        "allocation_report",
        "feasibility_report",
        "quality_report",
        "matchday_ids",
    )
    def _compute_readable_reports(self):
        for wizard in self:
            wizard.allocation_report_html = wizard._allocation_report_html()
            wizard.feasibility_report_html = wizard._feasibility_report_html()
            wizard.quality_report_html = wizard._quality_report_html()

    def _report_day_name(self, matchday_id):
        day = self.matchday_ids.filtered(lambda item: item.id == int(matchday_id))[:1]
        return day.display_name if day else _("Game Day %(id)s", id=matchday_id)

    def _allocation_report_html(self):
        rows = self.allocation_report or []
        if not rows:
            return _("<p>Preview the plan to see the allocation by game day.</p>")
        body = "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                escape(self._report_day_name(row.get("matchday_id", 0))),
                escape(str(row.get("date", ""))),
                escape(str(row.get("included_fixture_count", 0))),
                escape(str(row.get("capacity", 0))),
                escape(str(row.get("remaining_capacity", 0))),
            )
            for row in rows
        )
        return (
            "<div class='table-responsive'><table class='table table-sm mb-0'>"
            "<thead><tr><th>Game day</th><th>Date</th><th>Fixtures planned</th>"
            "<th>Available slots</th><th>Slots remaining</th></tr></thead>"
            "<tbody>%s</tbody></table></div>" % body
        )

    def _feasibility_report_html(self):
        report = self.feasibility_report or {}
        if not report:
            return _("<p>Preview the plan to see fixture and capacity checks.</p>")
        labels = (
            ("fixture_count", _("Playable fixtures")),
            ("included_fixture_count", _("Fixtures included")),
            ("excluded_fixture_count", _("Fixtures outside this run")),
            ("deferred_fixture_count", _("Deferred fixtures")),
            ("selected_stage_count", _("Competition stages")),
            ("available_slot_count", _("Available match slots")),
            ("capacity_surplus", _("Slots remaining after allocation")),
        )
        summary = "".join(
            "<li><strong>%s:</strong> %s</li>"
            % (escape(label), escape(str(report.get(key, 0))))
            for key, label in labels
        )
        day_rows = "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                escape(self._report_day_name(row.get("matchday_id", 0))),
                escape(str(row.get("date", ""))),
                escape(str(row.get("capacity", 0))),
                escape(str(row.get("blocked", 0))),
            )
            for row in report.get("game_days", [])
        )
        day_table = (
            "<table class='table table-sm'><thead><tr><th>Game day</th><th>Date</th>"
            "<th>Available slots</th><th>Blocked slots</th></tr></thead>"
            "<tbody>%s</tbody></table>" % day_rows
            if day_rows
            else ""
        )
        errors = report.get("errors", [])
        issue_list = (
            "<h4>Blocking issues</h4><ul>%s</ul>"
            % "".join("<li>%s</li>" % escape(str(item)) for item in errors)
            if errors
            else "<p class='text-success'>No blocking issues.</p>"
        )
        return "<ul>%s</ul>%s%s" % (summary, day_table, issue_list)

    def _quality_report_html(self):
        report = self.quality_report or {}
        if not report:
            return _("<p>Preview the plan to see quality warnings.</p>")
        counts = report.get("planned_fixture_counts", {})
        remaining = report.get("remaining_capacity", {})
        day_ids = sorted(set(counts) | set(remaining), key=lambda value: int(value))
        rows = "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                escape(self._report_day_name(day_id)),
                escape(str(counts.get(day_id, counts.get(str(day_id), 0)))),
                escape(str(remaining.get(day_id, remaining.get(str(day_id), 0)))),
            )
            for day_id in day_ids
        )
        day_table = (
            "<table class='table table-sm'><thead><tr><th>Game day</th>"
            "<th>Fixtures planned</th><th>Slots remaining</th></tr></thead>"
            "<tbody>%s</tbody></table>" % rows
            if rows
            else ""
        )
        warnings = report.get("warnings", [])
        warning_list = (
            "<h4>Warnings</h4><ul>%s</ul>"
            % "".join("<li>%s</li>" % escape(str(item)) for item in warnings)
            if warnings
            else "<p class='text-success'>No quality warnings.</p>"
        )
        repeat_count = report.get("teams_with_multiple_same_day_matches", 0)
        return (
            "<p><strong>Teams scheduled more than once on a game day:</strong> %s</p>%s%s"
            % (escape(str(repeat_count)), day_table, warning_list)
        )

    @api.model
    def _planning_stages(self, stages):
        """Include ready stages and pre-generated schedulable placeholders."""
        return stages.filtered(
            lambda stage: stage.graph_state in ("ready", "active")
            or (
                stage.graph_state == "waiting"
                and any(
                    fixture._is_schedulable() for fixture in stage.stage_fixture_ids
                )
            )
        )

    @api.depends("stage_window_ids")
    def _compute_has_stage_windows(self):
        for wizard in self:
            wizard.has_stage_windows = bool(wizard.stage_window_ids)

    def _stage_window_commands(self):
        """One line per stage of every multi-stage format in scope."""
        stages = self.structure_ids.mapped("stage_ids").filtered(
            lambda stage: len(stage.structure_id.stage_ids) > 1
        )
        if self.stage_ids:
            stages &= self.stage_ids
        depths = stages._planning_depths() if stages else {}
        ordered = stages.sorted(
            lambda stage: (
                stage.structure_id.division_id.name or "",
                depths.get(stage.id, 0),
                stage.sequence,
                stage.id,
            )
        )
        return [fields.Command.clear()] + [
            fields.Command.create(
                {
                    "stage_id": stage.id,
                    "matchday_ids": [fields.Command.set(stage.matchday_ids.ids)],
                }
            )
            for stage in ordered
        ]

    def _sync_stage_windows(self):
        """Store the chosen stage game days on the stages themselves."""
        for line in self.stage_window_ids:
            if set(line.matchday_ids.ids) != set(line.stage_id.matchday_ids.ids):
                line.stage_id.check_access("read")
                line.stage_id.sudo().matchday_ids = [
                    fields.Command.set(line.matchday_ids.ids)
                ]

    @api.onchange("edition_id")
    def _onchange_edition_id(self):
        if not self.edition_id:
            self.matchday_ids = False
            self.structure_ids = False
            return
        self.matchday_ids = self.env["federation.matchday"].search(
            [
                ("edition_id", "=", self.edition_id.id),
                ("state", "in", ("draft", "capacity_ready")),
            ],
            order="date,id",
        )
        candidates = self.env["federation.competition.structure"].search(
            [
                ("edition_id", "=", self.edition_id.id),
                ("state", "in", ("draft", "generated", "frozen")),
            ],
            order="division_id,version desc,id desc",
        )
        latest = self.env["federation.competition.structure"]
        seen = set()
        for structure in candidates:
            if structure.division_id.id not in seen:
                latest |= structure
                seen.add(structure.division_id.id)
        self.structure_ids = latest
        self.stage_ids = self._planning_stages(latest.mapped("stage_ids"))
        self.stage_window_ids = self._stage_window_commands()

    @api.onchange("structure_ids")
    def _onchange_structure_ids(self):
        allowed = self.structure_ids.mapped("stage_ids")
        self.stage_ids = self.stage_ids & allowed
        if not self.stage_ids and allowed:
            self.stage_ids = self._planning_stages(allowed) or allowed
        self.stage_window_ids = self._stage_window_commands()

    @api.constrains("preferred_rest_minutes", "mode", "rebuild_reason")
    def _check_configuration(self):
        for wizard in self:
            if wizard.preferred_rest_minutes < 0:
                raise ValidationError(_("Preferred rest cannot be negative."))
            if wizard.mode == "rebuild" and not (wizard.rebuild_reason or "").strip():
                raise ValidationError(_("Explain why unpublished planning is rebuilt."))

    def action_preview(self):
        self.ensure_one()
        self._sync_stage_windows()
        proposal = self._build_proposal()
        self.write(
            {
                "preview_ready": True,
                "preview_signature": self._input_signature(),
                "feasibility_report": proposal["feasibility"],
                "quality_report": proposal["quality"],
                "blocking_issue_count": len(proposal["errors"]),
                "warning_count": len(proposal["warnings"]),
                "included_fixture_count": proposal["feasibility"][
                    "included_fixture_count"
                ],
                "excluded_fixture_count": proposal["feasibility"][
                    "excluded_fixture_count"
                ],
                "selected_stage_count": proposal["feasibility"]["selected_stage_count"],
                "allocation_report": proposal["allocation_report"],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Plan Competition"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": dict(self.env.context),
        }

    def action_generate(self):
        """Check and generate in one step.

        The proposal is validated exactly like Preview. When nothing blocks,
        the schedules are generated immediately; otherwise the wizard stays
        open with the checks shown so the operator can fix the input.
        """
        self.ensure_one()
        self.action_preview()
        rest_shortfalls = (self.quality_report or {}).get("rest_shortfalls") or []
        self.rest_shortfall_html = (
            "<ul class='mb-0'>%s</ul>"
            % "".join("<li>%s</li>" % escape(str(item)) for item in rest_shortfalls)
            if rest_shortfalls
            else False
        )
        stop_for_rest = rest_shortfalls and not self.env.context.get(
            "accept_short_rest"
        )
        if self.blocking_issue_count or stop_for_rest:
            return {
                "type": "ir.actions.act_window",
                "name": _("Plan Competition"),
                "res_model": self._name,
                "res_id": self.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "new",
                "context": dict(self.env.context),
            }
        return self.action_apply()

    def action_apply(self):
        self.ensure_one()
        if not self.preview_ready:
            raise ValidationError(
                _("Preview the competition schedule before applying it.")
            )
        if self.preview_signature != self._input_signature():
            raise ValidationError(
                _("Competition planning changed after preview. Preview again.")
            )
        proposal = self._build_proposal()
        if proposal["errors"]:
            raise ValidationError("\n".join(proposal["errors"]))
        self._prepare_existing_planning()
        self._prepare_structures()
        proposal = self._build_proposal(require_generated=True)
        if proposal["errors"]:
            raise ValidationError("\n".join(proposal["errors"]))
        schedules = self.env["federation.schedule"]
        for day in self.matchday_ids.sorted(lambda item: (item.date, item.id)):
            fixture_ids = proposal["distribution"]["assignments"].get(day.id, [])
            if not fixture_ids:
                continue
            self._generate_day_slots(day)
            fixtures = self.env["federation.fixture"].browse(fixture_ids)
            self._create_allocations(day, fixtures)
            day.action_capacity_ready()
            schedule = self._schedule_for_day(day, fixtures)
            self.env["federation.schedule.auto.wizard"].create(
                {
                    "schedule_id": schedule.id,
                    "preferred_rest_minutes": self.preferred_rest_minutes,
                }
            ).action_apply()
            schedule.invalidate_recordset()
            if schedule.unassigned_fixture_ids:
                raise ValidationError(
                    _("%s still has unscheduled fixtures.") % day.display_name
                )
            schedules |= schedule
        if self.env.context.get("return_to_competition_workspace") and hasattr(
            self.edition_id, "action_open_competition_planner"
        ):
            return self.edition_id.action_open_competition_planner()
        return {
            "type": "ir.actions.act_window",
            "res_model": "federation.schedule",
            "view_mode": "list,form",
            "domain": [("id", "in", schedules.ids)],
        }

    def _prepare_existing_planning(self):
        if self.mode == "fill":
            return
        for day in self.matchday_ids:
            schedules = self.env["federation.schedule"].search(
                [("matchday_id", "=", day.id)]
            )
            if self.mode == "replace_auto":
                schedules.mapped("assignment_ids").filtered(
                    lambda item: item.method == "automatic"
                ).unlink()
            else:
                schedules.unlink()
                day.allocation_ids.unlink()
                day.slot_ids.unlink()
                day.state = "draft"

    def _prepare_structures(self):
        for structure in self.structure_ids:
            if structure.state == "draft":
                structure.action_generate()
            if structure.state == "generated":
                structure.action_freeze()

    def _generate_day_slots(self, day):
        if day.slot_ids and self.mode in ("fill", "replace_auto"):
            return
        self.env["federation.slot.generator"].generate_plan(
            day,
            day.planning_court_ids,
            day.default_day_start_hour,
            day.default_day_end_hour,
            day.default_slot_duration_minutes,
            noon_pause=day.default_noon_pause,
            noon_pause_minutes=day.default_noon_pause_minutes,
            replace_existing=bool(day.slot_ids),
        )

    def _create_allocations(self, day, fixtures):
        for structure in fixtures.mapped("structure_id"):
            allocated = fixtures.filtered(
                lambda fixture: fixture.structure_id == structure
            )
            current = day.allocation_ids.filtered(
                lambda item: item.structure_id == structure and item.manual_only
            )[:1]
            if current:
                current.manual_fixture_ids |= allocated
            else:
                self.env["federation.matchday.allocation"].create(
                    {
                        "matchday_id": day.id,
                        "structure_id": structure.id,
                        "manual_fixture_ids": [(6, 0, allocated.ids)],
                        "manual_only": True,
                    }
                )

    def _schedule_for_day(self, day, fixtures):
        schedule = self.env["federation.schedule"].search(
            [
                ("matchday_id", "=", day.id),
                ("state", "in", ("draft", "changes_requested")),
            ],
            limit=1,
        )
        if schedule and schedule.preferred_rest_minutes != self.preferred_rest_minutes:
            # The schedule is planned and later checked with this rest; a
            # reused draft must not keep the value of an earlier generation.
            schedule.preferred_rest_minutes = self.preferred_rest_minutes
        return schedule or self.env["federation.schedule"].create(
            {
                "name": _("%s schedule") % day.display_name,
                "edition_id": self.edition_id.id,
                "structure_id": fixtures[:1].structure_id.id,
                "matchday_id": day.id,
                "preferred_rest_minutes": self.preferred_rest_minutes,
            }
        )


class FederationCompetitionScheduleStageWindow(models.TransientModel):
    _name = "federation.competition.schedule.stage.window"
    _description = "Game Days of a Competition Stage"
    _order = "id"

    wizard_id = fields.Many2one(
        "federation.competition.schedule.wizard", required=True, ondelete="cascade"
    )
    stage_id = fields.Many2one(
        "federation.structure.stage", required=True, readonly=True, ondelete="cascade"
    )
    division_id = fields.Many2one(
        related="stage_id.structure_id.division_id", string="Division"
    )
    source_summary = fields.Char(string="Teams from", compute="_compute_source_summary")
    edition_id = fields.Many2one(related="wizard_id.edition_id")
    matchday_ids = fields.Many2many(
        "federation.matchday",
        "federation_comp_schedule_stage_window_matchday_rel",
        "window_id",
        "matchday_id",
        string="Game days",
        domain="[('edition_id', '=', edition_id)]",
    )

    @api.depends("stage_id")
    def _compute_source_summary(self):
        for line in self:
            sources = line.stage_id._planning_source_stages()
            line.source_summary = (
                ", ".join(sources.mapped("name")) if sources else _("Registered teams")
            )


class FederationCompetitionScheduleWizardGuidance(models.TransientModel):
    """Plain-language guidance for the competition schedule wizard.

    The wizard keeps its planning behaviour; this extension only explains the
    current check result, the next step and what a rerun mode changes.
    """

    _inherit = "federation.competition.schedule.wizard"

    guidance_status_html = fields.Html(
        string="Status",
        compute="_compute_guidance_status_html",
        readonly=True,
    )
    mode_impact_html = fields.Html(
        string="What this does",
        compute="_compute_mode_impact_html",
        readonly=True,
    )
    existing_slot_count = fields.Integer(
        string="Existing court times",
        compute="_compute_existing_planning",
        help="Court times already created on the selected game days.",
    )
    existing_draft_schedule_count = fields.Integer(
        string="Unpublished schedules",
        compute="_compute_existing_planning",
        help="Draft or change-requested schedules on the selected game days.",
    )

    @api.depends("matchday_ids", "matchday_ids.slot_ids")
    def _compute_existing_planning(self):
        Schedule = self.env["federation.schedule"]
        for wizard in self:
            days = wizard.matchday_ids
            day_ids = [day_id for day_id in days._origin.ids if day_id]
            wizard.existing_slot_count = sum(len(day.slot_ids) for day in days)
            wizard.existing_draft_schedule_count = (
                Schedule.search_count(
                    [
                        ("matchday_id", "in", day_ids),
                        ("state", "in", ("draft", "changes_requested")),
                    ]
                )
                if day_ids
                else 0
            )

    @api.depends(
        "matchday_ids",
        "preview_ready",
        "blocking_issue_count",
        "warning_count",
        "included_fixture_count",
        "excluded_fixture_count",
        "rest_shortfall_html",
    )
    def _compute_guidance_status_html(self):
        for wizard in self:
            wizard.guidance_status_html = wizard._guidance_status_markup()

    @api.depends(
        "mode", "existing_slot_count", "existing_draft_schedule_count"
    )
    def _compute_mode_impact_html(self):
        for wizard in self:
            wizard.mode_impact_html = wizard._mode_impact_markup()

    def _guidance_status(self):
        """Return ``(tone, title, body)`` for the current wizard state."""
        self.ensure_one()
        if not self.matchday_ids:
            return (
                "warning",
                _("Choose the game days to plan"),
                _(
                    "Matches are only placed on the game days you select. "
                    "Select at least one game day."
                ),
            )
        if not self.preview_ready:
            return (
                "info",
                _("Ready to check and generate"),
                _(
                    "Generate schedule first checks capacity and conflicts on "
                    "every selected game day. If something must be fixed, the "
                    "problems are listed here with the way to solve them."
                ),
            )
        if self.blocking_issue_count:
            return (
                "danger",
                _(
                    "%(count)s problem(s) must be fixed first",
                    count=self.blocking_issue_count,
                ),
                _(
                    "Nothing has been planned yet. Open Feasibility below to see "
                    "each problem and how to fix it, then generate again."
                ),
            )
        if self.warning_count or self.rest_shortfall_html:
            return (
                "warning",
                _(
                    "Can be generated, with %(count)s preference warning(s)",
                    count=self.warning_count,
                ),
                _(
                    "Every rule that must hold is met, but some preferences, "
                    "such as rest between matches, cannot all be met. Change the "
                    "input and generate again, or generate anyway and accept the "
                    "short rest when you publish."
                ),
            )
        return (
            "success",
            _("Ready to generate"),
            _("All checks passed. Generate the schedule, then review it."),
        )

    def _guidance_status_markup(self):
        self.ensure_one()
        tone, title, body = self._guidance_status()
        facts = [(_("Game days"), len(self.matchday_ids))]
        if self.matchday_ids and self.preview_ready:
            facts += [
                (_("Matches included"), self.included_fixture_count),
                (_("Matches left out"), self.excluded_fixture_count),
                (_("Must fix"), self.blocking_issue_count),
                (_("Could improve"), self.warning_count),
            ]
        fact_html = "".join(
            '<span class="me-4"><span class="text-muted">%s</span> <strong>%s</strong></span>'
            % (escape(str(label)), escape(str(value or 0)))
            for label, value in facts
        )
        return (
            '<div class="alert alert-%(tone)s mb-2" role="status">'
            "<p class=\"mb-1\"><strong>%(title)s</strong></p>"
            '<p class="mb-1">%(body)s</p>'
            '<p class="mb-0 small">%(facts)s</p>'
            "</div>"
        ) % {
            "tone": tone,
            "title": escape(str(title)),
            "body": escape(str(body)),
            "facts": fact_html,
        }

    def _mode_impact_markup(self):
        self.ensure_one()
        if self.mode == "replace_auto":
            tone = "warning"
            text = _(
                "Matches the scheduler placed earlier are removed and planned "
                "again. Matches you placed by hand stay where they are, and "
                "existing court times are kept."
            )
        elif self.mode == "rebuild":
            tone = "danger"
            text = _(
                "Deletes the unpublished planning of the selected game days "
                "(%(slots)s court time(s) and %(schedules)s unpublished "
                "schedule(s)), including matches placed by hand, and builds it "
                "again from the game-day settings. Game days that are in review, "
                "published, open or closed are never rebuilt. Explain why in the "
                "reason.",
                slots=self.existing_slot_count,
                schedules=self.existing_draft_schedule_count,
            )
        else:
            tone = "info"
            text = _(
                "Keeps everything already planned. Only matches that do not have "
                "a court and time yet are added."
            )
        return '<div class="alert alert-%s mb-0 py-2" role="note">%s</div>' % (
            tone,
            escape(str(text)),
        )
