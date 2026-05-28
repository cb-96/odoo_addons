from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestParticipantLifecycle(TransactionCase):
    """Tests for federation.tournament.participant state lifecycle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Participant Lifecycle Season",
                "date_start": "2025-09-01",
                "date_end": "2026-06-30",
            }
        )
        cls.club = cls.env["federation.club"].create({"name": "Participant Club"})
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Participant Test Tournament",
                "season_id": cls.season.id,
                "date_start": "2025-10-01",
            }
        )

    def _make_team(self, name="ParticipantTeam"):
        return self.env["federation.team"].create(
            {
                "name": name,
                "club_id": self.club.id,
            }
        )

    def _make_participant(self, team=None, **kwargs):
        vals = {
            "tournament_id": self.tournament.id,
            "team_id": (team or self._make_team()).id,
        }
        vals.update(kwargs)
        return self.env["federation.tournament.participant"].create(vals)

    def test_default_state_is_registered(self):
        p = self._make_participant()
        self.assertEqual(p.state, "registered")

    def test_action_confirm_transitions_to_confirmed(self):
        p = self._make_participant()
        p.action_confirm()
        self.assertEqual(p.state, "confirmed")

    def test_action_withdraw_transitions_to_withdrawn(self):
        p = self._make_participant()
        p.action_confirm()
        p.action_withdraw()
        self.assertEqual(p.state, "withdrawn")

    def test_re_confirm_after_withdrawal(self):
        """A participant can be re-confirmed after withdrawal."""
        p = self._make_participant()
        p.action_confirm()
        p.action_withdraw()
        p.action_confirm()
        self.assertEqual(p.state, "confirmed")

    def test_duplicate_participant_blocked(self):
        """Same team cannot be registered twice in the same tournament."""
        team = self._make_team("DupTeam")
        self._make_participant(team=team)
        with self.assertRaises(ValidationError):
            self._make_participant(team=team)

    def test_participant_name_computed(self):
        team = self._make_team("NamedTeam")
        p = self._make_participant(team=team)
        self.assertTrue(p.name)
        self.assertIn("NamedTeam", p.name)

    def test_different_teams_can_participate(self):
        team_a = self._make_team("TeamA")
        team_b = self._make_team("TeamB")
        p_a = self._make_participant(team=team_a)
        p_b = self._make_participant(team=team_b)
        self.assertNotEqual(p_a, p_b)
