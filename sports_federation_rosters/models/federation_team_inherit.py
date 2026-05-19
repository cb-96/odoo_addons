from datetime import timedelta

from odoo import _, fields, models


class FederationTeam(models.Model):
    _inherit = "federation.team"

    roster_ids = fields.One2many(
        "federation.team.roster",
        "team_id",
        string="Rosters",
    )
    roster_count = fields.Integer(
        compute="_compute_roster_count",
        string="Roster Count",
    )

    def _compute_roster_count(self):
        """Compute roster count."""
        for record in self:
            record.roster_count = len(record.roster_ids)

    def action_view_rosters(self):
        """Execute the view rosters action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_rosters.action_federation_team_roster"
        )
        action["context"] = {"default_team_id": self.id}
        rosters = self.roster_ids
        if len(rosters) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": rosters.id,
                    "domain": [],
                }
            )
            return action
        action["domain"] = [("team_id", "=", self.id)]
        return action

    def _ensure_tournament_roster(self, tournament):
        """Handle ensure tournament roster."""
        self.ensure_one()
        Roster = self.env["federation.team.roster"]
        if not tournament or not tournament.season_id:
            return Roster.browse([])

        roster = self._get_preferred_roster(
            tournament.season_id,
            competition=tournament.competition_id,
            statuses=("draft", "active"),
        )
        if roster:
            return roster

        roster_vals = {
            "team_id": self.id,
            "season_id": tournament.season_id.id,
            "competition_id": (
                tournament.competition_id.id if tournament.competition_id else False
            ),
        }
        if tournament.rule_set_id and not tournament.competition_id:
            roster_vals["rule_set_id"] = tournament.rule_set_id.id
        return Roster.create(roster_vals)

    def _get_preferred_roster(self, season, competition=False, statuses=None):
        """Return preferred roster."""
        self.ensure_one()
        Roster = self.env["federation.team.roster"]
        if not season:
            return Roster.browse([])

        season_id = season.id if hasattr(season, "id") else season
        competition_id = (
            competition.id
            if competition and hasattr(competition, "id")
            else competition
        )
        domain = [
            ("team_id", "=", self.id),
            ("season_id", "=", season_id),
        ]
        if statuses:
            domain.append(("status", "in", list(statuses)))

        if competition_id:
            roster = Roster.search(
                domain + [("competition_id", "=", competition_id)],
                limit=1,
                order="valid_from desc, id desc",
            )
            if roster:
                return roster

        return Roster.search(
            domain + [("competition_id", "=", False)],
            limit=1,
            order="valid_from desc, id desc",
        )

    def _get_tournament_first_match_date(self, tournament):
        """Return tournament first match date."""
        self.ensure_one()
        if not tournament:
            return False

        match = self.env["federation.match"].search(
            [
                ("tournament_id", "=", tournament.id),
                ("date_scheduled", "!=", False),
                ("state", "!=", "cancelled"),
                "|",
                ("home_team_id", "=", self.id),
                ("away_team_id", "=", self.id),
            ],
            order="date_scheduled asc, id asc",
            limit=1,
        )
        if match and match.date_scheduled:
            return fields.Datetime.to_datetime(match.date_scheduled).date()
        return tournament.date_start or False

    def _get_tournament_roster_assessment(self, tournament, today=None):
        """Return tournament roster assessment."""
        self.ensure_one()
        Roster = self.env["federation.team.roster"]
        if not tournament or not tournament.season_id:
            return {
                "roster": Roster.browse([]),
                "first_match_date": False,
                "deadline_date": False,
                "deadline_reached": False,
                "blocking_issues": [],
                "feedback": False,
            }

        today = today or fields.Date.context_today(self)
        first_match_date = self._get_tournament_first_match_date(tournament)
        deadline_date = (
            first_match_date - timedelta(days=7) if first_match_date else False
        )
        roster = self._get_preferred_roster(
            tournament.season_id,
            competition=tournament.competition_id,
            statuses=("active",),
        )
        if not roster:
            roster = self._get_preferred_roster(
                tournament.season_id,
                competition=tournament.competition_id,
                statuses=("draft",),
            )
        if not roster:
            roster = self._get_preferred_roster(
                tournament.season_id,
                competition=tournament.competition_id,
            )

        roster_issues = []
        if not roster:
            roster_issues.append(
                _("No roster exists yet for team '%(team)s' in season '%(season)s'.")
                % {
                    "team": self.display_name,
                    "season": tournament.season_id.display_name,
                }
            )
        else:
            if roster.status != "active":
                status_label = dict(roster._fields["status"].selection).get(
                    roster.status, roster.status
                )
                roster_issues.append(
                    _("Roster '%(roster)s' exists but is still %(status)s.")
                    % {
                        "roster": roster.display_name,
                        "status": status_label,
                    }
                )

            readiness_issues = roster._get_readiness_issues(
                reference_date=first_match_date or tournament.date_start or today
            )
            if readiness_issues:
                roster_issues.append(
                    _("Roster '%(roster)s' is not ready: %(issues)s")
                    % {
                        "roster": roster.display_name,
                        "issues": "; ".join(readiness_issues),
                    }
                )

        deadline_reached = bool(deadline_date and today >= deadline_date)
        blocking_issues = roster_issues if deadline_reached else []
        feedback = False
        if blocking_issues:
            feedback = _("Roster deadline reached on %(deadline)s. %(issues)s") % {
                "deadline": deadline_date,
                "issues": " ".join(blocking_issues),
            }
        elif roster_issues and deadline_date:
            feedback = _(
                "Team '%(team)s' can be confirmed without an active roster for now, but must have an active ready roster by %(deadline)s (one week before the first scheduled match or tournament start). %(issues)s"
            ) % {
                "team": self.display_name,
                "deadline": deadline_date,
                "issues": " ".join(roster_issues),
            }

        return {
            "roster": roster,
            "first_match_date": first_match_date,
            "deadline_date": deadline_date,
            "deadline_reached": deadline_reached,
            "blocking_issues": blocking_issues,
            "feedback": feedback,
        }
