from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class FederationCreateCompetitionWizardJourney(models.TransientModel):
    _inherit = "federation.create.competition.wizard"

    creation_draft_id = fields.Many2one("federation.competition.creation.draft", readonly=True)

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

    @api.onchange("setup_template", "date_start", "season_id")
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
