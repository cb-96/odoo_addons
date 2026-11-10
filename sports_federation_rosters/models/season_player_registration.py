from odoo import _, api, fields, models


class FederationTeamRosterSeasonPlayers(models.Model):
    _inherit = "federation.team.roster"

    season_registered_player_ids = fields.Many2many(
        "federation.player", compute="_compute_season_registered_players",
        string="Registered Season Players",
    )

    @api.depends("team_id", "season_id", "valid_from")
    def _compute_season_registered_players(self):
        License = self.env["federation.player.license"].sudo()
        for roster in self:
            roster.season_registered_player_ids = License._registered_players(
                roster.team_id.club_id, roster.season_id, roster._get_reference_date(),
            )

    def write(self, vals):
        result = super().write(vals)
        if {"team_id", "season_id", "competition_id", "valid_from"}.intersection(vals):
            self.mapped("line_ids").filtered(
                lambda line: line.status == "active"
            )._validate_player_eligibility()
        return result


class FederationRosterLineSeasonPlayers(models.Model):
    _inherit = "federation.team.roster.line"

    def _get_eligibility_reasons(self, reference_date=None):
        reasons = super()._get_eligibility_reasons(reference_date=reference_date)
        for line in self:
            roster = line.roster_id
            date = reference_date or roster._get_reference_date()
            License = self.env["federation.player.license"].sudo()
            license = License.search([
                ("player_id", "=", line.player_id.id),
                ("club_id", "=", roster.team_id.club_id.id),
                ("season_id", "=", roster.season_id.id),
                ("state", "=", "active"), ("issue_date", "<=", date),
                ("expiry_date", ">=", date),
            ], limit=1)
            if not license:
                reasons.append(_(
                    "The player needs an approved, valid registration for this club "
                    "in the competition season before joining the team roster."
                ))
            if line.license_id and line.license_id != license:
                reasons.append(_("The selected licence is not the player's valid club season registration."))
        return reasons


class FederationMatchSheetSeasonPlayers(models.Model):
    _inherit = "federation.match.sheet.line"

    def _get_eligibility_reasons(self):
        reasons = super()._get_eligibility_reasons()
        self.ensure_one()
        sheet = self.match_sheet_id
        if sheet and self.player_id:
            registered = self.env["federation.player.license"].sudo()._registered_players(
                sheet.team_id.club_id,
                sheet.match_id.tournament_id.season_id or sheet.match_id.tournament_id.edition_id.season_id,
                sheet._get_reference_date(),
            )
            if self.player_id not in registered:
                reasons.append(_("The player has no approved club season registration valid on the match date."))
        return reasons
