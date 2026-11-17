import hashlib
import json

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_handoffs")
class TestMatchJourney(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "Journey Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Journey Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Journey Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "Journey Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        participants = cls.env["federation.participant.set"].create(
            {
                "name": "Journey Participants",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        cls.structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Journey Structure",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "participant_set_id": participants.id,
                "format_type": "custom",
            }
        )
        cls.venue = cls.env["federation.venue"].create({"name": "Journey Venue"})
        cls.days = cls.env["federation.matchday"].create(
            [
                {
                    "name": "Day A",
                    "edition_id": cls.edition.id,
                    "date": "2026-10-03",
                    "venue_id": cls.venue.id,
                    "state": "capacity_ready",
                },
                {
                    "name": "Day B",
                    "edition_id": cls.edition.id,
                    "date": "2026-10-10",
                    "venue_id": cls.venue.id,
                    "state": "capacity_ready",
                },
            ]
        )

    @staticmethod
    def _digest(snapshot):
        payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _snapshot():
        # Odoo stores an explicitly empty required Json value as NULL.
        return [{"fixture_id": 1}]

    def _schedule_review(self, day, suffix):
        snapshot = self._snapshot()
        schedule = self.env["federation.schedule"].create(
            {
                "name": f"Schedule {suffix}",
                "edition_id": self.edition.id,
                "structure_id": self.structure.id,
                "matchday_id": day.id,
                "state": "approved",
            }
        )
        review = (
            self.env["federation.schedule.review"]
            .sudo()
            .create(
                {
                    "schedule_id": schedule.id,
                    "submitted_revision": schedule.revision,
                    "state": "pending",
                    "assignment_snapshot": snapshot,
                    "snapshot_digest": self._digest(snapshot),
                    "submitted_by_id": self.env.user.id,
                }
            )
        )
        return schedule, review

    def _create_ready_roster(self, team, suffix):
        if not self.env.get("federation.player") or not self.env.get(
            "federation.team.roster"
        ):
            self.skipTest(
                "Roster publication checks require the optional people and rosters addons."
            )
        player = self.env["federation.player"].create(
            {
                "first_name": f"{suffix} {team.name}",
                "last_name": "Roster Player",
                "gender": team.gender,
                "club_id": team.club_id.id,
                "birth_date": "2000-01-01",
            }
        )
        roster = self.env["federation.team.roster"].create(
            {
                "name": f"{suffix} {team.name} Roster",
                "team_id": team.id,
                "season_id": self.edition.season_id.id,
            }
        )
        registration = self.env["federation.club.season.registration"]._get_or_create(
            team.club_id, self.edition.season_id
        )
        registration.billing_partner_id = self.env["res.partner"].create(
            {"name": "Journey Billing Contact"}
        )
        self.env["federation.player.license"].create(
            {
                "player_id": player.id,
                "club_id": team.club_id.id,
                "season_id": self.edition.season_id.id,
                "state": "active",
                "issue_date": self.edition.season_id.date_start,
                "expiry_date": self.edition.season_id.date_end,
            }
        )
        self.env["federation.team.roster.line"].create(
            {"roster_id": roster.id, "player_id": player.id}
        )
        roster.action_activate()
        # A publishable schedule fixture must satisfy roster readiness itself.
        # Keep the production scheduling guard active in publication tests.
        self.assertEqual(roster.status, "active")
        return roster

    def _valid_schedule_review(self, day, suffix):
        stage = self.env["federation.structure.stage"].create(
            {
                "name": f"Journey Stage {suffix}",
                "structure_id": self.structure.id,
                "stage_type": "league",
            }
        )
        club = self.env["federation.club"].create({"name": f"Journey Club {suffix}"})
        teams = self.env["federation.team"].create(
            [
                {"name": f"Journey Home {suffix}", "club_id": club.id},
                {"name": f"Journey Away {suffix}", "club_id": club.id},
            ]
        )
        rosters = [self._create_ready_roster(team, suffix) for team in teams]
        for team, roster in zip(teams, rosters):
            self.assertEqual(roster.team_id, team)
            self.assertEqual(roster.season_id, self.edition.season_id)
            self.assertFalse(roster._get_readiness_issues(reference_date=day.date))
        fixture = self.env["federation.fixture"].create(
            {
                "structure_id": self.structure.id,
                "stage_id": stage.id,
                "round_number": 1,
                "home_team_id": teams[0].id,
                "away_team_id": teams[1].id,
                "state": "ready",
            }
        )
        area = self.env["federation.playing.area"].create(
            {"name": f"Journey Court {suffix}", "venue_id": self.venue.id}
        )
        slot = self.env["federation.schedule.slot"].create(
            {
                "matchday_id": day.id,
                "court_id": area.id,
                "start_datetime": "2026-10-03 09:00:00",
                "end_datetime": "2026-10-03 09:40:00",
            }
        )
        self.env["federation.matchday.allocation"].create(
            {
                "matchday_id": day.id,
                "structure_id": self.structure.id,
                "stage_id": stage.id,
                "round_number": 1,
            }
        )
        schedule = self.env["federation.schedule"].create(
            {
                "name": f"Valid Schedule {suffix}",
                "edition_id": self.edition.id,
                "structure_id": self.structure.id,
                "matchday_id": day.id,
            }
        )
        self.env["federation.schedule.assignment"].create(
            {
                "schedule_id": schedule.id,
                "fixture_id": fixture.id,
                "slot_id": slot.id,
            }
        )
        schedule.state = "approved"
        commands = self.env["federation.schedule.approval.commands"]
        snapshot = commands._snapshot(schedule)
        review = (
            self.env["federation.schedule.review"]
            .sudo()
            .create(
                {
                    "schedule_id": schedule.id,
                    "submitted_revision": schedule.revision,
                    "state": "pending",
                    "assignment_snapshot": snapshot,
                    "snapshot_digest": commands._digest(snapshot),
                    "submitted_by_id": self.env.user.id,
                }
            )
        )
        return schedule, review

    def test_publication_replay_returns_same_publication(self):
        schedule, review = self._valid_schedule_review(self.days[0], "Replay")
        commands = self.env["federation.schedule.approval.commands"]
        publication = commands.publish(schedule.id)
        replay = commands.publish(schedule.id, expected_publication_id=publication.id)
        self.assertEqual(replay, publication)
        self.assertEqual(schedule.matchday_id.current_publication_id, publication)

    def test_published_match_schedule_is_not_directly_editable(self):
        schedule, review = self._valid_schedule_review(self.days[0], "Guard")
        self.env["federation.schedule.approval.commands"].publish(schedule.id)
        match = schedule.assignment_ids[0].fixture_id.operational_match_id
        self.assertTrue(match)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            match.write({"scheduled_time": 22.0})
        action = match.action_open_match_workspace()
        self.assertEqual(action["res_model"], "federation.fixture")

    def test_stale_reschedule_dialog_rejected_without_revision(self):
        schedule, review = self._valid_schedule_review(self.days[0], "Stale")
        self.env["federation.schedule.approval.commands"].publish(schedule.id)
        fixture = schedule.assignment_ids[0].fixture_id
        action = fixture.action_reschedule_from_workspace()
        wizard = self.env["federation.match.reschedule.wizard"].browse(action["res_id"])
        wizard.expected_publication_id = 0
        wizard.reason = "Reviewed move"
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            wizard.action_prepare_amendment()
        self.assertFalse(schedule.superseded_by_id)

    def test_noop_reschedule_does_not_create_revision(self):
        schedule, review = self._valid_schedule_review(self.days[0], "Noop")
        self.env["federation.schedule.approval.commands"].publish(schedule.id)
        action = schedule.assignment_ids[
            0
        ].fixture_id.action_reschedule_from_workspace()
        wizard = self.env["federation.match.reschedule.wizard"].browse(action["res_id"])
        wizard.reason = "No move"
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            wizard.action_prepare_amendment()
        self.assertFalse(schedule.superseded_by_id)

    def test_valid_move_prepares_revision_without_changing_live_match(self):
        schedule, review = self._valid_schedule_review(self.days[0], "Move")
        publication = self.env["federation.schedule.approval.commands"].publish(
            schedule.id
        )
        assignment = schedule.assignment_ids[0]
        match = assignment.fixture_id.operational_match_id
        original_date = match.date_scheduled
        target = self.env["federation.schedule.slot"].create(
            {
                "matchday_id": schedule.matchday_id.id,
                "court_id": assignment.slot_id.court_id.id,
                "start_datetime": "2026-10-03 11:00:00",
                "end_datetime": "2026-10-03 11:40:00",
            }
        )
        action = assignment.fixture_id.action_reschedule_from_workspace()
        wizard = self.env["federation.match.reschedule.wizard"].browse(action["res_id"])
        wizard.write({"slot_id": target.id, "reason": "Reviewed venue timing change"})
        result = wizard.action_prepare_amendment()
        revision = self.env["federation.schedule"].browse(result["res_id"])
        self.assertEqual(revision.assignment_ids[0].slot_id, target)
        self.assertEqual(schedule.matchday_id.current_publication_id, publication)
        self.assertEqual(match.date_scheduled, original_date)

    def test_canonical_kickoff_write_cannot_bypass_schedule(self):
        schedule, review = self._valid_schedule_review(self.days[0], "Canonical")
        self.env["federation.schedule.approval.commands"].publish(schedule.id)
        match = schedule.assignment_ids[0].fixture_id.operational_match_id
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            match.write({"date_scheduled": "2026-10-03 22:00:00"})

    def test_planning_token_is_the_only_bypass(self):
        from odoo.addons.sports_federation_schedule_approval.planning_tokens import (
            PUBLISHED_PLANNING_CONTEXT_KEY,
            with_published_planning_token,
        )

        schedule, review = self._valid_schedule_review(self.days[0], "Token")
        self.env["federation.schedule.approval.commands"].publish(schedule.id)
        match = schedule.assignment_ids[0].fixture_id.operational_match_id
        forged = match.with_context(**{PUBLISHED_PLANNING_CONTEXT_KEY: True})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            forged.write({"date_scheduled": "2026-10-03 21:00:00"})
        with_published_planning_token(match).write(
            {"date_scheduled": "2026-10-03 10:00:00"}
        )
        self.assertEqual(str(match.date_scheduled), "2026-10-03 10:00:00")
