from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_officiating_competition")
class TestCompetitionOfficiatingContract(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # This contract must be deterministic when the officiating addon is
        # tested in isolation. Do not depend on demo data or another test class
        # having created a tournament or club first.
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Unbacked Match Contract Tournament",
                "code": "OFF-CONTRACT",
                "date_start": "2026-01-01",
            }
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Officiating Contract Club", "code": "OFF-CONTRACT"}
        )

    def _create_unbacked_match(self, name):
        return self.env["federation.match"].create(
            {"name": name, "tournament_id": self.tournament.id}
        )

    def test_unbacked_match_cannot_receive_referee_assignment(self):
        match = self._create_unbacked_match("Standalone assignment match")
        referee = self.env["federation.referee"].create(
            {"name": "Fixture Guard Referee"}
        )
        assignment = self.env["federation.match.referee"].create(
            {"match_id": match.id, "referee_id": referee.id, "role": "head"}
        )
        with self.assertRaises(ValidationError):
            assignment._assert_fixture_backing_for_activation()

    def test_unbacked_match_cannot_receive_club_duty(self):
        match = self._create_unbacked_match("Standalone duty match")
        duty = self.env["federation.match.club.referee.duty"].create(
            {"match_id": match.id, "club_id": self.club.id, "role": "table"}
        )
        with self.assertRaises(ValidationError):
            duty._assert_fixture_backing_for_activation()
