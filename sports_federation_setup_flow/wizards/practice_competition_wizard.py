"""Create a complete practice competition in one click.

The generator drives the same commands an operator uses, in order:
competition creation, teams and format, game days, schedule generation and
publication.  Afterwards the creator receives To-Do activities that walk
through every screen worth checking.  Anything that could not be completed
automatically becomes a "fix" activity instead of an error, so the creator
always ends up with a usable competition and an honest checklist.
"""

import logging
from datetime import timedelta
from html import escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..models.practice_competition import PRACTICE_CODE_PREFIX, PRACTICE_PREFIX

_logger = logging.getLogger(__name__)

SAMPLE_CLUB_NAMES = [
    "Falcons",
    "Otters",
    "Comets",
    "Wolves",
    "Hornets",
    "Pandas",
    "Ravens",
    "Lynx",
    "Sharks",
    "Bisons",
    "Herons",
    "Foxes",
]
FORMAT_BY_TYPE = {
    "league": "single_round_robin",
    "cup": "knockout",
    "tournament_day": "single_round_robin",
}
PRACTICE_REASON = "Practice competition: schedule warnings accepted automatically."


class FederationPracticeCompetitionWizard(models.TransientModel):
    _name = "federation.practice.competition.wizard"
    _description = "Create Practice Competition"

    name = fields.Char(required=True, default=lambda self: self._default_name())
    competition_type = fields.Selection(
        [
            ("league", "League"),
            ("tournament_day", "One-day tournament"),
            ("cup", "Knockout cup"),
        ],
        default="league",
        required=True,
        string="Type",
    )
    workflow_mode = fields.Selection(
        [("simple", "Streamlined"), ("controlled", "Independent Review")],
        default="simple",
        required=True,
        string="Workflow",
        help="Independent Review also lets you try the review and approval screens.",
    )
    division_count = fields.Integer(default=2, required=True, string="Divisions")
    teams_per_division = fields.Integer(
        default=6, required=True, string="Teams per division"
    )
    gameday_count = fields.Integer(default=3, required=True, string="Game days")
    first_gameday_today = fields.Boolean(
        default=True,
        string="First game day is today",
        help="Lets you try the live game day: running a court and entering results.",
    )
    first_gameday = fields.Date(
        default=lambda self: fields.Date.context_today(self) + timedelta(days=7),
        string="First game day",
    )

    @api.model
    def _default_name(self):
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        return _("Practice competition %(stamp)s", stamp=stamp.strftime("%d/%m %H:%M"))

    @api.constrains("division_count", "teams_per_division", "gameday_count")
    def _check_sizes(self):
        for wizard in self:
            if not 1 <= wizard.division_count <= 4:
                raise ValidationError(_("Use between 1 and 4 divisions."))
            if not 2 <= wizard.teams_per_division <= 12:
                raise ValidationError(_("Use between 2 and 12 teams per division."))
            if not 1 <= wizard.gameday_count <= 12:
                raise ValidationError(_("Use between 1 and 12 game days."))

    # ------------------------------------------------------------------
    # Sample master data (reused between practice competitions)
    # ------------------------------------------------------------------

    def _practice_venue(self):
        Venue = self.env["federation.venue"].with_context(active_test=False)
        venue = Venue.search(
            [("name", "=", "%s Sports Hall" % PRACTICE_PREFIX)], limit=1
        )
        if not venue:
            venue = Venue.create({"name": "%s Sports Hall" % PRACTICE_PREFIX})
        if "active" in venue._fields and not venue.active:
            venue.active = True
        Court = self.env["federation.playing.area"].with_context(active_test=False)
        courts = Court.search([("venue_id", "=", venue.id)])
        for index in range(len(courts) + 1, 4):
            courts |= Court.create(
                {"name": _("Court %(number)s", number=index), "venue_id": venue.id}
            )
        courts.filtered(
            lambda court: "active" in court._fields and not court.active
        ).write({"active": True})
        return venue

    def _practice_season(self, date_start, date_end):
        Season = self.env["federation.season"].with_context(active_test=False)
        code = "%sSEASON" % PRACTICE_CODE_PREFIX
        season = Season.search([("code", "=", code)], limit=1)
        values = {
            "date_start": (
                min(date_start, season.date_start)
                if season
                else date_start - timedelta(days=1)
            ),
            "date_end": (
                max(date_end, season.date_end)
                if season
                else date_end + timedelta(days=1)
            ),
        }
        if values["date_end"] <= values["date_start"]:
            values["date_end"] = values["date_start"] + timedelta(days=1)
        if season:
            season.write(dict(values, active=True))
        else:
            season = Season.create(
                dict(values, name=_("%s Season") % PRACTICE_PREFIX, code=code)
            )
        if season.state == "draft":
            try:
                with self.env.cr.savepoint():
                    season.action_open()
            except (UserError, ValidationError):
                _logger.info("Practice season left in draft.")
        return season

    def _practice_clubs(self, count):
        Club = self.env["federation.club"].with_context(active_test=False)
        clubs = Club.browse()
        for index in range(count):
            code = "%sCLUB-%02d" % (PRACTICE_CODE_PREFIX, index + 1)
            club = Club.search([("code", "=", code)], limit=1)
            if not club:
                club = Club.create(
                    {
                        "name": "%s %s"
                        % (
                            PRACTICE_PREFIX,
                            SAMPLE_CLUB_NAMES[index % len(SAMPLE_CLUB_NAMES)],
                        ),
                        "code": code,
                    }
                )
            elif not club.active:
                club.active = True
            clubs |= club
        return clubs

    def _practice_team(self, club, division_index):
        Team = self.env["federation.team"].with_context(active_test=False)
        code = "%s-D%s" % (club.code, division_index + 1)
        team = Team.search([("code", "=", code)], limit=1)
        name = "%s %s" % (
            club.name.replace(PRACTICE_PREFIX, "").strip(),
            division_index + 1,
        )
        if not team:
            team = Team.create(
                {"name": name, "code": code, "club_id": club.id, "category": "senior"}
            )
        elif not team.active:
            team.active = True
        return team

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _gameday_dates(self):
        first = (
            fields.Date.context_today(self)
            if self.first_gameday_today
            else (self.first_gameday or fields.Date.context_today(self))
        )
        count = 1 if self.competition_type == "tournament_day" else self.gameday_count
        return [first + timedelta(weeks=index) for index in range(count)]

    def _create_competition(self, venue, season, dates):
        division_names = [
            _("Division %(number)s", number=index + 1)
            for index in range(self.division_count)
        ]
        creation = self.env["federation.create.competition.wizard"].create(
            {
                "name": "%s %s" % (PRACTICE_PREFIX, self.name),
                "setup_template": self.competition_type,
                "workflow_mode": self.workflow_mode,
                "season_id": season.id,
                "date_start": dates[0],
                "date_end": dates[-1],
                "default_venue_id": venue.id,
                "default_format_type": FORMAT_BY_TYPE[self.competition_type],
                "division_line_ids": [
                    fields.Command.create(
                        {
                            "name": name,
                            "tournament_type": (
                                "single_day"
                                if self.competition_type == "tournament_day"
                                else "multi_day"
                            ),
                        }
                    )
                    for name in division_names
                ],
                "role_line_ids": [
                    fields.Command.create({"role": role, "user_id": self.env.user.id})
                    for role in (
                        "competition_director",
                        "matchday_manager",
                        "results_officer",
                    )
                ],
            }
        )
        creation.action_create_competition()
        edition = self.env["federation.competition.edition"].search(
            [("name", "=", "%s %s" % (PRACTICE_PREFIX, self.name))],
            order="id desc",
            limit=1,
        )
        if not edition:
            raise UserError(_("The practice competition could not be created."))
        edition.sudo().write(
            {"is_practice": True, "practice_created_by_id": self.env.user.id}
        )
        return edition

    def _run_step(self, issues, label, function, *args, **kwargs):
        try:
            with self.env.cr.savepoint():
                return function(*args, **kwargs)
        except (AccessError, UserError, ValidationError) as error:
            message = error.args[0] if error.args else str(error)
            issues.append((label, message))
            _logger.info("Practice competition step '%s' failed: %s", label, message)
            return False

    def _setup_teams_and_format(self, edition, clubs):
        teams_by_division = {}
        for index, division in enumerate(edition.tournament_ids.sorted("id")):
            teams_by_division[division] = self.env["federation.team"].browse(
                [self._practice_team(club, index).id for club in clubs]
            )
        DivisionWizard = self.env["federation.competition.division.setup.wizard"]
        format_type = FORMAT_BY_TYPE[self.competition_type]
        wizard = DivisionWizard.create(
            {
                "edition_id": edition.id,
                "line_ids": [
                    fields.Command.create(
                        {
                            "division_id": division.id,
                            "name": division.name,
                            "team_ids": [fields.Command.set(teams.ids)],
                            "format_type": format_type,
                            "pool_count": 2,
                        }
                    )
                    for division, teams in teams_by_division.items()
                ],
            }
        )
        wizard.action_apply()
        self._prepare_practice_rosters(edition, teams_by_division)
        return True

    def _prepare_practice_rosters(self, edition, teams_by_division):
        Player = self.env["federation.player"]
        RosterLine = self.env["federation.team.roster.line"]
        License = self.env["federation.player.license"]
        today = fields.Date.context_today(self)
        license_expiry = max(edition.season_id.date_end, today + timedelta(days=365))
        for division, teams in teams_by_division.items():
            for team in teams:
                roster = team._ensure_tournament_roster(division)
                active_lines = roster.line_ids.filtered(
                    lambda line: line.status == "active"
                )
                min_players, _max_players = roster._get_required_player_bounds()
                players_to_add = max(1, min_players) - len(active_lines)
                if players_to_add <= 0:
                    continue
                if roster.status == "active":
                    roster.action_set_draft()
                for index in range(players_to_add):
                    player = Player.create(
                        {
                            "first_name": team.name,
                            "last_name": _("Practice Player %s") % (index + 1),
                            "gender": team.gender or "male",
                            "birth_date": today - timedelta(days=365 * 25),
                            "club_id": team.club_id.id,
                            "team_ids": [fields.Command.link(team.id)],
                        }
                    )
                    license_record = License.create(
                        {
                            "name": "PRACTICE-%s-%s" % (edition.id, player.id),
                            "player_id": player.id,
                            "season_id": edition.season_id.id,
                            "club_id": team.club_id.id,
                            "issue_date": today,
                            "expiry_date": license_expiry,
                        }
                    )
                    license_record.action_activate()
                    RosterLine.create(
                        {
                            "roster_id": roster.id,
                            "player_id": player.id,
                            "license_id": license_record.id,
                            "status": "active",
                        }
                    )
                if roster.status == "draft":
                    roster.action_activate()

    def _setup_gamedays(self, edition, venue, dates):
        GamedayWizard = self.env["federation.competition.gameday.setup.wizard"]
        wizard = GamedayWizard.create(
            {
                "edition_id": edition.id,
                "new_date": dates[0],
                "default_venue_id": venue.id,
                "default_start_hour": 9.0,
                "default_end_hour": 18.0,
                "default_slot_duration_minutes": 40,
                "repeat_every_weeks": 1,
                "repeat_count": len(dates),
            }
        )
        wizard.line_ids.unlink()
        wizard.action_add_recurring_days()
        wizard._save_days()
        return True

    def _generate_schedule(self, edition):
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {"edition_id": edition.id}
        )
        wizard._onchange_edition_id()
        wizard.action_preview()
        if wizard.blocking_issue_count:
            raise ValidationError(
                _(
                    "The schedule has %(count)s blocking issue(s); open Generate schedule to see them.",
                    count=wizard.blocking_issue_count,
                )
            )
        wizard.action_apply()
        return True

    def _publish(self, edition, issues):
        summary = edition._publish_competition_schedule(
            warning_override_reason=PRACTICE_REASON
        )
        for item in summary["skipped"]:
            issues.append((_("Publish schedule"), item))
        return summary

    # ------------------------------------------------------------------
    # Verification checklist
    # ------------------------------------------------------------------

    def _todo(self, record, summary, note, sequence):
        activity_type = self.env.ref(
            "mail.mail_activity_data_todo", raise_if_not_found=False
        )
        today = fields.Date.context_today(self)
        record.activity_schedule(
            activity_type_id=activity_type.id if activity_type else False,
            summary="%02d. %s" % (sequence, summary),
            note=note,
            user_id=self.env.user.id,
            date_deadline=today,
        )

    def _assign_checklist(self, edition, issues, summary):
        days = self.env["federation.matchday"].search(
            [("edition_id", "=", edition.id)], order="date,id"
        )
        first_day = days[:1]
        division = edition.tournament_ids.sorted("id")[:1]
        review = edition.workflow_mode == "controlled"
        items = [
            (
                edition,
                _("Open the competition workspace"),
                _(
                    "<p>Click <b>Open Workspace</b>. Every step should be complete; check that "
                    "the next action and messages are clear.</p>"
                ),
            ),
            (
                edition,
                _("Review teams and format"),
                _(
                    "<p>Open <b>Teams &amp; format</b>. Check the teams per division and the "
                    "number of matches. Try changing a format and saving.</p>"
                ),
            ),
            (
                first_day or edition,
                _("Check the game days and schedule"),
                _(
                    "<p>Open <b>Game Days</b>. Check dates, courts and times, and look at the "
                    "schedule of each game day.</p>"
                ),
            ),
        ]
        if review:
            items.append(
                (
                    edition,
                    _("Try the independent review"),
                    _(
                        "<p>This competition uses Independent Review. Open <b>Publish</b> in the "
                        "workspace, then approve the schedules in the review queue. Separation of "
                        "duties may require a second user.</p>"
                    ),
                )
            )
        items += [
            (
                first_day or edition,
                _("Enter results on the first game day"),
                _(
                    "<p>Open the first game day and enter a few scores with <b>Save result</b>. "
                    "If the day is today, also try <b>Run this court</b>.</p>"
                ),
            ),
            (
                division or edition,
                _("Check standings"),
                _(
                    "<p>After entering results, open the division standings and check that "
                    "points and order are correct.</p>"
                ),
            ),
            (
                edition,
                _("Check the club view"),
                _(
                    "<p>Ask a colleague with a club representative account, or use a test portal "
                    "user linked to a <i>[Practice]</i> club, to look at rosters, lineups and "
                    "results in the portal.</p>"
                ),
            ),
            (
                edition,
                _("Look at the public preview"),
                _(
                    "<p>Use <b>Public preview</b>. Practice competitions can be previewed but never "
                    "published on the website.</p>"
                ),
            ),
        ]
        sequence = 1
        for label, message in issues:
            self._todo(
                edition,
                _("Fix: %(step)s", step=label),
                _(
                    "<p>This step could not be completed automatically:</p><p>%(message)s</p>",
                    message=escape(str(message)),
                ),
                sequence,
            )
            sequence += 1
        for record, title, note in items:
            self._todo(record, title, note, sequence)
            sequence += 1
        self._todo(
            edition,
            _("Remove the practice competition"),
            _(
                "<p>When you are done, use <b>Remove practice competition</b> on the "
                "competition. It archives the competition and its sample clubs.</p>"
            ),
            sequence,
        )

    def action_create(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sports_federation_base.group_federation_manager"
        ):
            raise AccessError(
                _("Only federation managers can create practice competitions.")
            )
        dates = self._gameday_dates()
        venue = self._practice_venue()
        season = self._practice_season(dates[0], dates[-1])
        clubs = self._practice_clubs(self.teams_per_division)
        edition = self._create_competition(venue, season, dates)
        edition.sudo().write({"practice_club_ids": [fields.Command.set(clubs.ids)]})

        issues = []
        summary = {"published": 0, "waiting": [], "skipped": []}
        if self._run_step(
            issues, _("Teams & format"), self._setup_teams_and_format, edition, clubs
        ):
            if self._run_step(
                issues, _("Game days"), self._setup_gamedays, edition, venue, dates
            ):
                if self._run_step(
                    issues, _("Generate schedule"), self._generate_schedule, edition
                ):
                    summary = (
                        self._run_step(
                            issues,
                            _("Publish schedule"),
                            self._publish,
                            edition,
                            issues,
                        )
                        or summary
                    )
        self._assign_checklist(edition, issues, summary)

        message = _(
            "Practice competition created with %(divisions)s division(s), %(teams)s teams "
            "each and %(days)s game day(s). Your checklist is in your activities.",
            divisions=self.division_count,
            teams=self.teams_per_division,
            days=len(dates),
        )
        if issues:
            message += " " + _(
                "%(count)s step(s) need your attention.", count=len(issues)
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Practice competition ready"),
                "message": message,
                "type": "warning" if issues else "success",
                "sticky": bool(issues),
                "next": edition.action_open_competition_planner(),
            },
        }
