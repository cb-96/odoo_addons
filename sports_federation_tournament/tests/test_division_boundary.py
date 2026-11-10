from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_boundaries")
class TestDivisionBoundary(TransactionCase):
    def setUp(self):
        super().setUp()
        self.season = self.env["federation.season"].create(
            {
                "name": "Division Boundary Season",
                "date_start": "2098-01-01",
                "date_end": "2098-12-31",
            }
        )
        self.competition = self.env["federation.competition"].create(
            {"name": "Division Boundary Competition"}
        )
        self.edition = self.env["federation.competition.edition"].create(
            {
                "name": "Division Boundary Edition",
                "competition_id": self.competition.id,
                "season_id": self.season.id,
            }
        )

    def division(self, **values):
        vals = {"name": "Boundary Division", "edition_id": self.edition.id}
        vals.update(values)
        return self.env["federation.tournament"].create(vals)

    def test_server_creation_derives_scope_without_onchange(self):
        division = self.division()
        self.assertEqual(division.season_id, self.season)
        self.assertEqual(division.competition_id, self.competition)
        self.assertEqual(division.date_start, self.season.date_start)

    def test_context_default_edition_is_normalized(self):
        division = (
            self.env["federation.tournament"]
            .with_context(default_edition_id=self.edition.id)
            .create({"name": "Context Division"})
        )
        self.assertEqual(division.competition_id, self.competition)

    def test_conflicting_scope_is_rejected(self):
        other = self.env["federation.competition"].create({"name": "Other Competition"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.division(competition_id=other.id)
        division = self.division()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            division.write({"competition_id": other.id})

    def test_edition_cannot_reinterpret_existing_divisions(self):
        self.division()
        other = self.env["federation.competition"].create({"name": "Reinterpretation"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.edition.write({"competition_id": other.id})
        self.edition.write({"competition_id": self.competition.id})

    def test_division_cannot_detach(self):
        division = self.division()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            division.write({"edition_id": False})

    def test_legacy_standalone_history_remains(self):
        legacy = self.env["federation.tournament"].create(
            {
                "name": "Legacy Standalone",
                "date_start": "2098-04-01",
                "location": "Historical venue",
                "tournament_type": "single_day",
            }
        )
        self.assertFalse(legacy.edition_id)
        self.assertEqual(legacy.location, "Historical venue")

    def test_edition_write_does_not_reset_division_dates(self):
        division = self.division(date_start="2098-04-01")
        division.write({"edition_id": self.edition.id})
        self.assertEqual(str(division.date_start), "2098-04-01")

    def test_game_day_action_is_edition_scoped(self):
        if self.env.get("federation.matchday") is None:
            self.skipTest("Scheduling addon is not installed")
        action = self.division().action_open_division_game_days()
        self.assertEqual(action["domain"], [("edition_id", "=", self.edition.id)])

    def test_division_cannot_move_to_another_edition(self):
        division = self.division()
        competition = self.env["federation.competition"].create(
            {"name": "Another Division Competition"}
        )
        edition = self.env["federation.competition.edition"].create(
            {
                "name": "Another Edition",
                "competition_id": competition.id,
                "season_id": self.season.id,
            }
        )
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            division.write({"edition_id": edition.id})
