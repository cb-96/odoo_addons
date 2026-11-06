from odoo import _, api, fields, models
from odoo.addons.sports_federation_base import readiness_vocabulary as vocabulary


class FederationMatchdayReadinessRosters(models.AbstractModel):
    """Rosters, game-day line-ups and player eligibility of a game day."""

    _inherit = "federation.matchday.readiness"

    @api.model
    def _readiness_providers(self):
        providers = super()._readiness_providers()
        providers += [
            ("rosters", "_readiness_rosters"),
            ("lineups", "_readiness_lineups"),
            ("eligibility", "_readiness_eligibility"),
        ]
        return providers

    @api.model
    def _club_owner(self, teams):
        """Name the club side that has to act, without inventing a person."""
        clubs = teams.mapped("club_id")
        if len(clubs) == 1:
            return _("Club representative: %(club)s") % {"club": clubs.display_name}
        if clubs:
            return _("Club representatives")
        return None

    @api.model
    def _team_matches(self, scope, team):
        return scope["matches"].filtered(
            lambda match: team in (match.home_team_id | match.away_team_id)
        )

    @api.model
    def _readiness_rosters(self, scope):
        teams = scope["teams"]
        if not teams:
            return self._ready_component(
                "rosters", _("No matches"), vocabulary.NOT_APPLICABLE
            )
        today = fields.Date.context_today(self)
        ready = self.env["federation.team"]
        blocked = self.env["federation.team"]
        pending = self.env["federation.team"]
        deadlines = {"blocked": [], "pending": []}
        for team in teams.sorted("id"):
            tournament = self._team_matches(scope, team)[:1].tournament_id
            assessment = team._get_tournament_roster_assessment(tournament, today=today)
            if not assessment["has_issues"]:
                ready |= team
            elif assessment["deadline_reached"]:
                blocked |= team
                deadlines["blocked"].append(assessment["deadline_date"])
            else:
                pending |= team
                deadlines["pending"].append(assessment["deadline_date"])
        blockers = []
        if blocked:
            blockers.append(
                vocabulary.make_blocker(
                    key="rosters-blocked",
                    status=vocabulary.BLOCKED,
                    problem=self._count_text(
                        len(blocked),
                        _(
                            "%(count)s team has no ready roster and its roster "
                            "deadline has passed."
                        ),
                        _(
                            "%(count)s teams have no ready roster and their roster "
                            "deadline has passed."
                        ),
                    ),
                    action=_("Complete and activate the roster."),
                    destination=self._records_destination(blocked),
                    owner=self._club_owner(blocked),
                    deadline=self._iso(self._earliest(deadlines["blocked"])),
                    count=len(blocked),
                    details=self._details(blocked.mapped("display_name")),
                )
            )
        if pending:
            blockers.append(
                vocabulary.make_blocker(
                    key="rosters-pending",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        len(pending),
                        _("%(count)s team still needs an active roster."),
                        _("%(count)s teams still need an active roster."),
                    ),
                    action=_("Complete and activate the roster."),
                    destination=self._records_destination(pending),
                    owner=self._club_owner(pending),
                    deadline=self._iso(self._earliest(deadlines["pending"])),
                    count=len(pending),
                    details=self._details(pending.mapped("display_name")),
                )
            )
        return self._counter_component("rosters", len(ready), len(teams), blockers)

    @api.model
    def _readiness_lineups(self, scope):
        teams = scope["teams"]
        matches = scope["matches"]
        if not teams:
            return self._ready_component(
                "lineups", _("No matches"), vocabulary.NOT_APPLICABLE
            )
        sheets = (
            self.env["federation.match.sheet"]
            .sudo()
            .search([("match_id", "in", matches.ids)])
        )
        ready = self.env["federation.team"]
        open_teams = self.env["federation.team"]
        waiting_teams = self.env["federation.team"]
        open_sheets = self.env["federation.match.sheet"]
        waiting_sheets = self.env["federation.match.sheet"]
        for team in teams.sorted("id"):
            team_matches = self._team_matches(scope, team)
            team_sheets = sheets.filtered(
                lambda sheet, team=team, team_matches=team_matches: (
                    sheet.team_id == team and sheet.match_id in team_matches
                )
            )
            statuses = [
                vocabulary.status_for("lineup", item.state) for item in team_sheets
            ]
            missing = len(team_matches) - len(team_sheets.mapped("match_id"))
            if missing or vocabulary.ACTION_NEEDED in statuses:
                open_teams |= team
                open_sheets |= team_sheets.filtered(
                    lambda sheet: vocabulary.status_for("lineup", sheet.state)
                    == vocabulary.ACTION_NEEDED
                )
            elif vocabulary.WAITING_REVIEW in statuses:
                waiting_teams |= team
                waiting_sheets |= team_sheets.filtered(
                    lambda sheet: vocabulary.status_for("lineup", sheet.state)
                    == vocabulary.WAITING_REVIEW
                )
            else:
                ready |= team
        deadline = self._iso(scope["first_kickoff"] or scope["matchday"].date)
        blockers = []
        if open_teams:
            blockers.append(
                vocabulary.make_blocker(
                    key="lineups-open",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        len(open_teams),
                        _("%(count)s game-day line-up still needs to be submitted."),
                        _("%(count)s game-day line-ups still need to be submitted."),
                    ),
                    action=_("Prepare and submit the game-day line-up."),
                    destination=(
                        self._records_destination(open_sheets)
                        if open_sheets
                        else self._matchday_destination(scope)
                    ),
                    owner=self._club_owner(open_teams),
                    deadline=deadline,
                    count=len(open_teams),
                    details=self._details(open_teams.mapped("display_name")),
                )
            )
        if waiting_teams:
            blockers.append(
                vocabulary.make_blocker(
                    key="lineups-waiting",
                    status=vocabulary.WAITING_REVIEW,
                    problem=self._count_text(
                        len(waiting_teams),
                        _("%(count)s game-day line-up is waiting for approval."),
                        _("%(count)s game-day line-ups are waiting for approval."),
                    ),
                    action=_("Review and approve the line-up."),
                    destination=self._records_destination(waiting_sheets),
                    owner=_("Match-day manager"),
                    deadline=deadline,
                    count=len(waiting_teams),
                    details=self._details(waiting_teams.mapped("display_name")),
                )
            )
        return self._counter_component("lineups", len(ready), len(teams), blockers)

    @api.model
    def _readiness_eligibility(self, scope):
        sheets = (
            self.env["federation.match.sheet"]
            .sudo()
            .search([("match_id", "in", scope["matches"].ids)])
        )
        lines = sheets.mapped("line_ids").filtered(lambda line: not line.crossed_out)
        if not lines:
            return self._ready_component(
                "eligibility",
                _("No line-ups to check yet"),
                vocabulary.NOT_APPLICABLE,
            )
        ineligible = lines.filtered(lambda line: not line.eligible)
        total = len(lines)
        ready = total - len(ineligible)
        if not ineligible:
            return vocabulary.make_component(
                "eligibility",
                vocabulary.READY,
                _("%(ready)s / %(total)s players eligible")
                % {"ready": ready, "total": total},
                ready=ready,
                total=total,
            )
        teams = ineligible.mapped("match_sheet_id.team_id")
        blocker = vocabulary.make_blocker(
            key="eligibility-failed",
            status=vocabulary.BLOCKED,
            problem=self._count_text(
                len(ineligible),
                _("%(count)s player on a game-day line-up is not eligible to play."),
                _("%(count)s players on game-day line-ups are not eligible to play."),
            ),
            action=_(
                "Replace or cross out the player, or resolve the eligibility issue."
            ),
            destination=self._records_destination(ineligible),
            owner=self._club_owner(teams),
            deadline=self._iso(scope["first_kickoff"] or scope["matchday"].date),
            count=len(ineligible),
            details=self._details(
                "%s (%s): %s"
                % (
                    line.player_id.display_name,
                    line.match_sheet_id.team_id.display_name,
                    (
                        (line.eligibility_feedback or "").splitlines()[0]
                        if line.eligibility_feedback
                        else _("not eligible")
                    ),
                )
                for line in ineligible
            ),
        )
        return vocabulary.make_component(
            "eligibility",
            vocabulary.BLOCKED,
            _("%(ready)s / %(total)s players eligible")
            % {"ready": ready, "total": total},
            blockers=[blocker],
            ready=ready,
            total=total,
        )
