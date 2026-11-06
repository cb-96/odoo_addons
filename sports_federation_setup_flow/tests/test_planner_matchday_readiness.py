from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_matchday_readiness")
class TestPlannerMatchdayReadiness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "Planner Readiness Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Planner Readiness Competition", "competition_type": "league"}
        )
        empty_competition = cls.env["federation.competition"].create(
            {
                "name": "Planner Readiness Empty Competition",
                "competition_type": "league",
            }
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Planner Readiness Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        cls.empty_edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Planner Readiness Empty Edition",
                "competition_id": empty_competition.id,
                "season_id": season.id,
            }
        )
        venue = cls.env["federation.venue"].create({"name": "Planner Readiness Venue"})
        cls.matchday = cls.env["federation.matchday"].create(
            {
                "name": "Planner Readiness Game Day",
                "edition_id": cls.edition.id,
                "date": "2026-10-10",
                "venue_id": venue.id,
            }
        )

    def test_planner_shows_the_answer_of_the_authoritative_service(self):
        answer = self.edition.get_planner_matchday_readiness()
        self.assertTrue(answer["available"])
        self.assertEqual(
            answer["readiness"],
            self.env["federation.matchday.readiness"].evaluate(self.matchday),
        )

    def test_competition_without_game_days_has_nothing_to_report(self):
        self.assertEqual(
            self.empty_edition.get_planner_matchday_readiness(),
            {"available": True, "readiness": False},
        )

    def test_the_cheap_planner_payload_does_not_pay_for_game_day_checks(self):
        data = self.edition.get_competition_planner_data()
        self.assertNotIn("matchday_readiness", data)
        self.assertNotIn("matchday_readiness", data["operations"])
