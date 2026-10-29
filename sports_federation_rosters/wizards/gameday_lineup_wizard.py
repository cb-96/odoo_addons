from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationGamedayLineupWizard(models.TransientModel):
    _name = "federation.gameday.lineup.wizard"
    _description = "Prepare Game-Day Lineup"

    matchday_id = fields.Many2one("federation.matchday", required=True, readonly=True)
    available_team_ids = fields.Many2many(
        "federation.team", compute="_compute_available_team_ids"
    )
    team_id = fields.Many2one(
        "federation.team",
        required=True,
        domain="[('id', 'in', available_team_ids)]",
    )
    roster_id = fields.Many2one(
        "federation.team.roster",
        required=True,
        domain="[('team_id', '=', team_id), ('status', '=', 'active')]",
    )
    line_ids = fields.One2many(
        "federation.gameday.lineup.wizard.line", "wizard_id", string="Players"
    )
    readiness_message = fields.Text(compute="_compute_readiness_message")

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        matchday = self.env["federation.matchday"].browse(
            values.get("matchday_id") or self.env.context.get("default_matchday_id")
        ).exists()
        if matchday:
            values["matchday_id"] = matchday.id
            teams = self._teams_for_matchday(matchday)
            team = self.env["federation.team"].browse(
                self.env.context.get("default_team_id")
            ).exists() or teams[:1]
            if team:
                values["team_id"] = team.id
                roster, commands = self._lineup_defaults(matchday, team)
                values["roster_id"] = roster.id
                values["line_ids"] = commands
        return values

    @api.model
    def _sheets_for(self, matchday, team):
        return self.env["federation.match.sheet"].search(
            [
                ("match_id.schedule_publication_id.matchday_id", "=", matchday.id),
                ("team_id", "=", team.id),
                ("match_id.state", "!=", "cancelled"),
            ],
            order="match_kickoff asc,id asc",
        )

    @api.model
    def _teams_for_matchday(self, matchday):
        return (
            matchday.published_match_ids.mapped("home_team_id")
            | matchday.published_match_ids.mapped("away_team_id")
        ).sorted(lambda team: (team.name or "", team.id))

    @api.depends("matchday_id", "matchday_id.published_match_ids")
    def _compute_available_team_ids(self):
        for wizard in self:
            wizard.available_team_ids = self._teams_for_matchday(wizard.matchday_id)

    @api.model
    def _lineup_defaults(self, matchday, team):
        sheets = self._sheets_for(matchday, team)
        source = sheets.filtered(
            lambda sheet: sheet.roster_id
            and sheet.roster_id.status == "active"
            and sheet.line_ids
        )[:1]
        if not source:
            source = sheets.filtered(
                lambda sheet: sheet.roster_id and sheet.roster_id.status == "active"
            )[:1]
        roster = source.roster_id if source else self.env["federation.team.roster"]
        if not roster:
            roster = self.env["federation.team.roster"].search(
                [
                    ("team_id", "=", team.id),
                    ("season_id", "=", matchday.edition_id.season_id.id),
                    ("competition_id", "=", matchday.edition_id.competition_id.id),
                    ("status", "=", "active"),
                ],
                order="id desc",
                limit=1,
            )
        commands = []
        if source and source.roster_id == roster and source.line_ids:
            commands = [
                fields.Command.create(
                    {
                        "player_id": line.player_id.id,
                        "roster_line_id": line.roster_line_id.id,
                        "is_starter": line.is_starter,
                        "is_substitute": line.is_substitute,
                        "is_captain": line.is_captain,
                        "jersey_number": line.jersey_number,
                    }
                )
                for line in source.line_ids
            ]
        elif roster:
            commands = [
                fields.Command.create(
                    {
                        "player_id": line.player_id.id,
                        "roster_line_id": line.id,
                        "is_substitute": True,
                        "jersey_number": line.jersey_number,
                    }
                )
                for line in roster.line_ids.filtered(lambda item: item.status == "active")
            ]
        return roster, commands

    @api.onchange("team_id")
    def _onchange_team_id(self):
        if not self.team_id:
            self.roster_id = False
            self.line_ids = False
            return
        self.roster_id, line_commands = self._lineup_defaults(
            self.matchday_id, self.team_id
        )
        self.line_ids = [fields.Command.clear(), *line_commands]

    @api.depends("team_id", "roster_id", "line_ids", "line_ids.player_id")
    def _compute_readiness_message(self):
        for wizard in self:
            issues = []
            if not wizard.roster_id:
                issues.append(_("Select an active roster."))
            if not wizard.line_ids:
                issues.append(_("Select at least one player."))
            if len(wizard.line_ids.mapped("player_id")) != len(wizard.line_ids):
                issues.append(_("Each player can appear only once."))
            if len(wizard.line_ids.filtered("is_captain")) > 1:
                issues.append(_("Select no more than one captain."))
            if wizard.line_ids.filtered(
                lambda line: line.is_starter and line.is_substitute
            ):
                issues.append(_("A player cannot be both a starter and a substitute."))
            wizard.readiness_message = "\n".join(issues) if issues else _("Ready to save.")

    def _apply(self):
        self.ensure_one()
        if not self.roster_id or not self.line_ids:
            raise ValidationError(self.readiness_message)
        if self.roster_id.team_id != self.team_id or self.roster_id.status != "active":
            raise ValidationError(_("Select an active roster for the selected team."))
        if self.line_ids.filtered(
            lambda line: line.roster_line_id.roster_id != self.roster_id
            or line.roster_line_id.player_id != line.player_id
        ):
            raise ValidationError(
                _("Every selected player must come from the selected active roster.")
            )
        if len(self.line_ids.mapped("player_id")) != len(self.line_ids):
            raise ValidationError(_("Each player can appear only once."))
        if len(self.line_ids.filtered("is_captain")) > 1:
            raise ValidationError(_("Select no more than one captain."))
        if self.line_ids.filtered(lambda line: line.is_starter and line.is_substitute):
            raise ValidationError(_("A player cannot be both a starter and a substitute."))
        sheets = self._sheets_for(self.matchday_id, self.team_id)
        if not sheets:
            raise ValidationError(
                _("Publish the schedule so operational matches and lineup sheets exist.")
            )
        source = sheets.filtered(lambda sheet: sheet.state == "draft")[:1]
        if not source:
            raise ValidationError(
                _("This game-day lineup has already been submitted or approved.")
            )
        source.write({"roster_id": self.roster_id.id})
        source.line_ids.unlink()
        self.env["federation.match.sheet.line"].create(
            [
                {
                    "match_sheet_id": source.id,
                    "player_id": line.player_id.id,
                    "roster_line_id": line.roster_line_id.id,
                    "is_starter": line.is_starter,
                    "is_substitute": line.is_substitute,
                    "is_captain": line.is_captain,
                    "jersey_number": line.jersey_number,
                }
                for line in self.line_ids
            ]
        )
        source._synchronize_gameday_lineup(source)
        return source

    def action_save_draft(self):
        source = self._apply()
        return source.get_formview_action()

    def action_save_submit(self):
        source = self._apply()
        source.action_submit()
        return source.get_formview_action()


class FederationGamedayLineupWizardLine(models.TransientModel):
    _name = "federation.gameday.lineup.wizard.line"
    _description = "Game-Day Lineup Player"
    _order = "is_starter desc,is_substitute,id"

    wizard_id = fields.Many2one(
        "federation.gameday.lineup.wizard", required=True, ondelete="cascade"
    )
    player_id = fields.Many2one("federation.player", required=True)
    roster_line_id = fields.Many2one("federation.team.roster.line", required=True)
    is_starter = fields.Boolean()
    is_substitute = fields.Boolean(default=True)
    is_captain = fields.Boolean()
    jersey_number = fields.Char()
