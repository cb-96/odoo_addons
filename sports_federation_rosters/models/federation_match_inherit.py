from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationMatch(models.Model):
    _inherit = "federation.match"

    match_sheet_ids = fields.One2many(
        "federation.match.sheet",
        "match_id",
        string="Match Sheets",
    )
    match_sheet_count = fields.Integer(
        compute="_compute_match_sheet_count",
        string="Match Sheet Count",
    )

    def _compute_match_sheet_count(self):
        """Compute match sheet count."""
        for record in self:
            record.match_sheet_count = len(record.match_sheet_ids)

    @api.model_create_multi
    def create(self, vals_list):
        matches = super().create(vals_list)
        if not self.env.context.get("skip_auto_match_sheets"):
            matches._create_auto_match_sheets()
        return matches

    def _create_auto_match_sheets(self):
        """Create draft match sheets for home and away teams if not already present."""
        Sheet = self.env["federation.match.sheet"]
        Rep = self.env.get("federation.club.representative")

        for match in self:
            sides = []
            if match.home_team_id:
                sides.append((match.home_team_id, "home"))
            if match.away_team_id:
                sides.append((match.away_team_id, "away"))

            for team, side in sides:
                existing = Sheet.search([
                    ("match_id", "=", match.id),
                    ("team_id", "=", team.id),
                    ("side", "=", side),
                ], limit=1)
                if existing:
                    continue

                vals = {
                    "match_id": match.id,
                    "team_id": team.id,
                    "side": side,
                    "state": "draft",
                }

                # Link the best available roster for this team/tournament
                if match.tournament_id and match.tournament_id.season_id:
                    roster = team._get_preferred_roster(
                        match.tournament_id.season_id,
                        competition=match.tournament_id.competition_id,
                        statuses=("active",),
                    )
                    if not roster:
                        roster = team._get_preferred_roster(
                            match.tournament_id.season_id,
                            competition=match.tournament_id.competition_id,
                        )
                    if roster:
                        vals["roster_id"] = roster.id

                # Use primary contact of the team's club as manager, if available
                if Rep is not None and team.club_id:
                    primary = Rep._get_primary_contact(team.club_id)
                    if primary and primary.partner_id:
                        vals["manager_id"] = primary.id
                        vals["manager_name"] = primary.partner_id.name

                Sheet.create(vals)

    def action_view_match_sheets(self):
        """Execute the view match sheets action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_rosters.action_federation_match_sheet"
        )
        action["domain"] = [("match_id", "=", self.id)]
        action["context"] = {"default_match_id": self.id}
        return action

    def _get_team_roster_deadline_issues(self):
        """Return team roster deadline issues."""
        self.ensure_one()
        if (
            not self.tournament_id
            or not self.date_scheduled
            or not (self.home_team_id or self.away_team_id)
        ):
            return []

        scheduled_date = fields.Datetime.to_datetime(self.date_scheduled).date()
        today = fields.Date.context_today(self)
        if scheduled_date < today:
            return []

        issues = []
        for team in (self.home_team_id | self.away_team_id):
            assessment = team._get_tournament_roster_assessment(
                self.tournament_id,
                today=today,
            )
            if assessment["blocking_issues"]:
                issues.append(
                    _("Team '%(team)s': %(issues)s")
                    % {
                        "team": team.display_name,
                        "issues": "; ".join(assessment["blocking_issues"]),
                    }
                )
        return issues

    @api.constrains(
        "tournament_id",
        "home_team_id",
        "away_team_id",
        "date_scheduled",
        "state",
    )
    def _check_team_roster_deadlines(self):
        """Validate team roster deadlines."""
        for record in self:
            if record.state == "cancelled":
                continue
            issues = record._get_team_roster_deadline_issues()
            if issues:
                raise ValidationError(
                    _(
                        "Matches cannot be scheduled on or after the roster deadline without an active ready team roster:\n- %(issues)s"
                    )
                    % {"issues": "\n- ".join(issues)}
                )