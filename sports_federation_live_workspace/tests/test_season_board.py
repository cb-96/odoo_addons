from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_live_workspace", "sf_competition_formats")
class TestSeasonBoard(TransactionCase):
    """Moving matches between game days and time slots on the match board."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.write(
            {"group_ids": [(4, cls.env.ref("sports_federation_base.group_federation_manager").id)]}
        )
        season = cls.env["federation.season"].create(
            {"name": "Board 26-27", "date_start": "2026-09-01", "date_end": "2027-06-30"}
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Board League", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {"name": "Board Edition", "competition_id": competition.id, "season_id": season.id}
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "Board Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        club = cls.env["federation.club"].create({"name": "Board Club"})
        cls.teams = cls.env["federation.team"].create(
            [{"name": "Board Team %s" % i, "club_id": club.id} for i in range(1, 5)]
        )
        pset = cls.env["federation.participant.set"].create(
            {
                "name": "Board Participants",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        cls.env["federation.participant.set.line"].create(
            [
                {"participant_set_id": pset.id, "team_id": team.id, "seed": seed}
                for seed, team in enumerate(cls.teams, 1)
            ]
        )
        cls.structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Board Format",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "participant_set_id": pset.id,
                "format_type": "single_round_robin",
            }
        )
        cls.structure.action_generate()
        cls.structure.action_freeze()
        venue = cls.env["federation.venue"].create({"name": "Board Venue"})
        cls.courts = cls.env["federation.playing.area"].create(
            [{"name": "Board Court %s" % i, "venue_id": venue.id} for i in (1, 2)]
        )
        cls.days = cls.env["federation.matchday"].create(
            [
                {
                    "name": "Board Day %s" % index,
                    "edition_id": cls.edition.id,
                    "date": "2026-10-%02d" % (index * 7),
                    "venue_id": venue.id,
                    "planning_court_ids": [(6, 0, cls.courts.ids)],
                    "default_day_start_hour": 9.0,
                    "default_day_end_hour": 11.0,
                    "default_slot_duration_minutes": 60,
                }
                for index in (1, 2)
            ]
        )
        cls.board = cls.env["federation.season.board"]

    def _load(self):
        return self.board.load(self.edition.id)

    def _slots(self, day):
        return day.slot_ids.sorted(lambda slot: (slot.start_datetime, slot.court_id.id))

    def _fixture(self, data, fixture):
        return next(row for row in data["fixtures"] if row["id"] == fixture.id)

    def _ready(self):
        data = self._load()
        for day in self.days:
            data = self.board.generate_slots(self.edition.id, day.id, data["signature"])
        return data

    def test_everything_starts_in_the_list(self):
        data = self._ready()
        self.assertEqual(len(data["fixtures"]), 6)
        self.assertEqual(data["unplanned_count"], 6)
        self.assertEqual([len(day["slots"]) for day in data["days"]], [4, 4])

    def test_move_swap_undo_and_unplan(self):
        data = self._ready()
        first, second = self.structure.fixture_ids.sorted("id")[:2]
        slot_a, slot_b = self._slots(self.days[0])[:2]
        data = self.board.move(self.edition.id, first.id, slot_a.id, data["signature"])
        self.assertTrue(data["ok"])
        self.assertEqual(self._fixture(data, first)["slot_id"], slot_a.id)
        self.assertTrue(self._fixture(data, first)["pinned"])
        schedule = self.board._active_schedule(self.days[0])
        self.assertIn("board_move", schedule.change_ids.mapped("command"))
        self.assertIn(first, self.days[0].allocation_ids.mapped("fixture_ids"))

        # Dropping another match on a taken slot swaps: the first goes back to the list.
        data = self.board.move(self.edition.id, second.id, slot_a.id, data["signature"])
        self.assertEqual(self._fixture(data, second)["slot_id"], slot_a.id)
        self.assertFalse(self._fixture(data, first)["slot_id"])
        self.assertNotIn(first, self.days[0].allocation_ids.mapped("fixture_ids"))

        undo = data["changes"]
        data = self.board.restore(self.edition.id, undo, data["signature"])
        self.assertEqual(self._fixture(data, first)["slot_id"], slot_a.id)
        self.assertFalse(self._fixture(data, second)["slot_id"])

        # Moving to another game day takes the match off the first day.
        slot_c = self._slots(self.days[1])[0]
        data = self.board.move(self.edition.id, first.id, slot_c.id, data["signature"])
        self.assertEqual(self._fixture(data, first)["day_id"], self.days[1].id)
        self.assertNotIn(first, self.days[0].allocation_ids.mapped("fixture_ids"))

        data = self.board.unplan(self.edition.id, [first.id], data["signature"])
        self.assertFalse(self._fixture(data, first)["day_id"])
        self.assertEqual(data["unplanned_count"], 6)

    def test_moves_that_add_errors_are_refused(self):
        data = self._ready()
        team = self.teams[0]
        both = self.structure.fixture_ids.filtered(
            lambda fixture: team in (fixture.home_team_id | fixture.away_team_id)
        )[:2]
        same_time = self._slots(self.days[0]).filtered(
            lambda slot: slot.start_datetime == self._slots(self.days[0])[0].start_datetime
        )
        data = self.board.move(self.edition.id, both[0].id, same_time[0].id, data["signature"])
        result = self.board.move(self.edition.id, both[1].id, same_time[1].id, data["signature"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["rejected"])
        self.assertFalse(self._fixture(result, both[1])["slot_id"])

    def test_place_on_day_uses_fitting_slots(self):
        data = self._ready()
        fixtures = self.structure.fixture_ids.filtered(lambda f: f.round_number == 1)
        data = self.board.place_on_day(self.edition.id, fixtures.ids, self.days[0].id, data["signature"])
        placed = [row for row in data["fixtures"] if row["id"] in fixtures.ids and row["slot_id"]]
        self.assertEqual(len(placed), len(fixtures))
        self.assertFalse(any(row["pinned"] for row in placed))
        data = self.board.set_pinned(self.edition.id, fixtures[0].id, True, data["signature"])
        self.assertTrue(self._fixture(data, fixtures[0])["pinned"])

    def test_stale_board_and_locked_days(self):
        data = self._ready()
        fixture = self.structure.fixture_ids[:1]
        slot = self._slots(self.days[0])[0]
        with self.assertRaises(ValidationError):
            self.board.move(self.edition.id, fixture.id, slot.id, "stale")
        data = self.board.move(self.edition.id, fixture.id, slot.id, data["signature"])
        schedule = self.board._active_schedule(self.days[0])
        schedule.write({"state": "published"})
        data = self._load()
        self.assertTrue(next(day for day in data["days"] if day["id"] == self.days[0].id)["locked"])
        with self.assertRaises(ValidationError):
            self.board.unplan(self.edition.id, fixture.ids, data["signature"])

    def test_planner_schedule_step_opens_the_board(self):
        action = self.edition.action_open_planner_step("schedule")
        self.assertEqual(action["tag"], "federation_season_board")
