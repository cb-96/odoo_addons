import hashlib
import json

from odoo.tests.common import TransactionCase


class TestCompetitionPlanner(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Planner Season",
                "code": "PLAN-2027",
                "date_start": "2027-01-01",
                "date_end": "2027-12-31",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {
                "name": "Planner Competition",
                "code": "PLAN",
                "competition_type": "league",
            }
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Planner Competition 2027",
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
                "date_start": "2027-02-01",
                "date_end": "2027-10-31",
            }
        )

    def test_continue_setup_opens_visual_planner(self):
        action = self.edition.action_continue_setup()

        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(
            action["tag"], "sports_federation_setup_flow.CompetitionPlanner"
        )
        self.assertEqual(action["params"]["edition_id"], self.edition.id)

    def test_planner_exposes_ordered_journey_and_first_blocker(self):
        data = self.edition.get_competition_planner_data()

        self.assertEqual(
            [step["key"] for step in data["steps"]],
            ["basics", "teams", "format", "gamedays", "schedule", "publication"],
        )
        self.assertEqual(data["current_step"], "basics")
        self.assertFalse(data["complete"])
        self.assertEqual(data["counts"]["divisions"], 0)
        self.assertIn("missing-divisions", [issue["key"] for issue in data["issues"]])
        self.assertEqual(data["primary_action"]["kind"], "issue")
        self.assertEqual(data["primary_action"]["key"], "missing-divisions")
        self.assertEqual(data["readiness"]["status"], "blocked")

    def test_step_actions_open_simplified_scoped_workflows(self):
        action = self.edition.action_open_planner_step("gamedays")

        self.assertEqual(
            action["res_model"], "federation.competition.gameday.setup.wizard"
        )
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(wizard.edition_id, self.edition)
        self.assertEqual(action["views"], [(False, "form")])

        schedule_action = self.edition.action_open_planner_step("schedule")
        self.assertEqual(
            schedule_action["res_model"], "federation.competition.schedule.wizard"
        )
        self.assertEqual(schedule_action["views"], [(False, "form")])
        self.assertTrue(schedule_action["context"]["return_to_competition_workspace"])

    def _prepare_two_day_competition(self):
        division = self.env["federation.tournament"].create(
            {
                "name": "Planner Division",
                "edition_id": self.edition.id,
                "competition_id": self.competition.id,
                "season_id": self.season.id,
                "date_start": "2027-02-01",
                "category": "senior",
                "gender": "male",
            }
        )
        club = self.env["federation.club"].create({"name": "Planner Club"})
        teams = self.env["federation.team"].create(
            [
                {"name": "Planner Team %s" % index, "club_id": club.id}
                for index in range(1, 5)
            ]
        )
        participant_set = self.env["federation.participant.set"].create(
            {
                "name": "Planner Participants",
                "edition_id": self.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        self.env["federation.participant.set.line"].create(
            [
                {
                    "participant_set_id": participant_set.id,
                    "team_id": team.id,
                    "seed": seed,
                }
                for seed, team in enumerate(teams, start=1)
            ]
        )
        window = self.env["federation.registration.window"].create(
            {
                "name": "Planner Registration",
                "edition_id": self.edition.id,
                "division_id": division.id,
                "state": "finalized",
                "participant_set_id": participant_set.id,
            }
        )
        structure = self.env["federation.competition.structure"].create(
            {
                "name": "Planner Frozen Format",
                "edition_id": self.edition.id,
                "division_id": division.id,
                "participant_set_id": participant_set.id,
                "format_type": "custom",
                "state": "frozen",
            }
        )
        stage = self.env["federation.structure.stage"].create(
            {
                "name": "Planner Stage",
                "structure_id": structure.id,
                "stage_type": "league",
                "format_type": "manual",
                "source_type": "manual",
            }
        )
        fixtures = self.env["federation.fixture"].create(
            [
                {
                    "structure_id": structure.id,
                    "stage_id": stage.id,
                    "round_number": round_number,
                    "home_team_id": teams[(round_number - 1) * 2].id,
                    "away_team_id": teams[(round_number - 1) * 2 + 1].id,
                    "state": "ready",
                }
                for round_number in (1, 2)
            ]
        )
        venue = self.env["federation.venue"].create({"name": "Planner Venue"})
        court = self.env["federation.playing.area"].create(
            {"name": "Planner Court", "venue_id": venue.id}
        )
        days = self.env["federation.matchday"].create(
            [
                {
                    "name": "Planner Day %s" % index,
                    "edition_id": self.edition.id,
                    "date": "2027-03-0%s" % (index + 1),
                    "venue_id": venue.id,
                    "state": "capacity_ready",
                }
                for index in (1, 2)
            ]
        )
        slots = self.env["federation.schedule.slot"].create(
            [
                {
                    "matchday_id": day.id,
                    "court_id": court.id,
                    "start_datetime": "2027-03-0%s 09:00:00" % (index + 1),
                    "end_datetime": "2027-03-0%s 09:40:00" % (index + 1),
                }
                for index, day in enumerate(days)
            ]
        )
        for index, day in enumerate(days):
            self.env["federation.matchday.allocation"].create(
                {
                    "matchday_id": day.id,
                    "structure_id": structure.id,
                    "stage_id": stage.id,
                    "round_number": index + 1,
                }
            )
        schedule = self.env["federation.schedule"].create(
            {
                "name": "Planner Day 1 Schedule",
                "edition_id": self.edition.id,
                "structure_id": structure.id,
                "matchday_id": days[0].id,
            }
        )
        self.env["federation.schedule.assignment"].create(
            {
                "schedule_id": schedule.id,
                "fixture_id": fixtures[0].id,
                "slot_id": slots[0].id,
            }
        )
        return division, structure, fixtures, days, slots, schedule

    def _add_day_schedule(self, structure, fixture, day, slot):
        schedule = self.env["federation.schedule"].create(
            {
                "name": "%s Schedule" % day.display_name,
                "edition_id": self.edition.id,
                "structure_id": structure.id,
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
        return schedule

    def _publish_for_readiness(self, schedule, day):
        commands = self.env["federation.schedule.approval.commands"]
        snapshot = commands._snapshot(schedule)
        digest = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        review = self.env["federation.schedule.review"].sudo().create(
            {
                "schedule_id": schedule.id,
                "submitted_revision": schedule.revision,
                "state": "approved",
                "assignment_snapshot": snapshot,
                "snapshot_digest": digest,
                "submitted_by_id": self.env.user.id,
            }
        )
        publication = self.env["federation.schedule.publication"].sudo().create(
            {
                "schedule_id": schedule.id,
                "version": 1,
                "assignment_snapshot": snapshot,
                "snapshot_digest": digest,
                "source_revision": schedule.revision,
                "review_id": review.id,
            }
        )
        schedule.state = "published"
        day.current_publication_id = publication

    def test_readiness_requires_a_schedule_for_each_allocated_matchday(self):
        _division, _structure, _fixtures, days, _slots, _schedule = (
            self._prepare_two_day_competition()
        )

        planner = self.edition.get_competition_planner_data()
        self.assertFalse(planner["complete"])
        self.assertEqual(planner["current_step"], "schedule")
        self.assertIn(
            "gameday-%s-missing-schedule" % days[1].id,
            [issue["key"] for issue in planner["issues"]],
        )
        assessment = self.env["federation.competition.setup.readiness"].evaluate(
            self.edition
        )
        self.assertEqual(assessment["step"], "schedule")
        self.assertLess(assessment["progress"], 100)

    def test_readiness_reports_missing_participant_set_per_division(self):
        division, _structure, _fixtures, _days, _slots, _schedule = (
            self._prepare_two_day_competition()
        )
        second_division = self.env["federation.tournament"].create(
            {
                "name": "Planner Division Without Teams",
                "edition_id": self.edition.id,
                "competition_id": self.competition.id,
                "season_id": self.season.id,
                "date_start": "2027-02-01",
                "category": "senior",
                "gender": "male",
            }
        )

        planner = self.edition.get_competition_planner_data()

        self.assertIn(
            "division-%s-teams" % second_division.id,
            [issue["key"] for issue in planner["issues"]],
        )
        rows = {row["id"]: row for row in planner["divisions"]}
        self.assertTrue(rows[division.id]["ready"])
        self.assertFalse(rows[second_division.id]["ready"])

    def test_form_and_planner_share_matchday_publication_readiness(self):
        _division, structure, fixtures, days, slots, _schedule = (
            self._prepare_two_day_competition()
        )
        day_two_schedule = self._add_day_schedule(
            structure, fixtures[1], days[1], slots[1]
        )
        day_one_schedule = self.env["federation.schedule"].search(
            [("matchday_id", "=", days[0].id)], limit=1
        )

        planner = self.edition.get_competition_planner_data()
        self.assertEqual(planner["current_step"], "publication")
        self._publish_for_readiness(day_one_schedule, days[0])
        self._publish_for_readiness(day_two_schedule, days[1])

        planner = self.edition.get_competition_planner_data()
        assessment = self.env["federation.competition.setup.readiness"].evaluate(
            self.edition
        )
        self.assertTrue(planner["complete"])
        self.assertEqual(assessment["step"], "complete")
        self.assertEqual(assessment["progress"], 100)

        days[1].current_publication_id = False
        planner = self.edition.get_competition_planner_data()
        assessment = self.env["federation.competition.setup.readiness"].evaluate(
            self.edition
        )
        self.assertFalse(planner["complete"])
        self.assertEqual(planner["current_step"], "publication")
        self.assertEqual(assessment["step"], "publication")
        self.assertIn(
            "gameday-%s-missing-publication" % days[1].id,
            [issue["key"] for issue in planner["issues"]],
        )

    def test_planner_blocker_is_actionable_and_opens_exact_record(self):
        division = self.env["federation.tournament"].create(
            {
                "name": "Actionable Division",
                "edition_id": self.edition.id,
                "competition_id": self.competition.id,
                "season_id": self.season.id,
                "date_start": "2027-02-01",
            }
        )
        window = self.env["federation.registration.window"].create(
            {
                "name": "Actionable Registration",
                "edition_id": self.edition.id,
                "division_id": division.id,
            }
        )

        data = self.edition.get_competition_planner_data()
        issue = next(
            item
            for item in data["issues"]
            if item["key"] == f"division-{division.id}-teams"
        )
        self.assertEqual(issue["owner"], "Registration manager")
        self.assertTrue(issue["action_label"])
        self.assertEqual(data["current_issue"]["key"], issue["key"])

        action = self.edition.action_open_planner_issue(issue["key"])
        self.assertEqual(action["res_model"], "federation.registration.window")
        self.assertEqual(action["res_id"], window.id)
        self.assertEqual(action["views"], [(False, "form")])

    def test_ordinary_manager_routes_to_simplified_team_picker(self):
        division = self.env["federation.tournament"].create(
            {
                "name": "Simplified Team Picker Division",
                "edition_id": self.edition.id,
                "competition_id": self.competition.id,
                "season_id": self.season.id,
                "date_start": "2027-02-01",
            }
        )
        self.env["federation.registration.window"].create(
            {
                "name": "Simplified Team Picker Registration",
                "edition_id": self.edition.id,
                "division_id": division.id,
            }
        )
        manager = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Ordinary Competition Manager",
                "login": "ordinary.competition.manager",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref(
                                "sports_federation_base.group_federation_manager"
                            ).id,
                        ],
                    )
                ],
            }
        )
        key = "division-%s-teams" % division.id

        action = self.edition.with_user(manager).action_open_planner_issue(key)

        self.assertEqual(
            action["res_model"], "federation.competition.team.selection.wizard"
        )
        self.assertEqual(action["views"], [(False, "form")])

    def test_waiting_steps_use_short_business_labels(self):
        data = self.edition.get_competition_planner_data()
        self.assertEqual(
            [step["label"] for step in data["steps"]],
            ["Competition", "Teams", "Format", "Dates & venues", "Schedule", "Review & publish"],
        )

    def test_operation_actions_remain_competition_scoped(self):
        action = self.edition.action_open_planner_operation("matchdays")
        self.assertEqual(action["domain"], [("edition_id", "=", self.edition.id)])
        self.assertEqual(action["context"]["default_edition_id"], self.edition.id)
        self.assertEqual(
            action["views"],
            [(False, "calendar"), (False, "list"), (False, "form")],
        )
