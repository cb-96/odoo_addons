from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestFederationCompetition(TransactionCase):
    """Tests for federation.competition (template) and federation.competition.edition models."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "2025-2026",
                "date_start": "2025-09-01",
                "date_end": "2026-06-30",
            }
        )

    def test_create_competition(self):
        """Test creating a basic competition template."""
        comp = self.env["federation.competition"].create(
            {
                "name": "Premier League",
                "code": "PL",
                "competition_type": "league",
            }
        )
        self.assertEqual(comp.name, "Premier League")
        self.assertEqual(comp.code, "PL")
        self.assertEqual(comp.competition_type, "league")
        self.assertEqual(comp.state, "draft")

    def test_competition_state_transitions(self):
        """Test state transitions."""
        comp = self.env["federation.competition"].create(
            {
                "name": "Test Cup",
                "competition_type": "cup",
            }
        )
        self.assertEqual(comp.state, "draft")

        comp.action_activate()
        self.assertEqual(comp.state, "active")

        comp.action_close()
        self.assertEqual(comp.state, "closed")

        comp.action_draft()
        self.assertEqual(comp.state, "draft")

    def test_competition_code_unique(self):
        """Test that competition code must be unique."""
        self.env["federation.competition"].create(
            {
                "name": "Comp 1",
                "code": "UNIQUE",
            }
        )
        with self.assertRaises(ValidationError):
            self.env["federation.competition"].create(
                {
                    "name": "Comp 2",
                    "code": "UNIQUE",
                }
            )

    def test_competition_rule_set_link(self):
        """Test linking a competition to a rule set."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Standard Rules",
                "code": "STD",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        comp = self.env["federation.competition"].create(
            {
                "name": "League A",
                "competition_type": "league",
                "rule_set_id": rule_set.id,
            }
        )
        self.assertEqual(comp.rule_set_id, rule_set)

    def test_competition_edition_count(self):
        """Test edition count computation on competition template."""
        comp = self.env["federation.competition"].create(
            {
                "name": "Comp with Editions",
                "competition_type": "league",
            }
        )
        self.assertEqual(comp.edition_count, 0)

        # Create an edition linked to this competition
        self.env["federation.competition.edition"].create(
            {
                "name": "Comp 2025-2026",
                "competition_id": comp.id,
                "season_id": self.season.id,
            }
        )
        comp._compute_edition_count()
        self.assertEqual(comp.edition_count, 1)

    def test_create_edition(self):
        """Test creating a competition edition."""
        comp = self.env["federation.competition"].create(
            {
                "name": "League",
                "competition_type": "league",
            }
        )
        edition = self.env["federation.competition.edition"].create(
            {
                "name": "League 2025-2026",
                "competition_id": comp.id,
                "season_id": self.season.id,
            }
        )
        self.assertEqual(edition.competition_id, comp)
        self.assertEqual(edition.season_id, self.season)
        self.assertEqual(edition.state, "draft")
        self.assertEqual(edition.competition_type, "league")

    def test_edition_state_transitions(self):
        """Test edition state transitions."""
        comp = self.env["federation.competition"].create(
            {
                "name": "Cup",
                "competition_type": "cup",
            }
        )
        edition = self.env["federation.competition.edition"].create(
            {
                "name": "Cup 2025-2026",
                "competition_id": comp.id,
                "season_id": self.season.id,
            }
        )
        self.assertEqual(edition.state, "draft")
        edition.action_open()
        self.assertEqual(edition.state, "open")
        edition.action_start()
        self.assertEqual(edition.state, "in_progress")
        edition.action_close()
        self.assertEqual(edition.state, "closed")

    def test_edition_tournament_link(self):
        """Test linking tournaments (divisions) to an edition."""
        comp = self.env["federation.competition"].create(
            {
                "name": "League",
                "competition_type": "league",
            }
        )
        edition = self.env["federation.competition.edition"].create(
            {
                "name": "League 2025-2026",
                "competition_id": comp.id,
                "season_id": self.season.id,
            }
        )
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Division 1",
                "date_start": "2025-09-01",
                "edition_id": edition.id,
                "competition_id": comp.id,
            }
        )
        edition._compute_tournament_count()
        self.assertEqual(edition.tournament_count, 1)
        self.assertEqual(tournament.edition_id, edition)

    def test_season_tournament_fields_use_distinct_labels(self):
        """Season tournament relation and counter should not share the same label."""
        self.assertEqual(self.season._fields["tournament_ids"].string, "Tournaments")
        self.assertEqual(
            self.season._fields["tournament_count"].string, "Tournament Count"
        )

        self.env["federation.tournament"].create(
            {
                "name": "Season Tournament",
                "code": "ST01",
                "season_id": self.season.id,
                "date_start": "2025-09-01",
            }
        )

        self.assertEqual(self.season.tournament_count, 1)

    def test_tournament_open_requires_season(self):
        """Test that tournament open requires season."""
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Seasonless Tournament",
                "code": "SLT",
                "date_start": "2025-09-01",
            }
        )

        with self.assertRaises(ValidationError):
            tournament.action_open()

    def test_tournament_start_requires_stage_and_archive_rules(self):
        """Test that tournament start requires stage and archive rules."""
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Guarded Tournament",
                "code": "GT01",
                "season_id": self.season.id,
                "date_start": "2025-09-01",
            }
        )

        tournament.action_open()
        with self.assertRaises(ValidationError):
            tournament.action_start()

        self.env["federation.tournament.stage"].create(
            {
                "name": "Group Stage",
                "tournament_id": tournament.id,
                "stage_type": "group",
            }
        )
        tournament.action_start()
        self.assertEqual(tournament.state, "in_progress")

        with self.assertRaises(ValidationError):
            tournament.action_archive()

        tournament.action_close()
        tournament.action_archive()
        self.assertFalse(tournament.active)

        tournament.action_restore()
        self.assertTrue(tournament.active)

    def test_tournament_team_eligibility_uses_category_and_gender(self):
        """Test that tournament team eligibility uses category and gender."""
        club = self.env["federation.club"].create(
            {
                "name": "Eligibility Club",
                "code": "ELIGCLUB",
            }
        )
        eligible_team = self.env["federation.team"].create(
            {
                "name": "Eligible Team",
                "club_id": club.id,
                "code": "ET1",
                "category": "senior",
                "gender": "male",
            }
        )
        wrong_gender_team = self.env["federation.team"].create(
            {
                "name": "Wrong Gender Team",
                "club_id": club.id,
                "code": "ET2",
                "category": "senior",
                "gender": "female",
            }
        )
        wrong_category_team = self.env["federation.team"].create(
            {
                "name": "Wrong Category Team",
                "club_id": club.id,
                "code": "ET3",
                "category": "junior",
                "gender": "male",
            }
        )
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Senior Men Cup",
                "code": "SMC",
                "season_id": self.season.id,
                "date_start": "2025-09-01",
                "category": "senior",
                "gender": "male",
            }
        )

        self.assertTrue(tournament.is_team_allowed(eligible_team))
        self.assertFalse(tournament.is_team_allowed(wrong_gender_team))
        self.assertFalse(tournament.is_team_allowed(wrong_category_team))
        eligible_teams = tournament.search_eligible_teams(
            [
                (
                    "id",
                    "in",
                    [eligible_team.id, wrong_gender_team.id, wrong_category_team.id],
                ),
            ]
        )
        self.assertIn(eligible_team, eligible_teams)
        self.assertNotIn(wrong_gender_team, eligible_teams)
        self.assertNotIn(wrong_category_team, eligible_teams)

    def test_tournament_participant_rejects_ineligible_team(self):
        """Test that tournament participant rejects ineligible team."""
        club = self.env["federation.club"].create(
            {
                "name": "Participant Club",
                "code": "PARTCLUB",
            }
        )
        eligible_team = self.env["federation.team"].create(
            {
                "name": "Participant Eligible Team",
                "club_id": club.id,
                "code": "PET1",
                "category": "senior",
                "gender": "male",
            }
        )
        ineligible_team = self.env["federation.team"].create(
            {
                "name": "Participant Ineligible Team",
                "club_id": club.id,
                "code": "PET2",
                "category": "senior",
                "gender": "female",
            }
        )
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Participant Cup",
                "code": "PCUP",
                "season_id": self.season.id,
                "date_start": "2025-09-01",
                "gender": "male",
                "category": "senior",
            }
        )

        participant = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": tournament.id,
                "team_id": eligible_team.id,
            }
        )
        self.assertEqual(participant.team_id, eligible_team)

        with self.assertRaises(ValidationError):
            self.env["federation.tournament.participant"].create(
                {
                    "tournament_id": tournament.id,
                    "team_id": ineligible_team.id,
                }
            )

    def test_tournament_participant_backend_domain_uses_eligible_teams(self):
        """Test that tournament participant backend domain uses eligible teams."""
        club = self.env["federation.club"].create(
            {
                "name": "Domain Club",
                "code": "DOMAINCLUB",
            }
        )
        eligible_team = self.env["federation.team"].create(
            {
                "name": "Domain Eligible Team",
                "club_id": club.id,
                "code": "DET",
                "category": "senior",
                "gender": "male",
            }
        )
        ineligible_team = self.env["federation.team"].create(
            {
                "name": "Domain Ineligible Team",
                "club_id": club.id,
                "code": "DIT",
                "category": "senior",
                "gender": "female",
            }
        )
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Domain Cup",
                "code": "DCUP",
                "season_id": self.season.id,
                "date_start": "2025-09-01",
                "gender": "male",
                "category": "senior",
            }
        )

        participant = self.env["federation.tournament.participant"].new(
            {
                "tournament_id": tournament.id,
            }
        )
        participant._compute_team_selection()

        eligible_team_ids = participant.eligible_team_ids._origin.ids
        self.assertIn(eligible_team.id, eligible_team_ids)
        self.assertNotIn(ineligible_team.id, eligible_team_ids)

        available_team_ids = participant.available_team_ids._origin.ids
        self.assertIn(eligible_team.id, available_team_ids)
        self.assertNotIn(ineligible_team.id, available_team_ids)
        self.assertIn("Domain Ineligible Team", participant.excluded_team_feedback_html)

    def test_tournament_participant_backend_feedback_explains_duplicate_team(self):
        """Test that tournament participant backend feedback explains duplicate team."""
        club = self.env["federation.club"].create(
            {
                "name": "Duplicate Team Club",
                "code": "DUPCLUB",
            }
        )
        duplicate_team = self.env["federation.team"].create(
            {
                "name": "Existing Participant Team",
                "club_id": club.id,
                "code": "EXISTTEAM",
                "category": "senior",
                "gender": "male",
            }
        )
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Duplicate Participant Cup",
                "code": "DPCUP",
                "season_id": self.season.id,
                "date_start": "2025-09-01",
                "gender": "male",
                "category": "senior",
            }
        )
        self.env["federation.tournament.participant"].create(
            {
                "tournament_id": tournament.id,
                "team_id": duplicate_team.id,
            }
        )

        participant = self.env["federation.tournament.participant"].new(
            {
                "tournament_id": tournament.id,
            }
        )
        participant._compute_team_selection()

        self.assertNotIn(duplicate_team.id, participant.available_team_ids._origin.ids)
        self.assertIn(
            "A participant record already exists for this team.",
            participant.excluded_team_feedback_html,
        )
