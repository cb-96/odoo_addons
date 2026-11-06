from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_gameday_overview")
class TestGamedayOverview(TransactionCase):
    """Roster -> game day -> line-up: what clubs see as current, past and next."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        today = fields.Date.context_today(env["federation.season"])
        cls.today = today
        Season = env["federation.season"]
        cls.season = Season.create(
            {
                "name": "Overview Current Season",
                "code": "OVS-NOW",
                "date_start": today - timedelta(days=100),
                "date_end": today + timedelta(days=100),
                "state": "open",
            }
        )
        # Ended long ago but nobody closed it: still history for clubs.
        cls.ended_season = Season.create(
            {
                "name": "Overview Ended Season",
                "code": "OVS-ENDED",
                "date_start": today - timedelta(days=400),
                "date_end": today - timedelta(days=200),
                "state": "open",
            }
        )
        cls.closed_season = Season.create(
            {
                "name": "Overview Closed Season",
                "code": "OVS-CLOSED",
                "date_start": today - timedelta(days=100),
                "date_end": today + timedelta(days=100),
                "state": "closed",
            }
        )
        club = env["federation.club"].create({"name": "Overview Club", "code": "OVC"})
        cls.club = club
        cls.team = env["federation.team"].create(
            {"name": "Overview Team", "club_id": club.id, "code": "OVT"}
        )
        cls.tournament = env["federation.tournament"].create(
            {
                "name": "Overview Tournament",
                "code": "OVTOUR",
                "season_id": cls.season.id,
                "date_start": today - timedelta(days=100),
            }
        )
        cls.ended_tournament = env["federation.tournament"].create(
            {
                "name": "Overview Ended Tournament",
                "code": "OVTOUR-OLD",
                "season_id": cls.ended_season.id,
                "date_start": today - timedelta(days=400),
            }
        )
        Match = env["federation.match"].with_context(skip_auto_match_sheets=True)

        def make_match(tournament, day_offset, hour):
            day = today + timedelta(days=day_offset)
            return Match.create(
                {
                    "tournament_id": tournament.id,
                    # Home team only: an opponent without a roster would trip the
                    # roster-deadline rule, which is not what is tested here.
                    "home_team_id": cls.team.id,
                    "date_scheduled": "%s %02d:00:00" % (day, hour),
                }
            )

        cls.rule_set = env["federation.rule.set"].create(
            {
                "name": "Overview Rules",
                "code": "OVERVIEW-RULES",
                "squad_min_size": 1,
                "gameday_roster_max_size": 3,
            }
        )
        cls.roster = env["federation.team.roster"].create(
            {
                "name": "Overview Season Roster",
                "team_id": cls.team.id,
                "season_id": cls.season.id,
                "rule_set_id": cls.rule_set.id,
            }
        )
        player = env["federation.player"].create(
            {
                "name": "Overview Player",
                "first_name": "Overview",
                "last_name": "Player",
                "gender": "male",
            }
        )
        cls.roster_line = env["federation.team.roster.line"].create(
            {"roster_id": cls.roster.id, "player_id": player.id}
        )
        cls.roster.action_activate()
        cls.old_roster = env["federation.team.roster"].create(
            {
                "name": "Overview Ended Roster",
                "team_id": cls.team.id,
                "season_id": cls.ended_season.id,
            }
        )

        Sheet = env["federation.match.sheet"]

        def make_sheet(match):
            return Sheet.create(
                {"match_id": match.id, "team_id": cls.team.id, "side": "home"}
            )

        cls.first_sheet = make_sheet(make_match(cls.tournament, 7, 10))
        cls.second_sheet = make_sheet(make_match(cls.tournament, 7, 14))
        cls.past_sheet = make_sheet(make_match(cls.tournament, -10, 10))
        cls.other_season_sheet = make_sheet(make_match(cls.ended_tournament, 8, 10))
        cls.sheets = (
            cls.first_sheet | cls.second_sheet | cls.past_sheet | cls.other_season_sheet
        )

    # ── seasons ──────────────────────────────────────────────────────────

    def test_only_running_seasons_are_current(self):
        current = self.env["federation.team.roster"]._portal_current_season_ids()
        self.assertIn(self.season.id, current)
        self.assertNotIn(self.ended_season.id, current)
        self.assertNotIn(self.closed_season.id, current)

    def test_closing_a_season_closes_its_active_rosters(self):
        self.assertEqual(self.roster.status, "active")
        self.season.action_close()
        self.assertEqual(self.roster.status, "closed")

    def test_cancelling_a_season_closes_its_active_rosters(self):
        self.season.action_cancel()
        self.assertEqual(self.roster.status, "closed")

    # ── game days ────────────────────────────────────────────────────────

    def test_upcoming_and_past_domains_split_the_sheets(self):
        Sheet = self.env["federation.match.sheet"]
        gameday = self.env["federation.portal.gameday"]
        scope = [("id", "in", self.sheets.ids)]
        upcoming = Sheet.search(scope + gameday.upcoming_domain())
        past = Sheet.search(scope + gameday.past_domain())
        self.assertEqual(
            upcoming, self.first_sheet | self.second_sheet | self.other_season_sheet
        )
        self.assertEqual(past, self.past_sheet)

    def test_matches_of_one_day_form_one_game_day(self):
        gameday = self.env["federation.portal.gameday"]
        rows = gameday.group_gamedays(self.first_sheet | self.second_sheet)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["matches"], 2)
        self.assertEqual(row["state"], "not_started")
        self.assertTrue(row["needs_action"])
        self.assertEqual(row["selected"], 0)

        self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": self.first_sheet.id,
                "player_id": self.roster_line.player_id.id,
                "roster_line_id": self.roster_line.id,
            }
        )
        row = gameday.group_gamedays(self.first_sheet | self.second_sheet)[0]
        self.assertEqual(row["state"], "draft")
        self.assertEqual(row["selected"], 1)
        self.assertEqual(row["limit"], 3)
        self.assertEqual(row["url"], "/my/match-sheets/%s" % row["sheet"].id)

    def test_game_days_are_ordered_soonest_first_and_earlier_latest_first(self):
        gameday = self.env["federation.portal.gameday"]
        later = self.other_season_sheet
        rows = gameday.group_gamedays(self.first_sheet | later, upcoming=True)
        self.assertEqual([row["sheet"] for row in rows], [self.first_sheet, later])
        rows = gameday.group_gamedays(self.first_sheet | later, upcoming=False)
        self.assertEqual([row["sheet"] for row in rows], [later, self.first_sheet])

    # ── what a club representative sees on the roster page ───────────────

    def _club_user(self):
        env = self.env
        user = env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Overview Rep",
                "login": "overview_rep_test",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            env.ref(
                                "sports_federation_portal.group_federation_portal_club"
                            ).id
                        ],
                    )
                ],
            }
        )
        role = env["federation.club.role.type"].create(
            {"name": "Overview role", "code": "overview_test_role"}
        )
        env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": user.partner_id.id,
                "user_id": user.id,
                "role_type_id": role.id,
            }
        )
        return user

    def test_roster_page_lists_only_its_own_season_game_days(self):
        user = self._club_user()
        gameday = self.env["federation.portal.gameday"]
        upcoming = gameday.roster_gamedays(self.roster, user=user, upcoming=True)
        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0]["matches"], 2)
        earlier = gameday.roster_gamedays(self.roster, user=user, upcoming=False)
        self.assertEqual([row["sheet"] for row in earlier], [self.past_sheet])

    # ── which rosters a line-up may use ──────────────────────────────────

    def test_line_up_only_offers_rosters_of_the_same_season(self):
        gameday = self.env["federation.portal.gameday"]
        rosters = gameday.lineup_rosters(self.first_sheet, user=self.env.user)
        self.assertIn(self.roster, rosters)
        self.assertNotIn(self.old_roster, rosters)
        self.assertEqual(
            gameday.default_lineup_roster(self.first_sheet, rosters), self.roster
        )

    def test_an_already_linked_roster_stays_selectable(self):
        gameday = self.env["federation.portal.gameday"]
        self.first_sheet.write({"roster_id": self.old_roster.id})
        rosters = gameday.lineup_rosters(self.first_sheet, user=self.env.user)
        self.assertIn(self.old_roster, rosters)
        self.assertEqual(
            gameday.default_lineup_roster(self.first_sheet, rosters), self.old_roster
        )

    # ── sheets created before the team had a roster ──────────────────────

    def test_game_days_do_not_depend_on_the_roster_link(self):
        """A sheet made with its match has no roster yet but is still a game day."""
        gameday = self.env["federation.portal.gameday"]
        self.assertFalse((self.first_sheet | self.second_sheet).mapped("roster_id"))
        sheets = gameday.team_sheets(self.team, self.season, user=self.env.user)
        self.assertEqual(sheets, self.first_sheet | self.second_sheet)
        # The other season's sheet is not part of this season's game days.
        self.assertNotIn(self.other_season_sheet, sheets)
        rows = gameday.group_gamedays(sheets)
        self.assertEqual(len(rows), 1)
        # The row names the roster the line-up will start from.
        self.assertEqual(rows[0]["roster"], self.roster)
        self.assertFalse(rows[0]["roster_linked"])

    def test_season_domain_uses_the_match_division_not_the_roster(self):
        Sheet = self.env["federation.match.sheet"]
        gameday = self.env["federation.portal.gameday"]
        found = Sheet.search(
            [("id", "in", self.sheets.ids)] + gameday.season_domain(self.season)
        )
        self.assertEqual(found, self.first_sheet | self.second_sheet | self.past_sheet)

    def test_new_roster_links_the_open_draft_sheets_of_its_season(self):
        env = self.env
        late_team = env["federation.team"].create(
            {"name": "Overview Late Team", "club_id": self.club.id, "code": "OVL"}
        )
        Match = env["federation.match"].with_context(skip_auto_match_sheets=True)
        Sheet = env["federation.match.sheet"]

        def sheet_for(tournament, offset):
            match = Match.create(
                {
                    "tournament_id": tournament.id,
                    "home_team_id": late_team.id,
                    "date_scheduled": "%s 10:00:00" % (self.today + timedelta(days=offset)),
                }
            )
            return Sheet.create({"match_id": match.id, "team_id": late_team.id, "side": "home"})

        # Far enough ahead that the roster deadline has not been reached yet.
        this_season = sheet_for(self.tournament, 40)
        other_season = sheet_for(self.ended_tournament, 40)
        self.assertFalse(this_season.roster_id | other_season.roster_id)

        roster = env["federation.team.roster"].create(
            {
                "name": "Overview Late Roster",
                "team_id": late_team.id,
                "season_id": self.season.id,
            }
        )
        self.assertEqual(this_season.roster_id, roster)
        self.assertFalse(other_season.roster_id)

    def test_new_roster_keeps_the_roster_a_sheet_already_has(self):
        sheet = self.first_sheet
        sheet.write({"roster_id": self.roster.id})
        other = self.env["federation.team.roster"].create(
            {
                "name": "Overview Second Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
                "competition_id": False,
            }
        )
        self.assertEqual(sheet.roster_id, self.roster)
        self.assertNotEqual(other, sheet.roster_id)
