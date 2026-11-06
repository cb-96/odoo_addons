from unittest import mock

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_auto_club_duties")
class TestAutoClubDutyAssignment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "Duty Season",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Duty Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Duty Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "Duty Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-06-01",
            }
        )
        participant_set = cls.env["federation.participant.set"].create(
            {
                "name": "Duty Participants",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Duty Structure",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "participant_set_id": participant_set.id,
                "format_type": "custom",
            }
        )
        stage = cls.env["federation.structure.stage"].create(
            {"name": "Duty Stage", "structure_id": structure.id, "stage_type": "league"}
        )
        clubs = cls.env["federation.club"].create(
            [{"name": f"Duty Club {code}", "code": f"DUTY-{code}"} for code in "ABCDE"]
        )
        teams = cls.env["federation.team"].create(
            [
                {
                    "name": f"Duty Team {code}",
                    "code": f"DUTY-T-{code}",
                    "club_id": club.id,
                }
                for code, club in zip("ABCDE", clubs)
            ]
        )
        fixtures = cls.env["federation.fixture"].create(
            [
                {
                    "structure_id": structure.id,
                    "stage_id": stage.id,
                    "round_number": 1,
                    "home_team_id": teams[0].id,
                    "away_team_id": teams[1].id,
                    "state": "ready",
                },
                {
                    "structure_id": structure.id,
                    "stage_id": stage.id,
                    "round_number": 1,
                    "home_team_id": teams[2].id,
                    "away_team_id": teams[3].id,
                    "state": "ready",
                },
                {
                    "structure_id": structure.id,
                    "stage_id": stage.id,
                    "round_number": 1,
                    "home_team_id": teams[4].id,
                    "away_team_id": teams[0].id,
                    "state": "ready",
                },
            ]
        )
        venue = cls.env["federation.venue"].create({"name": "Duty Venue"})
        cls.matchday = cls.env["federation.matchday"].create(
            {
                "name": "Duty Day",
                "edition_id": cls.edition.id,
                "date": "2026-06-20",
                "venue_id": venue.id,
            }
        )
        courts = cls.env["federation.playing.area"].create(
            [
                {"name": "Duty Court 1", "venue_id": venue.id},
                {"name": "Duty Court 2", "venue_id": venue.id},
            ]
        )
        slots = cls.env["federation.schedule.slot"].create(
            [
                {
                    "matchday_id": cls.matchday.id,
                    "court_id": courts[0].id,
                    "start_datetime": "2026-06-20 10:00:00",
                    "end_datetime": "2026-06-20 11:00:00",
                },
                {
                    "matchday_id": cls.matchday.id,
                    "court_id": courts[1].id,
                    "start_datetime": "2026-06-20 10:00:00",
                    "end_datetime": "2026-06-20 11:00:00",
                },
                {
                    "matchday_id": cls.matchday.id,
                    "court_id": courts[0].id,
                    "start_datetime": "2026-06-20 12:00:00",
                    "end_datetime": "2026-06-20 13:00:00",
                },
            ]
        )
        schedule = cls.env["federation.schedule"].create(
            {
                "name": "Duty Schedule",
                "edition_id": cls.edition.id,
                "structure_id": structure.id,
                "matchday_id": cls.matchday.id,
            }
        )
        assignments = cls.env["federation.schedule.assignment"].create(
            [
                {
                    "schedule_id": schedule.id,
                    "fixture_id": fixture.id,
                    "slot_id": slot.id,
                }
                for fixture, slot in zip(fixtures, slots)
            ]
        )
        cls.env["federation.fixture.materializer"].sudo().materialize(fixtures)
        snapshot = cls.env["federation.schedule.approval.commands"]._snapshot(schedule)
        review = (
            cls.env["federation.schedule.review"]
            .sudo()
            .create(
                {
                    "schedule_id": schedule.id,
                    "submitted_revision": schedule.revision,
                    "state": "pending",
                    "assignment_snapshot": snapshot,
                    "snapshot_digest": cls.env[
                        "federation.schedule.approval.commands"
                    ]._digest(snapshot),
                    "submitted_by_id": cls.env.user.id,
                }
            )
        )
        publication = (
            cls.env["federation.schedule.publication"]
            .sudo()
            .create(
                {
                    "schedule_id": schedule.id,
                    "version": 1,
                    "assignment_snapshot": snapshot,
                    "snapshot_digest": cls.env[
                        "federation.schedule.approval.commands"
                    ]._digest(snapshot),
                    "source_revision": schedule.revision,
                    "review_id": review.id,
                }
            )
        )
        cls.matches = fixtures.mapped("operational_match_id")
        for assignment in assignments:
            assignment.fixture_id.operational_match_id.sudo().write(
                {
                    "published_slot_id": assignment.slot_id.id,
                    "schedule_publication_id": publication.id,
                    "date_scheduled": assignment.slot_id.start_datetime,
                }
            )
        cls.matchday.sudo().write({"current_publication_id": publication.id})
        cls.clubs = clubs

    def test_prefers_non_playing_club_and_creates_four_roles(self):
        volunteer = self.env["federation.referee"].create({"name": "Volunteer Head"})
        self.env["federation.match.referee"].create(
            {"match_id": self.matches[0].id, "referee_id": volunteer.id, "role": "head"}
        )
        wizard = self.env["federation.matchday.assign.official.wizard"].create(
            {
                "matchday_id": self.matchday.id,
                "assignment_type": "auto_club",
                "officials_per_match": 4,
                "preserve_existing_assignments": True,
                "avoid_clubs_playing_same_slot": True,
                "allow_playing_club_fallback": True,
            }
        )
        wizard.action_apply()
        duties = self.env["federation.match.club.referee.duty"].search(
            [("match_id", "=", self.matches[0].id)]
        )
        self.assertEqual(
            set(duties.mapped("role")),
            {"assistant_1", "assistant_2", "fourth"},
        )
        self.assertEqual(duties.mapped("club_id"), self.clubs[4])
        self.assertTrue(all(duty.state == "open" for duty in duties))

    def test_configuration_can_require_a_non_playing_club(self):
        wizard = self.env["federation.matchday.assign.official.wizard"].create(
            {
                "matchday_id": self.matchday.id,
                "assignment_type": "auto_club",
                "officials_per_match": 2,
                "avoid_clubs_playing_same_slot": True,
                "allow_playing_club_fallback": False,
            }
        )
        wizard.action_apply()
        first_match_duties = self.env["federation.match.club.referee.duty"].search(
            [("match_id", "=", self.matches[0].id)]
        )
        self.assertEqual(first_match_duties.mapped("club_id"), self.clubs[4])

    # ── duties are created when a schedule is published ──────────────────

    def _require_officials(self, count, ask_clubs=True):
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Duty Rules %s" % count,
                "code": "DUTY-RULES-%s-%s" % (count, int(ask_clubs)),
                "referee_required_count": count,
                "club_duties_on_publication": ask_clubs,
            }
        )
        self.matches.mapped("tournament_id").write({"rule_set_id": rule_set.id})
        return rule_set

    def _duties(self):
        return self.env["federation.match.club.referee.duty"].search(
            [("match_id", "in", self.matches.ids)]
        )

    def test_publication_creates_the_required_club_duties(self):
        self._require_officials(2)
        commands = self.env["federation.schedule.approval.commands"]

        created = commands._ensure_club_duties(self.matches)

        self.assertEqual(len(created), 2 * len(self.matches))
        self.assertEqual(set(created.mapped("role")), {"head", "assistant_1"})
        self.assertTrue(all(duty.state == "open" for duty in created))
        first = created.filtered(lambda duty: duty.match_id == self.matches[0])
        self.assertEqual(first.mapped("club_id"), self.clubs[4])

    def test_creating_the_duties_again_adds_nothing(self):
        self._require_officials(2)
        commands = self.env["federation.schedule.approval.commands"]
        commands._ensure_club_duties(self.matches)
        before = self._duties()

        again = commands._ensure_club_duties(self.matches)

        self.assertFalse(again)
        self.assertEqual(self._duties(), before)

    def test_late_linked_matches_get_their_duties_too(self):
        self._require_officials(1)
        commands = self.env["federation.schedule.approval.commands"]

        commands.link_placeholder_matches(self.matches)

        self.assertEqual(set(self._duties().mapped("role")), {"head"})
        self.assertEqual(len(self._duties()), len(self.matches))

    def test_an_existing_federation_referee_counts_towards_the_requirement(self):
        self._require_officials(2)
        volunteer = self.env["federation.referee"].create({"name": "Counted Head"})
        self.env["federation.match.referee"].create(
            {"match_id": self.matches[0].id, "referee_id": volunteer.id, "role": "head"}
        )

        self.env["federation.schedule.approval.commands"]._ensure_club_duties(
            self.matches
        )

        first = self._duties().filtered(lambda duty: duty.match_id == self.matches[0])
        self.assertEqual(first.mapped("role"), ["assistant_1"])

    def test_no_requirement_means_no_duties(self):
        self._require_officials(0)

        created = self.env["federation.schedule.approval.commands"]._ensure_club_duties(
            self.matches
        )

        self.assertFalse(created)
        self.assertFalse(self._duties())

    def test_a_rule_set_can_keep_officials_with_the_federation(self):
        self._require_officials(2, ask_clubs=False)

        created = self.env["federation.schedule.approval.commands"]._ensure_club_duties(
            self.matches
        )

        self.assertFalse(created)

    def test_a_problem_never_blocks_publication_and_is_noted_on_the_match_day(self):
        self._require_officials(2)
        wizard_model = self.env.registry["federation.matchday.assign.official.wizard"]

        with mock.patch.object(
            wizard_model,
            "_auto_assign_club_duties",
            side_effect=ValidationError("No club can cover this match."),
        ):
            created = self.env[
                "federation.schedule.approval.commands"
            ]._ensure_club_duties(self.matches)

        self.assertFalse(created)
        note = self.matchday.message_ids[:1]
        self.assertIn("No club can cover this match.", str(note.body))
