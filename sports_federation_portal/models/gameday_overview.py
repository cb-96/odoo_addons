"""Game-day overview for the club portal.

A team's season **roster** is the pool of players. For every **game day** the
team declares one **line-up** (the players available that day), shared by all
of its matches that day; at each match the coach only crosses out the players
who do not play.

Technically a line-up is a match sheet and a game day is the set of one team's
match sheets that share the same declaration. This model is the single place
where the portal turns match sheets into game-day rows, decides what is
upcoming or past and which rosters a line-up may use, so the roster page, the
game-day list and the line-up page always agree.
"""

from datetime import datetime

from odoo import api, fields, models

# Least advanced first; a game day shows its least advanced match sheet.
STATE_RANK = {"draft": 1, "submitted": 2, "approved": 3, "locked": 4}


class FederationPortalGameday(models.AbstractModel):
    _name = "federation.portal.gameday"
    _description = "Portal Game-day Overview"

    _SHEET_LIMIT = 500

    # ── Time scope ───────────────────────────────────────────────────────

    @api.model
    def upcoming_domain(self):
        """Match sheets of matches still to be played (undated ones last)."""
        today = fields.Date.context_today(self)
        return [
            ("match_id.state", "not in", ("cancelled", "done")),
            "|",
            ("match_scheduled_date", ">=", today),
            "&",
            ("match_scheduled_date", "=", False),
            ("match_id.state", "!=", "draft"),
        ]

    @api.model
    def past_domain(self):
        """Match sheets of matches that were played or whose date has passed."""
        today = fields.Date.context_today(self)
        return [
            ("match_id.state", "!=", "cancelled"),
            "|",
            ("match_scheduled_date", "<", today),
            ("match_id.state", "=", "done"),
        ]

    @api.model
    def season_domain(self, season):
        """Match sheets of matches played in ``season``.

        The season comes from the match's division (or its edition) and never
        from the linked roster: a sheet created before its team had a roster
        has no roster, yet it still belongs to the season.
        """
        season_id = season.id if hasattr(season, "id") else season
        return [
            "|",
            ("match_id.tournament_id.season_id", "=", season_id),
            "&",
            ("match_id.tournament_id.season_id", "=", False),
            ("match_id.tournament_id.edition_id.season_id", "=", season_id),
        ]

    @api.model
    def team_sheets(self, team, season, user=None, upcoming=True):
        """Visible match sheets of one team in one season, linked or not."""
        user = user or self.env.user
        Sheet = self.env["federation.match.sheet"]
        scope = Sheet._portal_get_domain(user=user)
        if scope == [("id", "=", False)]:
            return Sheet.browse()
        domain = scope + [("team_id", "=", team.id)] + self.season_domain(season)
        domain += self.upcoming_domain() if upcoming else self.past_domain()
        return self.env["federation.portal.privilege"].portal_search(
            Sheet,
            domain,
            user=user,
            limit=self._SHEET_LIMIT,
            order="match_kickoff asc, id asc",
        )

    # ── Season / competition of a match sheet ────────────────────────────

    @api.model
    def sheet_season(self, sheet):
        division = sheet.match_id.tournament_id
        return division.season_id or division.edition_id.season_id

    @api.model
    def sheet_competition(self, sheet):
        division = sheet.match_id.tournament_id
        return division.competition_id or division.edition_id.competition_id

    # ── Line-up state ────────────────────────────────────────────────────

    @api.model
    def state_labels(self):
        words = self.env["federation.readiness.vocabulary"]
        return {
            state: words.label_for("lineup", state)
            for state in ("not_started", "draft", "submitted", "approved", "locked")
        }

    @api.model
    def lineup_state(self, sheet):
        """Return the club-facing state key of one line-up."""
        if sheet.state == "draft" and not sheet.line_ids:
            return "not_started"
        return sheet.state

    # ── Rosters a line-up may use ────────────────────────────────────────

    @api.model
    def lineup_rosters(self, sheet, user=None):
        """Rosters of the same team, season and competition as the line-up.

        Rosters of other seasons or competitions are never offered, so a coach
        cannot attach last year's roster. A roster that is already linked stays
        listed so an existing choice is never silently dropped.
        """
        user = user or self.env.user
        Roster = self.env["federation.team.roster"]
        rosters = self.env["federation.portal.privilege"].portal_search(
            Roster,
            [
                ("team_id", "=", sheet.team_id.id),
                ("status", "in", ("active", "draft")),
            ],
            user=user,
            order="id desc",
        )
        season = self.sheet_season(sheet)
        if season:
            rosters = rosters.filtered(lambda roster: roster.season_id == season)
        competition = self.sheet_competition(sheet)
        if competition:
            rosters = rosters.filtered(
                lambda roster: not roster.competition_id
                or roster.competition_id == competition
            )
        if sheet.roster_id and sheet.roster_id not in rosters:
            rosters |= sheet.roster_id
        return rosters.sorted(
            key=lambda roster: (
                0 if competition and roster.competition_id == competition else 1,
                0 if roster.status == "active" else 1,
                -roster.id,
            )
        )

    @api.model
    def default_lineup_roster(self, sheet, rosters):
        """The linked roster, or the best choice when the club has not chosen."""
        return sheet.roster_id or rosters[:1]

    @api.model
    def suggested_roster(self, sheet):
        """The roster a line-up without a chosen roster will start from.

        Mirrors the choice made when a sheet is created: the active roster of
        the team for the season (and competition), else the best other one.
        """
        season = self.sheet_season(sheet)
        if not season:
            return self.env["federation.team.roster"]
        competition = self.sheet_competition(sheet)
        team = sheet.team_id.sudo()
        return team._get_preferred_roster(
            season, competition=competition, statuses=("active",)
        ) or team._get_preferred_roster(season, competition=competition)

    # ── Game-day rows ────────────────────────────────────────────────────

    @staticmethod
    def _kickoff_key(sheet):
        return (not sheet.match_kickoff, sheet.match_kickoff or datetime.min, sheet.id)

    @api.model
    def _gameday_row(self, group):
        lead = min(
            group,
            key=lambda sheet: (
                STATE_RANK.get(sheet.state, 0),
                self._kickoff_key(sheet),
            ),
        )
        first = group.sorted(key=self._kickoff_key)[:1]
        state = self.lineup_state(lead)
        roster = lead.roster_id or self.suggested_roster(lead)
        limit = lead.gameday_roster_limit
        if not limit and roster:
            rule_set = roster._get_effective_rule_set()
            limit = rule_set.gameday_roster_max_size if rule_set else 0
            if not limit:
                limit = roster._get_required_player_bounds()[1]
        return {
            "key": (lead.team_id.id, first.id),
            "team": lead.team_id,
            "sheet": lead,
            "sheets": group,
            "first_match": first.match_id,
            "kickoff": first.match_kickoff,
            "date": first.match_scheduled_date,
            "matches": len(group),
            "roster": roster,
            "roster_linked": bool(lead.roster_id),
            "state": state,
            "state_label": self.state_labels().get(state, state),
            "selected": len(lead.line_ids),
            "limit": limit,
            "playing": lead.participant_count,
            "needs_action": state in ("not_started", "draft"),
            "url": "/my/match-sheets/%s" % lead.id,
        }

    @api.model
    def group_gamedays(self, sheets, upcoming=True):
        """Group match sheets into one row per team game day.

        Upcoming game days are ordered soonest first (undated last), earlier
        ones most recent first.
        """
        groups = {}
        for sheet in sheets:
            key = (sheet.team_id.id, sheet._get_gameday_scope() or ("sheet", sheet.id))
            groups[key] = groups.get(key, sheets.browse()) | sheet
        rows = [self._gameday_row(group) for group in groups.values()]
        rows.sort(
            key=lambda row: (
                not row["kickoff"],
                row["kickoff"] or datetime.min,
                row["team"].name or "",
                row["sheet"].id,
            )
        )
        if not upcoming:
            rows.reverse()
        return rows

    @api.model
    def roster_gamedays(self, roster, user=None, upcoming=True, limit=None):
        """Game-day rows of one roster's team within the roster's season.

        Sheets that are linked to another roster of the team are left out;
        sheets without a roster are included because the coach will pick this
        one (or its season's only roster) when preparing the line-up.
        """
        user = user or self.env.user
        sheets = self.team_sheets(roster.team_id, roster.season_id, user, upcoming)
        competition = roster.competition_id
        sheets = sheets.filtered(
            lambda sheet: (not sheet.roster_id or sheet.roster_id == roster)
            and (not competition or self.sheet_competition(sheet) == competition)
        )
        rows = self.group_gamedays(sheets, upcoming=upcoming)
        return rows[:limit] if limit else rows
