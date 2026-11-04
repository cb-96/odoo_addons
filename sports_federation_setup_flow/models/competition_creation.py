from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationCreateCompetitionWizardJourney(models.TransientModel):
    _inherit = "federation.create.competition.wizard"

    creation_draft_id = fields.Many2one("federation.competition.creation.draft", readonly=True)
    # Only name, type, dates and divisions are asked up front.  The parent
    # competition and the season are derived when left empty.
    competition_id = fields.Many2one(required=False)
    season_id = fields.Many2one(required=False)

    _COMPETITION_TYPE_BY_PRESET = {
        "league": "league",
        "tournament_day": "tournament",
        "cup": "cup",
        "custom": "other",
    }

    def _derive_competition(self):
        """Reuse a competition with the same name or create one."""
        self.ensure_one()
        Competition = self.env["federation.competition"]
        competition = Competition.search([("name", "=ilike", self.name)], limit=1)
        if competition:
            return competition
        return Competition.create(
            {
                "name": self.name,
                "competition_type": self._COMPETITION_TYPE_BY_PRESET.get(
                    self.setup_template or "league", "league"
                ),
                "rule_set_id": self.rule_set_id.id,
            }
        )

    def _derive_season(self):
        """Use the season that contains the start date, or create it."""
        self.ensure_one()
        Season = self.env["federation.season"]
        season = Season.search(
            [
                ("date_start", "<=", self.date_start),
                ("date_end", ">=", self.date_start),
                ("state", "!=", "cancelled"),
            ],
            order="state desc,date_start desc",
            limit=1,
        )
        if season:
            return season
        # Sport seasons run from July to June.
        first_year = self.date_start.year if self.date_start.month >= 7 else self.date_start.year - 1
        start = fields.Date.to_date("%s-07-01" % first_year)
        end = fields.Date.to_date("%s-06-30" % (first_year + 1))
        if self.date_end and self.date_end > end:
            end = self.date_end
        return Season.create(
            {
                "name": "%s-%s" % (first_year, first_year + 1),
                "date_start": start,
                "date_end": end,
            }
        )

    def action_save_creation_draft(self):
        self.ensure_one()
        names = ["setup_template", "competition_id", "name", "season_id", "date_start", "date_end", "rule_set_id", "registration_open", "registration_close", "workflow_mode", "default_venue_id", "default_format_type", "default_start_hour", "default_end_hour", "default_slot_duration_minutes", "show_additional_settings"]
        payload = self.read(names)[0]
        payload.pop("id", None)
        for name in names:
            field = self._fields[name]
            value = payload[name]
            if field.type == "many2one": payload[name] = value[0] if value else False
            elif field.type == "date": payload[name] = fields.Date.to_string(fields.Date.to_date(value)) if value else False
            elif field.type == "datetime": payload[name] = fields.Datetime.to_string(fields.Datetime.to_datetime(value)) if value else False
        for name, columns in [("division_line_ids", ["name", "code", "category", "gender", "tournament_type"]), ("role_line_ids", ["role", "user_id"])]:
            commands = []
            for row in self[name].read(columns):
                row.pop("id", None)
                if "user_id" in row: row["user_id"] = row["user_id"][0] if row["user_id"] else False
                commands.append((0, 0, row))
            payload[name] = commands
        values = {"name": self.name or _("Competition draft"), "payload": payload}
        if self.creation_draft_id:
            self.creation_draft_id.write(values)
        else:
            self.creation_draft_id = self.env["federation.competition.creation.draft"].create(values)
        return {"type": "ir.actions.act_window_close"}

    show_additional_settings = fields.Boolean(string="Additional settings", default=False)

    setup_template = fields.Selection(
        selection_add=[("custom", "Custom")],
        string="Competition Type",
        ondelete={"custom": "set default"},
    )
    workflow_mode = fields.Selection(
        [
            ("simple", "Streamlined"),
            ("controlled", "Independent Review"),
            ("custom", "Advanced / Custom"),
        ],
        default="simple",
        required=True,
        string="Workflow",
    )
    workflow_summary = fields.Text(compute="_compute_workflow_summary", readonly=True)
    default_venue_id = fields.Many2one("federation.venue", string="Default Venue")
    default_format_type = fields.Selection(
        [
            ("single_round_robin", "League"),
            ("double_round_robin", "Home & Away League"),
            ("knockout", "Knockout Cup"),
            ("pool_knockout", "Groups then Knockout"),
        ],
        default="single_round_robin",
        required=True,
        string="Default Format",
    )
    default_start_hour = fields.Float(default=9.0, required=True, string="Day Starts")
    default_end_hour = fields.Float(default=18.0, required=True, string="Day Ends")
    default_slot_duration_minutes = fields.Integer(
        default=40, required=True, string="Match Slot (minutes)"
    )

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        if "division_line_ids" in field_list and not values.get("division_line_ids"):
            preset = values.get("setup_template", "league")
            labels = {
                "league": "League Division",
                "tournament_day": "Tournament Division",
                "cup": "Cup Division",
                "custom": "Competition Division",
            }
            values["division_line_ids"] = [
                fields.Command.create(
                    {
                        "name": labels[preset],
                        "tournament_type": (
                            "single_day" if preset == "tournament_day" else "multi_day"
                        ),
                    }
                )
            ]
        return values

    @api.onchange("setup_template", "date_start")
    def _onchange_competition_preset(self):
        for wizard in self:
            preset = wizard.setup_template or "league"
            if preset == "custom":
                continue
            wizard.default_format_type = (
                "knockout" if preset == "cup" else "single_round_robin"
            )
            wizard.workflow_mode = "controlled" if preset == "cup" else "simple"
            labels = {
                "league": "League Division",
                "tournament_day": "Tournament Division",
                "cup": "Cup Division",
            }
            if not wizard.division_line_ids:
                wizard.division_line_ids = [
                    fields.Command.create(
                        {
                            "name": labels[preset],
                            "tournament_type": (
                                "single_day"
                                if preset == "tournament_day"
                                else "multi_day"
                            ),
                        }
                    )
                ]
            if wizard.date_start:
                if preset == "tournament_day":
                    wizard.date_end = wizard.date_start
                elif preset == "cup":
                    wizard.date_end = wizard.date_start + relativedelta(weeks=8)
                else:
                    wizard.date_end = (
                        wizard.season_id.date_end
                        if wizard.season_id and wizard.season_id.date_end
                        else wizard.date_start + relativedelta(months=6)
                    )
                start = fields.Datetime.to_datetime(wizard.date_start)
                lead_days = 30 if preset == "league" else 14
                wizard.registration_open = start - timedelta(days=lead_days)
                wizard.registration_close = start - timedelta(days=7)

    @api.onchange("season_id")
    def _onchange_competition_season(self):
        for wizard in self:
            season = wizard.season_id
            if season and season.date_start:
                start = wizard.date_start
                if (
                    not start
                    or start < season.date_start
                    or (season.date_end and start > season.date_end)
                ):
                    wizard.date_start = season.date_start
            wizard._onchange_competition_preset()

    @api.depends("workflow_mode")
    def _compute_workflow_summary(self):
        summaries = {
            "simple": (
                "One operator can complete routine checkpoints. Entries, schedules, "
                "lineups and results still run every validation and create the same "
                "immutable snapshots and audit history."
            ),
            "controlled": (
                "A second person reviews protected schedules and results before they "
                "become official. Use this for independent approval or formal events."
            ),
            "custom": (
                "Advanced: create the competition first, then configure each checkpoint "
                "from Competition details."
            ),
        }
        for wizard in self:
            wizard.workflow_summary = summaries.get(wizard.workflow_mode, "")

    def action_create_competition(self):
        self.ensure_one()
        if not self.date_start:
            raise ValidationError(_("Enter the start date."))
        if not self.season_id:
            self.season_id = self._derive_season()
        if not self.competition_id:
            self.competition_id = self._derive_competition()
        action = super().action_create_competition()
        edition = self.env["federation.competition.edition"].browse(action.get("res_id")).exists()
        if edition:
            edition.write(
                {
                    "workflow_mode": self.workflow_mode,
                    "setup_preset": self.setup_template,
                    "setup_default_format_type": self.default_format_type,
                    "setup_default_venue_id": self.default_venue_id.id,
                    "setup_default_start_hour": self.default_start_hour,
                    "setup_default_end_hour": self.default_end_hour,
                    "setup_default_slot_duration_minutes": self.default_slot_duration_minutes,
                }
            )
            if self.creation_draft_id:
                self.creation_draft_id.unlink()
            action = edition.action_open_competition_planner()
            action["context"] = dict(
                self.env.context,
                competition_setup_created=True,
                default_edition_id=edition.id,
                default_venue_id=self.default_venue_id.id,
            )
        return action
