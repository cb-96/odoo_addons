import hashlib
import json

from odoo.tests.common import TransactionCase


class TestGamedayLineupWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Lineup Wizard Season",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Lineup Wizard League", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Lineup Wizard Edition",
                "competition_id": competition.id,
                "season_id": cls.season.id,
                "workflow_mode": "simple",
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Lineup Wizard Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": cls.season.id,
                "date_start": "2024-01-01",
            }
        )
        club = cls.env["federation.club"].create({"name": "Lineup Wizard Club"})
        cls.home = cls.env["federation.team"].create(
            {"name": "Lineup Wizard Home", "club_id": club.id}
        )
        cls.away = cls.env["federation.team"].create(
            {"name": "Lineup Wizard Away", "club_id": club.id}
        )
        participant_set = cls.env["federation.participant.set"].create(
            {
                "name": "Lineup Wizard Participants",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
                "state": "finalized",
            }
        )
        structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Lineup Wizard Structure",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
                "participant_set_id": participant_set.id,
                "format_type": "custom",
            }
        )
        venue = cls.env["federation.venue"].create({"name": "Lineup Wizard Venue"})
        cls.matchday = cls.env["federation.matchday"].create(
            {
                "name": "Lineup Wizard Day",
                "edition_id": cls.edition.id,
                "date": "2024-06-15",
                "venue_id": venue.id,
                "state": "scheduled",
            }
        )
        schedule = cls.env["federation.schedule"].create(
            {
                "name": "Lineup Wizard Schedule",
                "edition_id": cls.edition.id,
                "structure_id": structure.id,
                "matchday_id": cls.matchday.id,
                "state": "published",
            }
        )
        snapshot = [{"fixture_id": 1}]
        digest = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        review = cls.env["federation.schedule.review"].sudo().create(
            {
                "schedule_id": schedule.id,
                "submitted_revision": schedule.revision,
                "state": "approved",
                "assignment_snapshot": snapshot,
                "snapshot_digest": digest,
                "submitted_by_id": cls.env.user.id,
            }
        )
        publication = cls.env["federation.schedule.publication"].sudo().create(
            {
                "schedule_id": schedule.id,
                "version": 1,
                "assignment_snapshot": snapshot,
                "snapshot_digest": digest,
                "source_revision": schedule.revision,
                "review_id": review.id,
            }
        )
        cls.matchday.sudo().write({"current_publication_id": publication.id})
        for kickoff in ("2024-06-15 10:00:00", "2024-06-15 14:00:00"):
            match = cls.env["federation.match"].create(
                {
                    "tournament_id": cls.division.id,
                    "home_team_id": cls.home.id,
                    "away_team_id": cls.away.id,
                    "date_scheduled": kickoff,
                    "state": "scheduled",
                }
            )
            match.sudo().write({"schedule_publication_id": publication.id})
        player = cls.env["federation.player"].create(
            {"name": "Lineup Wizard Player", "first_name": "Lineup", "last_name": "Player"}
        )
        rule_set = cls.env["federation.rule.set"].create(
            {"name": "Lineup Wizard Rules", "code": "LINEUP-WIZ", "squad_min_size": 1}
        )
        cls.roster = cls.env["federation.team.roster"].create(
            {
                "team_id": cls.home.id,
                "season_id": cls.season.id,
                "competition_id": competition.id,
                "rule_set_id": rule_set.id,
            }
        )
        cls.env["federation.team.roster.line"].create(
            {"roster_id": cls.roster.id, "player_id": player.id, "jersey_number": "7"}
        )
        cls.roster.action_activate()

    def test_one_wizard_prepares_and_streamlines_shared_gameday_lineup(self):
        action = self.matchday.action_prepare_lineups()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        wizard.team_id = self.home
        wizard._onchange_team_id()

        wizard.action_save_submit()

        sheets = self.env["federation.match.sheet"].search(
            [
                ("match_id.schedule_publication_id.matchday_id", "=", self.matchday.id),
                ("team_id", "=", self.home.id),
            ]
        )
        self.assertEqual(len(sheets), 2)
        self.assertEqual(set(sheets.mapped("state")), {"approved"})
        self.assertEqual(set(sheets.mapped("line_ids.player_id").ids), set(self.roster.line_ids.player_id.ids))

    def test_independent_review_keeps_shared_lineup_submitted(self):
        self.edition.write({"workflow_mode": "controlled"})
        action = self.matchday.action_prepare_lineups()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        wizard.team_id = self.home
        wizard._onchange_team_id()

        wizard.action_save_submit()

        sheets = self.env["federation.match.sheet"].search(
            [
                ("match_id.schedule_publication_id.matchday_id", "=", self.matchday.id),
                ("team_id", "=", self.home.id),
            ]
        )
        self.assertEqual(set(sheets.mapped("state")), {"submitted"})
