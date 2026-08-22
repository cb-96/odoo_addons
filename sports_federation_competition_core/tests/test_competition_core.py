from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install", "sf_competition_core")
class TestCompetitionCore(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season=cls.env["federation.season"].create({"name":"Core 26-27","date_start":"2026-09-01","date_end":"2027-06-30"})
        competition=cls.env["federation.competition"].create({"name":"Core League","competition_type":"league"})
        cls.edition=cls.env["federation.competition.edition"].create({"name":"Core Edition","competition_id":competition.id,"season_id":season.id})
    def test_valid_lifecycle_records_events(self):
        self.edition.transition_engine_state("active")
        self.assertEqual(self.edition.engine_state,"active")
        self.assertEqual(self.edition.event_ids[:1].event_type,"competition_state_changed")
    def test_invalid_lifecycle_is_rejected(self):
        with self.assertRaises(ValidationError): self.edition.transition_engine_state("archived")
    def test_role_assignment_is_unique(self):
        vals={"edition_id":self.edition.id,"role":"schedule_planner","user_id":self.env.user.id}
        self.env["federation.competition.role.assignment"].create(vals)
        with self.assertRaises(Exception):
            with self.env.cr.savepoint(): self.env["federation.competition.role.assignment"].create(vals)
