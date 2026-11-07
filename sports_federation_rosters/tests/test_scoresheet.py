from odoo.tests.common import TransactionCase, tagged

REPORT = "sports_federation_rosters.report_match_scoresheet"


@tagged("post_install", "-at_install")
class TestMatchScoresheet(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        club = cls.env["federation.club"].create({"name": "Sheet Club", "code": "SHC"})
        cls.home = cls.env["federation.team"].create(
            {"name": "Sheet Home", "club_id": club.id, "code": "SHH"}
        )
        cls.away = cls.env["federation.team"].create(
            {"name": "Sheet Away", "club_id": club.id, "code": "SHA"}
        )
        season = cls.env["federation.season"].create(
            {
                "name": "Sheet Season",
                "code": "SHS",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        tournament = cls.env["federation.tournament"].create(
            {
                "name": "Sheet Division",
                "code": "SHD",
                "season_id": season.id,
                "date_start": "2026-01-01",
            }
        )
        cls.match = (
            cls.env["federation.match"]
            .with_context(skip_auto_match_sheets=True)
            .create(
                {
                    "tournament_id": tournament.id,
                    "home_team_id": cls.home.id,
                    "away_team_id": cls.away.id,
                    "date_scheduled": "2026-11-15 13:30:00",
                }
            )
        )
        players = cls.env["federation.player"].create(
            [
                {
                    "first_name": first_name,
                    "last_name": "Player",
                    "gender": "male",
                    "club_id": club.id,
                }
                for first_name in ("Ten", "Two", "Out")
            ]
        )
        sheet = cls.env["federation.match.sheet"].create(
            {"match_id": cls.match.id, "team_id": cls.home.id, "side": "home"}
        )
        cls.env["federation.match.sheet.line"].create(
            [
                {
                    "match_sheet_id": sheet.id,
                    "player_id": players[0].id,
                    "jersey_number": "10",
                },
                {
                    "match_sheet_id": sheet.id,
                    "player_id": players[1].id,
                    "jersey_number": "2",
                    "is_captain": True,
                },
                {
                    "match_sheet_id": sheet.id,
                    "player_id": players[2].id,
                    "jersey_number": "1",
                    "crossed_out": True,
                },
            ]
        )

    def _values(self):
        return self.env["report." + REPORT]._get_report_values(self.match.ids)

    def test_prints_the_whole_gameday_line_up_in_shirt_order(self):
        sheet = self._values()["sheets"][0]
        home, away = sheet["teams"]
        self.assertEqual(home["name"], "Sheet Home")
        self.assertEqual(
            [row["number"] for row in home["players"][:3]], ["1", "2", "10"]
        )
        # Players crossed out for this match before printing stay on the
        # sheet, marked, because the sheet is the game-day line-up.
        crossed = [row["name"] for row in home["players"] if row["crossed_out"]]
        self.assertEqual(crossed, ["Out Player"])
        self.assertEqual(home["captain"], "Two Player")
        self.assertEqual(home["match_players"], 12)
        self.assertEqual(len(home["players"]), 14)
        # A team without a line-up still gets a complete blank grid.
        self.assertEqual(away["players"][0]["name"], "")
        self.assertEqual(len(away["players"]), 14)
        self.assertFalse(sheet["lineups_final"])

    def test_two_halves_of_fifteen_sets_and_wdbf_set_points(self):
        sheet = self._values()["sheets"][0]
        labels = [half["label"] for half in sheet["halves"]]
        self.assertEqual(labels, ["1st half", "2nd half"])
        self.assertEqual(sheet["halves"][1]["sets"][0], 16)
        self.assertEqual(sum(len(half["sets"]) for half in sheet["halves"]), 30)
        self.assertEqual(len(sheet["assistants"]), 5)
        # Without a configured competition the sheet uses WDBF 2 / 1 points.
        self.assertEqual((sheet["win_points"], sheet["draw_points"]), (2, 1))
        self.assertIn("barcode_type=QR", sheet["qr_src"])

    def test_report_renders(self):
        html, _format = self.env["ir.actions.report"]._render_qweb_html(
            REPORT, self.match.ids
        )
        html = html.decode()
        self.assertIn("Sheet Home", html)
        self.assertIn("Game-day line-up", html)
        self.assertIn("sf-crossed", html)
        self.assertIn("B1", html)
        self.assertIn("B2", html)
        self.assertIn("Tie-breaking set", html)
        self.assertIn("Line-up not approved when printed", html)
