from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("-at_install", "post_install", "sf_competition_workspace")
class TestCompetitionWorkspaceService(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["federation.competition.workspace.service"]
        cls.club = cls.env["federation.club"].create({"name": "Workspace Club"})
        cls.teams = cls.env["federation.team"]
        for index in range(1, 9):
            cls.teams |= cls.env["federation.team"].create(
                {
                    "name": f"Workspace Team {index}",
                    "club_id": cls.club.id,
                }
            )

        cls.season = cls.env["federation.season"].create(
            {
                "name": "2026-2027",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        cls.competition_template = cls.env["federation.competition"].create(
            {
                "name": "Workspace League",
                "competition_type": "league",
            }
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Workspace League 2026",
                "competition_id": cls.competition_template.id,
                "season_id": cls.season.id,
                "date_start": "2026-10-01",
                "date_end": "2027-04-30",
            }
        )
        cls.venue = cls.env["federation.venue"].create({"name": "Central Hall"})
        cls.court_1 = cls.env["federation.playing.area"].create(
            {"name": "Court 1", "venue_id": cls.venue.id}
        )
        cls.court_2 = cls.env["federation.playing.area"].create(
            {"name": "Court 2", "venue_id": cls.venue.id}
        )

        planner_group = cls.env.ref(
            "sports_federation_competition_engine.group_federation_competition_planner"
        )
        manager_group = cls.env.ref("sports_federation_base.group_federation_manager")
        user_group = cls.env.ref("sports_federation_base.group_federation_user")

        cls.planner_user = cls.env["res.users"].create(
            {
                "name": "Competition Planner",
                "login": "competition_planner",
                "email": "competition_planner@example.com",
                "group_ids": [(6, 0, [planner_group.id])],
            }
        )
        cls.manager_user = cls.env["res.users"].create(
            {
                "name": "Competition Manager",
                "login": "competition_manager",
                "email": "competition_manager@example.com",
                "group_ids": [(6, 0, [manager_group.id])],
            }
        )
        cls.regular_user = cls.env["res.users"].create(
            {
                "name": "Competition Observer",
                "login": "competition_observer",
                "email": "competition_observer@example.com",
                "group_ids": [(6, 0, [user_group.id])],
            }
        )

    def _create_division(
        self,
        name,
        team_count,
        team_offset=0,
        minimum_rest_minutes=30,
        max_consecutive_matches_per_team=1,
        planning_format="single_round_robin",
    ):
        division = self.env["federation.tournament"].create(
            {
                "name": name,
                "edition_id": self.edition.id,
                "competition_id": self.competition_template.id,
                "season_id": self.season.id,
                "date_start": "2026-10-10",
                "date_end": "2026-10-10",
                "planning_format": planning_format,
                "workspace_state": "registration_open",
                "minimum_rest_minutes": minimum_rest_minutes,
                "max_consecutive_matches_per_team": max_consecutive_matches_per_team,
            }
        )
        participants = self.env["federation.tournament.participant"]
        for seed, team in enumerate(
            self.teams[team_offset : team_offset + team_count],
            start=1,
        ):
            participants |= self.env["federation.tournament.participant"].create(
                {
                    "tournament_id": division.id,
                    "team_id": team.id,
                    "seed": seed,
                    "state": "confirmed",
                }
            )
        return division, participants

    def _prepare_shared_planned_divisions(self):
        host_division, _participants = self._create_division(
            "Shared Host Division",
            4,
            team_offset=0,
            minimum_rest_minutes=30,
        )
        guest_division, _participants = self._create_division(
            "Shared Guest Division",
            4,
            team_offset=4,
            minimum_rest_minutes=30,
        )
        host_division.action_lock_team_entries()
        guest_division.action_lock_team_entries()
        self.service.generate_round_robin(host_division.id)
        self.service.generate_round_robin(guest_division.id)
        gameday_id = self.service.create_gameday(
            {
                "division_id": host_division.id,
                "name": "Shared Gameday 1",
                "round_date": "2026-10-10",
                "shared_division_ids": [guest_division.id],
                "venue_id": self.venue.id,
            }
        )["gameday_id"]
        host_gameday = self.env["federation.tournament.round"].browse(gameday_id)
        guest_gameday = guest_division.round_ids.filtered(
            lambda round_record: round_record.planner_root_round_id == host_gameday
        )[:1]
        self.service.generate_slots(
            host_gameday.id,
            [self.court_1.id, self.court_2.id],
            "09:00",
            "10:20",
            30,
            5,
            [],
            False,
        )
        return host_division, guest_division, host_gameday, guest_gameday

    def _prepare_planned_division(self, name="Planner Division"):
        division, _participants = self._create_division(name, 4, minimum_rest_minutes=30)
        division.action_lock_team_entries()
        self.service.generate_round_robin(division.id)
        gameday_id = self.service.create_gameday(
            {
                "division_id": division.id,
                "name": "Gameday 1",
                "round_date": "2026-10-10",
                "venue_id": self.venue.id,
            }
        )["gameday_id"]
        self.service.generate_slots(
            gameday_id,
            [self.court_1.id, self.court_2.id],
            "09:00",
            "10:20",
            30,
            5,
            [],
            False,
        )
        return division, self.env["federation.tournament.round"].browse(gameday_id)

    def test_create_competition_shell(self):
        result = self.service.with_user(self.manager_user).create_competition_shell(
            {
                "name": "Created Through Workspace",
                "season_id": self.season.id,
                "competition_vals": {
                    "name": "Created Through Workspace Template",
                    "competition_type": "league",
                },
                "date_start": "2026-11-01",
                "date_end": "2027-03-01",
            }
        )
        self.assertTrue(result["created"])
        self.assertTrue(result["competition_id"])
        created = self.env["federation.competition.edition"].browse(
            result["competition_id"]
        )
        self.assertEqual(created.name, "Created Through Workspace")
        self.assertEqual(created.competition_id.name, "Created Through Workspace Template")

    def test_create_competition_shell_reuses_existing_edition(self):
        result = self.service.with_user(self.manager_user).create_competition_shell(
            {
                "name": "Duplicate Workspace League 2026",
                "season_id": self.season.id,
                "competition_id": self.competition_template.id,
            }
        )

        self.assertFalse(result["created"])
        self.assertEqual(result["competition_id"], self.edition.id)

    def test_edition_action_opens_competition_workspace_client_action(self):
        action = self.edition.with_user(
            self.manager_user
        ).action_open_competition_workspace()

        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(
            action["tag"],
            "sports_federation_competition_engine.competition_workspace",
        )
        self.assertEqual(action["params"]["competition_id"], self.edition.id)

    def test_division_action_opens_competition_workspace_client_action(self):
        division, _participants = self._create_division("Workspace Action Division", 4)

        action = division.with_user(self.manager_user).action_open_competition_workspace()

        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(
            action["tag"],
            "sports_federation_competition_engine.competition_workspace",
        )
        self.assertEqual(action["params"]["competition_id"], self.edition.id)
        self.assertEqual(action["params"]["division_id"], division.id)

    def test_create_competition_shell_requires_name(self):
        with self.assertRaises(ValidationError):
            self.service.with_user(self.manager_user).create_competition_shell(
                {
                    "name": "",
                    "season_id": self.season.id,
                    "competition_id": self.competition_template.id,
                }
            )

    def test_create_competition_shell_requires_season(self):
        with self.assertRaises(ValidationError):
            self.service.with_user(self.manager_user).create_competition_shell(
                {
                    "name": "Missing Season Shell",
                    "season_id": False,
                    "competition_id": self.competition_template.id,
                }
            )

    def test_create_competition_shell_requires_manager(self):
        with self.assertRaises(AccessError):
            self.service.with_user(self.planner_user).create_competition_shell(
                {
                    "name": "Planner Cannot Create",
                    "season_id": self.season.id,
                    "competition_vals": {
                        "name": "Planner Cannot Create",
                    },
                }
            )

    def test_generate_round_robin_even_teams_creates_unscheduled_matches(self):
        division, _participants = self._create_division("Even Division", 4)
        division.action_lock_team_entries()

        result = self.service.generate_round_robin(division.id)

        self.assertEqual(result["match_count"], 6)
        self.assertEqual(division.match_ids.mapped("round_number"), [1, 1, 2, 2, 3, 3])
        self.assertFalse(any(division.match_ids.mapped("slot_id")))
        self.assertFalse(any(division.match_ids.mapped("round_id")))
        self.assertFalse(any(division.match_ids.mapped("date_scheduled")))

    def test_generate_round_robin_odd_teams_adds_bye_without_duplicates(self):
        division, _participants = self._create_division("Odd Division", 5)
        division.action_lock_team_entries()

        result = self.service.generate_round_robin(division.id)

        self.assertEqual(result["match_count"], 10)
        pairings = {
            tuple(sorted([match.home_team_id.id, match.away_team_id.id]))
            for match in division.match_ids
        }
        self.assertEqual(len(pairings), 10)

    def test_generate_double_round_robin_creates_home_and_away_matches(self):
        division, _participants = self._create_division(
            "Home And Away Division",
            4,
            planning_format="double_round_robin",
        )
        division.action_lock_team_entries()

        result = self.service.generate_schedule_structure(division.id)

        self.assertEqual(result["match_count"], 12)
        self.assertEqual(
            sorted(division.match_ids.mapped("round_number")),
            [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6],
        )
        pairings = {}
        for match in division.match_ids:
            key = frozenset((match.home_team_id.id, match.away_team_id.id))
            pairings.setdefault(key, set()).add(
                (match.home_team_id.id, match.away_team_id.id)
            )
        self.assertEqual(len(pairings), 6)
        self.assertTrue(all(len(oriented_pairs) == 2 for oriented_pairs in pairings.values()))
        self.assertFalse(any(division.match_ids.mapped("slot_id")))
        self.assertFalse(any(division.match_ids.mapped("round_id")))
        self.assertFalse(any(division.match_ids.mapped("date_scheduled")))

    def test_generate_knockout_creates_unscheduled_bracket_matches(self):
        division, _participants = self._create_division(
            "Knockout Division",
            6,
            planning_format="knockout",
        )
        division.action_lock_team_entries()

        result = self.service.generate_schedule_structure(division.id)

        self.assertEqual(result["match_count"], 5)
        self.assertEqual(division._workspace_get_or_create_stage().stage_type, "knockout")
        self.assertEqual(sorted(division.match_ids.mapped("round_number")), [1, 1, 2, 2, 3])
        self.assertFalse(any(division.match_ids.mapped("slot_id")))
        self.assertFalse(any(division.match_ids.mapped("round_id")))
        self.assertFalse(any(division.match_ids.mapped("date_scheduled")))

        first_round = division.match_ids.filtered(
            lambda match: match.round_number == 1
        ).sorted(lambda match: match.bracket_position)
        second_round = division.match_ids.filtered(
            lambda match: match.round_number == 2
        ).sorted(lambda match: match.bracket_position)

        self.assertEqual(second_round[0].home_team_id, self.teams[0])
        self.assertEqual(second_round[0].source_match_2_id, first_round[0])
        self.assertEqual(second_round[1].home_team_id, self.teams[1])
        self.assertEqual(second_round[1].source_match_2_id, first_round[1])

        payload = self.service.get_competition_workspace_data(self.edition.id, division.id)
        preview = payload["selected_division"]["generation_preview"]
        self.assertEqual(preview["format"], "knockout")
        self.assertEqual(preview["rounds"][1]["name"], "Semifinal")
        self.assertEqual(
            preview["rounds"][1]["matches"][0]["home_team_name"],
            self.teams[0].display_name,
        )
        self.assertIn(
            "Winner of",
            preview["rounds"][1]["matches"][0]["away_team_name"],
        )

    def _freeze_pool_standing(self, division, pool_stage, group, ranked_participants):
        standing = self.env["federation.standing"].create(
            {
                "name": f"{group.name} Standing",
                "tournament_id": division.id,
                "stage_id": pool_stage.id,
                "group_id": group.id,
                "state": "computed",
            }
        )
        line_vals = []
        points_seed = len(ranked_participants)
        for rank, participant in enumerate(ranked_participants, start=1):
            line_vals.append(
                {
                    "standing_id": standing.id,
                    "participant_id": participant.id,
                    "rank": rank,
                    "points": points_seed - rank + 1,
                    "score_for": (points_seed - rank + 1) * 2,
                    "score_against": rank - 1,
                }
            )
        self.env["federation.standing.line"].create(line_vals)
        standing.action_freeze()
        return standing

    def test_generate_pool_then_bracket_creates_pool_stage_and_progressions(self):
        division, _participants = self._create_division(
            "Pool Then Bracket Division",
            8,
            planning_format="pool_then_bracket",
        )
        division.write({"pool_count": 2, "pool_qualifier_count": 2})
        division.action_lock_team_entries()

        result = self.service.generate_schedule_structure(division.id)

        pool_stage = division._workspace_get_or_create_stage()
        knockout_stage = division._workspace_get_or_create_knockout_stage()
        pool_groups = pool_stage.group_ids.sorted(lambda group: (group.sequence, group.id))
        self.assertEqual(result["match_count"], 12)
        self.assertEqual(pool_stage.stage_type, "group")
        self.assertEqual(knockout_stage.stage_type, "knockout")
        self.assertEqual(len(pool_groups), 2)
        self.assertEqual(sorted(pool_groups.mapped("participant_count")), [4, 4])
        self.assertEqual(
            len(division.match_ids.filtered(lambda match: match.stage_id == pool_stage)),
            12,
        )
        self.assertFalse(
            division.match_ids.filtered(lambda match: match.stage_id == knockout_stage)
        )

        progressions = self.env["federation.stage.progression"].search(
            [
                ("tournament_id", "=", division.id),
                ("source_stage_id", "=", pool_stage.id),
                ("target_stage_id", "=", knockout_stage.id),
            ]
        )
        self.assertEqual(len(progressions), 4)
        self.assertEqual(len(knockout_stage.group_ids), 2)
        self.assertTrue(all(progressions.mapped("auto_advance")))

        payload = self.service.get_competition_workspace_data(self.edition.id, division.id)
        preview = payload["selected_division"]["generation_preview"]
        self.assertEqual(preview["format"], "pool_then_bracket")
        self.assertTrue(preview["supported"])
        self.assertFalse(preview["action_label"])
        self.assertIn("Freeze", preview["description"])
        self.assertEqual(len(preview["rounds"]), 3)

    def test_pool_then_bracket_can_generate_bracket_after_auto_advance(self):
        division, _participants = self._create_division(
            "Pool Bracket Progression Division",
            8,
            planning_format="pool_then_bracket",
        )
        division.write({"pool_count": 2, "pool_qualifier_count": 2})
        division.action_lock_team_entries()
        self.service.generate_schedule_structure(division.id)

        pool_stage = division._workspace_get_or_create_stage()
        knockout_stage = division._workspace_get_or_create_knockout_stage()
        pool_groups = pool_stage.group_ids.sorted(lambda group: (group.sequence, group.id))

        self._freeze_pool_standing(
            division,
            pool_stage,
            pool_groups[0],
            pool_groups[0].participant_ids.sorted(
                lambda participant: (participant.seed or 9999, participant.team_id.name or "")
            ),
        )
        self._freeze_pool_standing(
            division,
            pool_stage,
            pool_groups[1],
            pool_groups[1].participant_ids.sorted(
                lambda participant: (participant.seed or 9999, participant.team_id.name or "")
            ),
        )

        advanced = division.participant_ids.filtered(
            lambda participant: participant.stage_id == knockout_stage
        ).sorted(lambda participant: participant.seed)
        self.assertEqual(len(advanced), 4)
        self.assertEqual(advanced.mapped("seed"), [1, 1, 2, 2])
        self.assertEqual(
            advanced.sorted(
                lambda participant: (
                    participant.group_id.sequence if participant.group_id else 9999,
                    participant.seed or 9999,
                    participant.team_id.name or "",
                )
            ).mapped("seed"),
            [1, 2, 1, 2],
        )

        result = self.service.generate_schedule_structure(division.id)

        advanced = division.participant_ids.filtered(
            lambda participant: participant.stage_id == knockout_stage
        ).sorted(lambda participant: participant.seed)
        self.assertEqual(advanced.mapped("seed"), [1, 2, 3, 4])

        bracket_matches = division.match_ids.filtered(
            lambda match: match.stage_id == knockout_stage
        ).sorted(lambda match: (match.round_number, match.bracket_position or 0, match.id))
        self.assertEqual(result["match_count"], 3)
        self.assertEqual(sorted(bracket_matches.mapped("round_number")), [1, 1, 2])
        self.assertEqual(
            [
                (match.home_team_id.id, match.away_team_id.id)
                for match in bracket_matches.filtered(lambda match: match.round_number == 1)
            ],
            [
                (advanced[0].team_id.id, advanced[3].team_id.id),
                (advanced[1].team_id.id, advanced[2].team_id.id),
            ],
        )

    def test_pool_then_bracket_knockout_gameday_targets_knockout_stage_matches(self):
        division, _participants = self._create_division(
            "Pool Then Bracket Planner Division",
            8,
            planning_format="pool_then_bracket",
        )
        division.write({"pool_count": 2, "pool_qualifier_count": 2})
        division.action_lock_team_entries()
        self.service.generate_schedule_structure(division.id)

        pool_stage = division._workspace_get_or_create_stage()
        knockout_stage = division._workspace_get_or_create_knockout_stage()
        pool_groups = pool_stage.group_ids.sorted(lambda group: (group.sequence, group.id))
        for group in pool_groups:
            self._freeze_pool_standing(
                division,
                pool_stage,
                group,
                group.participant_ids.sorted(
                    lambda participant: (
                        participant.seed or 9999,
                        participant.team_id.name or "",
                    )
                ),
            )
        self.service.generate_schedule_structure(division.id)

        gameday_id = self.service.create_gameday(
            {
                "division_id": division.id,
                "name": "Knockout Day 1",
                "round_date": "2026-10-18",
                "stage_id": knockout_stage.id,
                "venue_id": self.venue.id,
            }
        )["gameday_id"]
        self.service.generate_slots(
            gameday_id,
            [self.court_1.id],
            "09:00",
            "10:20",
            30,
            5,
            [],
            False,
        )

        knockout_gameday = self.env["federation.tournament.round"].browse(gameday_id)
        planner = self.service.get_gameday_planner_data(knockout_gameday.id)
        payload = self.service.get_competition_workspace_data(self.edition.id, division.id)

        self.assertEqual(knockout_gameday.stage_id, knockout_stage)
        self.assertEqual(planner["gameday"]["stage_id"], knockout_stage.id)
        self.assertTrue(planner["unscheduled_matches"])
        self.assertEqual(
            {match["stage_id"] for match in planner["unscheduled_matches"]},
            {knockout_stage.id},
        )
        self.assertEqual(
            {stage["id"] for stage in payload["selected_division"]["stage_options"]},
            {pool_stage.id, knockout_stage.id},
        )
        self.assertEqual(
            {round_item["stage_id"] for round_item in payload["selected_division"]["rounds"]},
            {pool_stage.id, knockout_stage.id},
        )

    def test_fairness_summary_is_exposed_on_division_planner_and_overview_payloads(self):
        division, gameday = self._prepare_planned_division("Fairness Summary Division")
        slots = gameday.slot_ids.sorted(
            lambda slot: (slot.start_datetime, slot.playing_area_id.id, slot.id)
        )
        team_one = self.teams[0]
        team_one_matches = division.match_ids.filtered(
            lambda match: team_one in (match.home_team_id, match.away_team_id)
        ).sorted(lambda match: match.id)
        team_one_slots = slots[::2][: len(team_one_matches)]
        support_match = division.match_ids.filtered(
            lambda match: {
                match.home_team_id.id,
                match.away_team_id.id,
            }
            == {self.teams[1].id, self.teams[2].id}
        )[:1]

        for match, slot in zip(team_one_matches, team_one_slots):
            result = self.service.assign_match_to_slot(
                match.id,
                slot.id,
                force=True,
                override_reason="Fairness regression fixture",
            )
            self.assertTrue(result["ok"])
        result = self.service.assign_match_to_slot(
            support_match.id,
            slots[1].id,
            force=True,
            override_reason="Fairness regression fixture",
        )
        self.assertTrue(result["ok"])

        payload = self.service.get_competition_workspace_data(self.edition.id, division.id)
        planner = self.service.get_gameday_planner_data(gameday.id)
        fairness_summary = payload["selected_division"]["fairness_summary"]
        overview_summary = payload["overview"]["fairness_summary"]

        self.assertEqual(fairness_summary["tracked_team_count"], 4)
        self.assertIn("rest_balance_gap_minutes", fairness_summary)
        self.assertGreater(fairness_summary["court_balance_gap_percent"], 0)
        self.assertGreater(fairness_summary["timeslot_balance_gap_minutes"], 0)
        self.assertEqual(
            {component["key"] for component in fairness_summary["score_components"]},
            {"rest_fairness", "court_fairness", "timeslot_fairness"},
        )
        self.assertTrue(
            any(
                metric["average_rest_gap_minutes"] is not False
                for metric in fairness_summary["team_metrics"]
            )
        )
        self.assertTrue(
            all(
                "threshold" in component
                for component in fairness_summary["score_components"]
            )
        )
        self.assertEqual(planner["fairness_summary"]["tracked_team_count"], 4)
        self.assertEqual(overview_summary["tracked_division_count"], 1)
        self.assertIn("warning_division_count", overview_summary)

    def test_match_slot_suggestions_return_ranked_open_slots(self):
        division, gameday = self._prepare_planned_division("Suggestion Division")
        match = division.match_ids[:1]

        suggestions = self.service.get_match_slot_suggestions(match.id, gameday.id, limit=3)

        self.assertEqual(len(suggestions), 3)
        self.assertEqual(
            {component["key"] for component in suggestions[0]["score_components"]},
            {"validation_headroom", "slot_order"},
        )
        self.assertEqual(
            [suggestion["start_label"] for suggestion in suggestions],
            ["09:00", "09:00", "09:35"],
        )
        self.assertTrue(
            suggestions[0]["score"] >= suggestions[1]["score"] >= suggestions[2]["score"]
        )

    def test_generate_round_robin_requires_locked_entries(self):
        division, _participants = self._create_division("Unlocked Division", 4)

        with self.assertRaises(ValidationError):
            self.service.generate_round_robin(division.id)

    def test_slot_generation_creates_expected_slots_with_buffer(self):
        division, _participants = self._create_division("Slot Division", 4)
        division.action_lock_team_entries()
        gameday_id = self.service.create_gameday(
            {
                "division_id": division.id,
                "name": "Slot Gameday",
                "round_date": "2026-10-11",
                "venue_id": self.venue.id,
            }
        )["gameday_id"]

        result = self.service.generate_slots(
            gameday_id,
            [self.court_1.id, self.court_2.id],
            "09:00",
            "11:00",
            30,
            5,
            [],
            False,
        )

        self.assertEqual(result["slot_count"], 6)
        gameday = self.env["federation.tournament.round"].browse(gameday_id)
        slot_times = sorted(
            {
                (
                    slot.start_datetime.strftime("%H:%M"),
                    slot.end_datetime.strftime("%H:%M"),
                )
                for slot in gameday.slot_ids
            }
        )
        self.assertEqual(
            slot_times,
            [("09:00", "09:30"), ("09:35", "10:05"), ("10:10", "10:40")],
        )

    def test_assigning_two_matches_to_same_slot_is_blocked(self):
        division, gameday = self._prepare_planned_division("Double Booked Division")
        match_a, match_b = division.match_ids[:2]
        slot = gameday.slot_ids.filtered(lambda record: record.state == "available")[:1]

        first_assignment = self.service.assign_match_to_slot(match_a.id, slot.id)
        second_assignment = self.service.assign_match_to_slot(match_b.id, slot.id)

        self.assertTrue(first_assignment["ok"])
        self.assertFalse(second_assignment["ok"])
        self.assertEqual(
            second_assignment["validation"]["blocking"][0]["code"],
            "slot_occupied",
        )

    def test_assigned_matches_can_swap_occupied_slots(self):
        division, gameday = self._prepare_planned_division("Safe Swap Division")
        match_a = division.match_ids[:1]
        match_b = division.match_ids.filtered(
            lambda match: match != match_a
            and match.home_team_id not in (match_a.home_team_id, match_a.away_team_id)
            and match.away_team_id not in (match_a.home_team_id, match_a.away_team_id)
        )[:1]
        slots = gameday.slot_ids.filtered(lambda slot: slot.state == "available").sorted(
            lambda slot: (slot.start_datetime, slot.playing_area_id.id)
        )

        self.assertTrue(self.service.assign_match_to_slot(match_a.id, slots[0].id)["ok"])
        self.assertTrue(self.service.assign_match_to_slot(match_b.id, slots[1].id)["ok"])

        swap_result = self.service.assign_match_to_slot(match_a.id, slots[1].id)

        self.assertTrue(swap_result["ok"])
        match_a.invalidate_recordset()
        match_b.invalidate_recordset()
        slots.invalidate_recordset()
        self.assertEqual(match_a.slot_id, slots[1])
        self.assertEqual(match_b.slot_id, slots[0])
        self.assertEqual(
            [operation["operation_type"] for operation in swap_result["planner"]["operation_history"][:2]],
            ["move", "move"],
        )
        self.assertTrue(swap_result["planner"]["operation_history"][0]["batch_key"])
        self.assertEqual(
            swap_result["planner"]["operation_history"][0]["batch_key"],
            swap_result["planner"]["operation_history"][1]["batch_key"],
        )

    def test_team_overlap_is_blocked(self):
        division, gameday = self._prepare_planned_division("Overlap Division")
        team_1_matches = division.match_ids.filtered(
            lambda match: match.home_team_id == self.teams[0]
            or match.away_team_id == self.teams[0]
        )
        match_a = team_1_matches[0]
        match_b = team_1_matches[1]
        first_row_slots = gameday.slot_ids.filtered(
            lambda slot: slot.start_datetime
            == min(gameday.slot_ids.mapped("start_datetime"))
        ).sorted(lambda slot: slot.playing_area_id.id)

        self.assertTrue(
            self.service.assign_match_to_slot(match_a.id, first_row_slots[0].id)["ok"]
        )
        overlap_attempt = self.service.assign_match_to_slot(
            match_b.id, first_row_slots[1].id
        )

        self.assertFalse(overlap_attempt["ok"])
        self.assertEqual(
            overlap_attempt["validation"]["blocking"][0]["code"],
            "team_overlap",
        )

    def test_short_rest_creates_warning(self):
        division, gameday = self._prepare_planned_division("Short Rest Division")
        team_1_matches = division.match_ids.filtered(
            lambda match: match.home_team_id == self.teams[0]
            or match.away_team_id == self.teams[0]
        )
        match_a = team_1_matches[0]
        match_b = team_1_matches[1]
        slots = gameday.slot_ids.filtered(lambda slot: slot.state == "available").sorted(
            lambda slot: (slot.start_datetime, slot.playing_area_id.id)
        )

        self.assertTrue(self.service.assign_match_to_slot(match_a.id, slots[0].id)["ok"])
        warning_attempt = self.service.assign_match_to_slot(match_b.id, slots[2].id)

        self.assertFalse(warning_attempt["ok"])
        warning_codes = {
            issue["code"] for issue in warning_attempt["validation"]["warnings"]
        }
        self.assertIn("short_rest", warning_codes)

    def test_consecutive_match_limit_creates_warning(self):
        division, gameday = self._prepare_planned_division("Consecutive Limit Division")
        division.write(
            {
                "minimum_rest_minutes": 30,
                "max_consecutive_matches_per_team": 1,
            }
        )
        team_1_matches = division.match_ids.filtered(
            lambda match: match.home_team_id == self.teams[0]
            or match.away_team_id == self.teams[0]
        )
        match_a = team_1_matches[0]
        match_b = team_1_matches[1]
        slots = gameday.slot_ids.filtered(lambda slot: slot.state == "available").sorted(
            lambda slot: (slot.start_datetime, slot.playing_area_id.id)
        )

        self.assertTrue(self.service.assign_match_to_slot(match_a.id, slots[0].id)["ok"])
        warning_attempt = self.service.assign_match_to_slot(match_b.id, slots[2].id)

        self.assertFalse(warning_attempt["ok"])
        warning_codes = {
            issue["code"] for issue in warning_attempt["validation"]["warnings"]
        }
        self.assertIn("team_consecutive_limit", warning_codes)

    def test_manager_force_warning_assignment_requires_reason(self):
        division, gameday = self._prepare_planned_division(
            "Manager Force Reason Division"
        )
        team_1_matches = division.match_ids.filtered(
            lambda match: match.home_team_id == self.teams[0]
            or match.away_team_id == self.teams[0]
        )
        match_a = team_1_matches[0]
        match_b = team_1_matches[1]
        slots = gameday.slot_ids.filtered(lambda slot: slot.state == "available").sorted(
            lambda slot: (slot.start_datetime, slot.playing_area_id.id)
        )

        self.assertTrue(
            self.service.assign_match_to_slot(match_a.id, slots[0].id)["ok"]
        )

        force_result = self.service.with_user(self.manager_user).assign_match_to_slot(
            match_b.id,
            slots[2].id,
            True,
        )

        self.assertFalse(force_result["ok"])
        self.assertEqual(
            force_result["validation"]["blocking"][0]["code"],
            "override_reason_required",
        )

    def test_manager_can_force_warning_only_assignment(self):
        division, gameday = self._prepare_planned_division("Manager Force Division")
        team_1_matches = division.match_ids.filtered(
            lambda match: match.home_team_id == self.teams[0]
            or match.away_team_id == self.teams[0]
        )
        match_a = team_1_matches[0]
        match_b = team_1_matches[1]
        slots = gameday.slot_ids.filtered(lambda slot: slot.state == "available").sorted(
            lambda slot: (slot.start_datetime, slot.playing_area_id.id)
        )

        self.assertTrue(self.service.assign_match_to_slot(match_a.id, slots[0].id)["ok"])

        force_result = self.service.with_user(self.manager_user).assign_match_to_slot(
            match_b.id,
            slots[2].id,
            True,
            override_reason="Approved short-rest exception for venue availability.",
        )

        self.assertTrue(force_result["ok"])
        match_b.invalidate_recordset()
        self.assertEqual(match_b.slot_id, slots[2])
        self.assertTrue(force_result["planner"]["operation_history"][0]["forced"])
        self.assertEqual(
            force_result["planner"]["operation_history"][0]["override_reason"],
            "Approved short-rest exception for venue availability.",
        )

    def test_planner_user_cannot_force_warning_only_assignment(self):
        division, gameday = self._prepare_planned_division("Planner Force Division")
        team_1_matches = division.match_ids.filtered(
            lambda match: match.home_team_id == self.teams[0]
            or match.away_team_id == self.teams[0]
        )
        match_a = team_1_matches[0]
        match_b = team_1_matches[1]
        slots = gameday.slot_ids.filtered(lambda slot: slot.state == "available").sorted(
            lambda slot: (slot.start_datetime, slot.playing_area_id.id)
        )

        self.assertTrue(
            self.service.with_user(self.planner_user).assign_match_to_slot(
                match_a.id,
                slots[0].id,
            )["ok"]
        )

        with self.assertRaises(AccessError):
            self.service.with_user(self.planner_user).assign_match_to_slot(
                match_b.id,
                slots[2].id,
                True,
            )

    def test_assignment_and_unassignment_keep_match_and_slot_consistent(self):
        division, gameday = self._prepare_planned_division("Assignment Division")
        match = division.match_ids[:1]
        slot = gameday.slot_ids.filtered(lambda record: record.state == "available")[:1]

        self.assertTrue(self.service.assign_match_to_slot(match.id, slot.id)["ok"])
        match.invalidate_recordset()
        slot.invalidate_recordset()
        self.assertEqual(match.slot_id, slot)
        self.assertEqual(slot.match_id, match)
        self.assertEqual(match.round_id, gameday)
        self.assertEqual(match.state, "scheduled")

        self.service.unassign_match(match.id)
        match.invalidate_recordset()
        slot.invalidate_recordset()
        self.assertFalse(match.slot_id)
        self.assertFalse(match.round_id)
        self.assertFalse(slot.match_id)
        self.assertEqual(match.state, "draft")

    def test_unassigning_published_match_reopens_schedule_for_review(self):
        division, gameday = self._prepare_planned_division("Rollback Division")
        match = division.match_ids[:1]
        slot = gameday.slot_ids.filtered(lambda record: record.state == "available")[:1]

        self.assertTrue(
            self.service.with_user(self.manager_user).assign_match_to_slot(match.id, slot.id)["ok"]
        )
        self.assertTrue(
            self.service.with_user(self.manager_user).publish_gameday(gameday.id)["ok"]
        )

        self.service.with_user(self.manager_user).unassign_match(match.id)

        division.invalidate_recordset()
        gameday.invalidate_recordset()
        self.assertEqual(division.workspace_state, "planning")
        self.assertEqual(gameday.planner_state, "planned")

    def test_assign_match_rejects_stale_planner_revision(self):
        division, gameday = self._prepare_planned_division("Revision Assignment Division")
        match_a, match_b = division.match_ids[:2]
        slots = gameday.slot_ids.filtered(lambda slot: slot.state == "available").sorted(
            lambda slot: (slot.start_datetime, slot.playing_area_id.id)
        )
        stale_revision = gameday.planner_revision

        self.assertTrue(
            self.service.assign_match_to_slot(
                match_a.id,
                slots[0].id,
                False,
                stale_revision,
            )["ok"]
        )

        with self.assertRaises(ValidationError):
            self.service.assign_match_to_slot(
                match_b.id,
                slots[1].id,
                False,
                stale_revision,
            )

    def test_publish_gameday_rejects_stale_planner_revision(self):
        division, gameday = self._prepare_planned_division("Revision Publish Division")
        match = division.match_ids[:1]
        slot = gameday.slot_ids.filtered(lambda record: record.state == "available")[:1]
        stale_revision = gameday.planner_revision

        self.assertTrue(
            self.service.with_user(self.manager_user).assign_match_to_slot(
                match.id,
                slot.id,
                False,
                stale_revision,
            )["ok"]
        )

        with self.assertRaises(ValidationError):
            self.service.with_user(self.manager_user).publish_gameday(
                gameday.id,
                stale_revision,
            )

    def test_workspace_extension_issues_normalizes_contract(self):
        malformed_results = [
            {
                "blocking": [
                    {
                        "code": "team_overlap",
                        "message": "Team already plays in this timeslot.",
                        "record_id": "42",
                        "team_ids": [3, "1", "bad"],
                    },
                    {"message": "missing code"},
                    "invalid-issue",
                ],
                "warnings": {
                    "code": "short_rest",
                    "message": "Short rest warning",
                    "slot_id": "7",
                },
            },
            ["invalid-result-shape"],
            {
                "blocking": {"code": "slot_occupied", "message": "Slot busy", "slot_id": "11"},
                "warnings": [{"code": "", "message": "invalid warning"}],
            },
        ]

        with patch.object(
            type(self.service),
            "_workspace_extension_results",
            return_value=malformed_results,
        ):
            issues = self.service._workspace_extension_issues(
                "extend_match_assignment_validation"
            )

        self.assertEqual(len(issues["blocking"]), 2)
        self.assertEqual(len(issues["warnings"]), 1)
        first_blocking = issues["blocking"][0]
        self.assertEqual(first_blocking["record_id"], 42)
        self.assertEqual(first_blocking["team_ids"], [1, 3])
        self.assertEqual(issues["warnings"][0]["slot_id"], 7)
        self.assertEqual(issues["blocking"][1]["slot_id"], 11)

    def test_gameday_planner_data_reports_stale_consistency(self):
        division, gameday = self._prepare_planned_division(
            "Planner Consistency Division"
        )
        stale_revision = gameday.planner_revision
        match = division.match_ids[:1]
        slot = gameday.slot_ids.filtered(lambda record: record.state == "available")[:1]

        self.assertTrue(self.service.assign_match_to_slot(match.id, slot.id)["ok"])

        planner = self.service.get_gameday_planner_data(
            gameday.id,
            {"expected_planner_revision": stale_revision},
        )

        self.assertTrue(planner["consistency"]["is_stale"])
        self.assertEqual(
            planner["consistency"]["expected_planner_revision"], stale_revision
        )
        self.assertGreater(
            planner["consistency"]["current_planner_revision"], stale_revision
        )

    def test_workspace_payload_forwards_expected_planner_revision_consistency(self):
        division, gameday = self._prepare_planned_division(
            "Workspace Consistency Forwarding Division"
        )

        payload = self.service.get_competition_workspace_data(
            self.edition.id,
            division.id,
            {
                "include_planner": True,
                "gameday_id": gameday.id,
                "expected_planner_revision": "invalid-revision",
            },
        )

        self.assertFalse(payload["planner"]["consistency"]["is_stale"])
        self.assertTrue(
            payload["planner"]["consistency"]["invalid_expected_planner_revision"]
        )
        self.assertFalse(payload["planner"]["consistency"]["expected_planner_revision"])

    def test_merge_planner_validations_keeps_distinct_slot_conflicts(self):
        merged = self.service._merge_planner_validations(
            {
                "valid": False,
                "blocking": [
                    {
                        "code": "team_overlap",
                        "message": "Team already plays in this timeslot.",
                        "record_id": 42,
                        "match_id": 42,
                        "slot_id": 10,
                        "team_ids": [1, 3],
                    }
                ],
                "warnings": [],
                "unscheduled_matches": [],
                "empty_slots": [],
            },
            {
                "valid": False,
                "blocking": [
                    {
                        "code": "team_overlap",
                        "message": "Team already plays in this timeslot.",
                        "record_id": 42,
                        "match_id": 42,
                        "slot_id": 11,
                        "team_ids": [3, 1],
                    }
                ],
                "warnings": [],
                "unscheduled_matches": [],
                "empty_slots": [],
            },
            {
                "valid": False,
                "blocking": [
                    {
                        "code": "team_overlap",
                        "message": "Team already plays in this timeslot.",
                        "record_id": 42,
                        "match_id": 42,
                        "slot_id": 10,
                        "team_ids": [1, 3],
                    }
                ],
                "warnings": [],
                "unscheduled_matches": [],
                "empty_slots": [],
            },
        )

        self.assertEqual(len(merged["blocking"]), 2)
        self.assertEqual({issue["slot_id"] for issue in merged["blocking"]}, {10, 11})

    def test_assign_match_accepts_blank_expected_planner_revision_token(self):
        division, gameday = self._prepare_planned_division("Blank Revision Token Division")
        match = division.match_ids[:1]
        slot = gameday.slot_ids.filtered(lambda record: record.state == "available")[:1]

        result = self.service.assign_match_to_slot(
            match.id,
            slot.id,
            False,
            "   ",
        )

        self.assertTrue(result["ok"])

    def test_assign_match_rejects_invalid_expected_planner_revision_token(self):
        division, gameday = self._prepare_planned_division("Invalid Revision Token Division")
        match = division.match_ids[:1]
        slot = gameday.slot_ids.filtered(lambda record: record.state == "available")[:1]

        with self.assertRaises(ValidationError):
            self.service.assign_match_to_slot(
                match.id,
                slot.id,
                False,
                "not-a-revision",
            )

    def test_schedule_revisions_keep_live_draft_and_superseded_versions(self):
        division, gameday = self._prepare_planned_division("Schedule Revision Division")
        match_a = division.match_ids[:1]
        match_b = division.match_ids.filtered(
            lambda match: match != match_a
            and match.home_team_id
            not in (match_a.home_team_id, match_a.away_team_id)
            and match.away_team_id
            not in (match_a.home_team_id, match_a.away_team_id)
        )[:1]
        slots = gameday.slot_ids.filtered(lambda slot: slot.state == "available").sorted(
            lambda slot: (slot.start_datetime, slot.playing_area_id.id)
        )

        gameday.invalidate_recordset()
        initial_draft = gameday.schedule_draft_revision_id
        self.assertTrue(initial_draft)
        self.assertEqual(initial_draft.state, "draft")

        self.assertTrue(
            self.service.with_user(self.manager_user).assign_match_to_slot(
                match_a.id,
                slots[0].id,
            )["ok"]
        )

        first_publish = self.service.with_user(self.manager_user).publish_gameday(
            gameday.id
        )

        self.assertTrue(first_publish["ok"])
        gameday.invalidate_recordset()
        first_live_revision = gameday.schedule_live_revision_id
        self.assertTrue(first_live_revision)
        self.assertEqual(first_live_revision.state, "live")
        self.assertFalse(gameday.schedule_draft_revision_id)

        self.assertTrue(
            self.service.with_user(self.manager_user).assign_match_to_slot(
                match_b.id,
                slots[1].id,
            )["ok"]
        )

        gameday.invalidate_recordset()
        draft_revision = gameday.schedule_draft_revision_id
        self.assertTrue(draft_revision)
        self.assertEqual(draft_revision.state, "draft")
        self.assertEqual(draft_revision.based_on_revision_id, first_live_revision)

        republish_without_reason = self.service.with_user(
            self.manager_user
        ).publish_gameday(gameday.id)

        self.assertFalse(republish_without_reason["ok"])
        self.assertEqual(
            republish_without_reason["validation"]["blocking"][0]["code"],
            "override_reason_required",
        )

        republish_result = self.service.with_user(self.manager_user).publish_gameday(
            gameday.id,
            override_reason="Republished after court-balancing adjustment.",
        )

        self.assertTrue(republish_result["ok"])
        first_live_revision.invalidate_recordset()
        gameday.invalidate_recordset()
        self.assertEqual(first_live_revision.state, "superseded")
        self.assertFalse(gameday.schedule_draft_revision_id)
        self.assertEqual(gameday.schedule_live_revision_id.state, "live")
        self.assertEqual(
            gameday.schedule_live_revision_id.override_reason,
            "Republished after court-balancing adjustment.",
        )
        planner_data = self.service.get_gameday_planner_data(gameday.id)
        self.assertTrue(planner_data["gameday"]["schedule_revisions"]["live_revision"])
        self.assertFalse(
            planner_data["gameday"]["schedule_revisions"]["draft_revision"]
        )

    def test_workspace_presence_reports_same_gameday_editors(self):
        division, gameday = self._prepare_planned_division("Presence Division")

        self.service.with_user(self.planner_user).heartbeat_workspace_presence(
            self.edition.id,
            division.id,
            gameday.id,
            "planner",
        )
        summary = self.service.with_user(self.manager_user).heartbeat_workspace_presence(
            self.edition.id,
            division.id,
            gameday.id,
            "planner",
        )

        self.assertTrue(summary["planner_collaboration"]["has_same_gameday_editors"])
        self.assertEqual(summary["planner_collaboration"]["same_gameday_count"], 1)
        self.assertEqual(
            summary["planner_collaboration"]["same_gameday_users"][0]["user_id"],
            self.planner_user.id,
        )
        self.assertEqual(
            summary["planner_collaboration"]["same_gameday_users"][0]["active_section"],
            "planner",
        )

    def test_validation_payload_groups_conflicts_with_hints_and_focus(self):
        division, gameday = self._prepare_planned_division(
            "Explainable Conflict Division"
        )
        team_1_matches = division.match_ids.filtered(
            lambda match: match.home_team_id == self.teams[0]
            or match.away_team_id == self.teams[0]
        )
        match_a = team_1_matches[0]
        match_b = team_1_matches[1]
        first_row_slots = gameday.slot_ids.filtered(
            lambda slot: slot.start_datetime
            == min(gameday.slot_ids.mapped("start_datetime"))
        ).sorted(lambda slot: slot.playing_area_id.id)

        self.assertTrue(
            self.service.assign_match_to_slot(match_a.id, first_row_slots[0].id)["ok"]
        )

        overlap_result = self.service.assign_match_to_slot(
            match_b.id,
            first_row_slots[1].id,
        )

        self.assertFalse(overlap_result["ok"])
        validation = overlap_result["validation"]
        self.assertTrue(validation["blocking_groups"])
        self.assertEqual(validation["blocking_groups"][0]["key"], "team_conflicts")
        self.assertEqual(validation["blocking_groups"][0]["count"], 1)
        self.assertEqual(validation["blocking"][0]["severity"], "blocking")
        self.assertEqual(validation["blocking"][0]["focus_target"], "team")
        self.assertTrue(validation["blocking"][0]["hint"])

    def test_validation_issue_signature_keeps_distinct_slots(self):
        validation_service = self.env[
            "federation.competition.workspace.validation.service"
        ]
        issues = []
        dedupe = set()

        base_issue = {
            "code": "team_overlap",
            "record_id": 42,
            "match_id": 42,
            "message": "Team already plays in this timeslot.",
            "team_ids": [3, 1],
        }

        validation_service._append_issue(
            issues,
            {**base_issue, "slot_id": 10},
            dedupe,
        )
        validation_service._append_issue(
            issues,
            {**base_issue, "slot_id": 11},
            dedupe,
        )
        validation_service._append_issue(
            issues,
            {**base_issue, "slot_id": 10, "team_ids": [1, 3]},
            dedupe,
        )

        self.assertEqual(len(issues), 2)
        self.assertEqual({issue["slot_id"] for issue in issues}, {10, 11})

    def test_shared_gameday_assignment_keeps_match_on_its_division_round(self):
        _host_division, guest_division, host_gameday, guest_gameday = (
            self._prepare_shared_planned_divisions()
        )
        guest_match = guest_division.match_ids[:1]
        slot = host_gameday.slot_ids.filtered(
            lambda record: record.state == "available"
        )[:1]

        result = self.service.assign_match_to_slot(guest_match.id, slot.id)

        self.assertTrue(result["ok"])
        guest_match.invalidate_recordset()
        slot.invalidate_recordset()
        self.assertEqual(guest_match.slot_id, slot)
        self.assertEqual(guest_match.round_id, guest_gameday)
        self.assertEqual(guest_match.round_id.tournament_id, guest_division)
        self.assertEqual(slot.match_id, guest_match)

    def test_shared_gameday_rejects_unlinked_division_assignments(self):
        _host_division, _guest_division, host_gameday, _guest_gameday = (
            self._prepare_shared_planned_divisions()
        )
        outsider_division, _participants = self._create_division(
            "Outsider Division",
            4,
            team_offset=0,
        )
        outsider_division.action_lock_team_entries()
        self.service.generate_round_robin(outsider_division.id)
        outsider_match = outsider_division.match_ids[:1]
        slot = host_gameday.slot_ids.filtered(
            lambda record: record.state == "available"
        )[:1]

        result = self.service.assign_match_to_slot(outsider_match.id, slot.id)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["validation"]["blocking"][0]["code"],
            "cross_division_slot",
        )

    def test_shared_gameday_planner_payload_uses_shared_slots_for_guest_division(self):
        host_division, guest_division, host_gameday, guest_gameday = (
            self._prepare_shared_planned_divisions()
        )

        planner = self.service.get_gameday_planner_data(guest_gameday.id)
        workspace_payload = self.service.get_competition_workspace_data(
            self.edition.id,
            guest_division.id,
        )

        self.assertEqual(planner["gameday"]["id"], guest_gameday.id)
        self.assertEqual(planner["gameday"]["planner_root_id"], host_gameday.id)
        self.assertEqual(len(planner["slots"]), len(host_gameday.slot_ids))
        self.assertEqual(
            {division["id"] for division in planner["participating_divisions"]},
            {host_division.id, guest_division.id},
        )
        self.assertEqual(
            {match["division_id"] for match in planner["unscheduled_matches"]},
            {host_division.id, guest_division.id},
        )
        self.assertEqual(workspace_payload["planner"]["gameday"]["id"], guest_gameday.id)
        self.assertEqual(
            workspace_payload["selected_division"]["slot_count"],
            len(host_gameday.slot_ids),
        )

    def test_shared_gameday_planner_payload_filters_unscheduled_matches_by_division(self):
        host_division, guest_division, _host_gameday, guest_gameday = (
            self._prepare_shared_planned_divisions()
        )

        mixed_planner = self.service.get_gameday_planner_data(guest_gameday.id)
        guest_only_planner = self.service.get_gameday_planner_data(
            guest_gameday.id,
            {"division_id": guest_division.id},
        )

        self.assertEqual(
            {match["division_id"] for match in mixed_planner["unscheduled_matches"]},
            {host_division.id, guest_division.id},
        )
        self.assertEqual(
            {match["division_id"] for match in guest_only_planner["unscheduled_matches"]},
            {guest_division.id},
        )
        self.assertLess(
            len(guest_only_planner["unscheduled_matches"]),
            len(mixed_planner["unscheduled_matches"]),
        )
        self.assertEqual(
            {
                division["id"]
                for division in guest_only_planner["participating_divisions"]
            },
            {host_division.id, guest_division.id},
        )

    def test_assignment_history_supports_undo_and_redo(self):
        division, gameday = self._prepare_planned_division("Planner History Division")
        match = division.match_ids[:1]
        slot = gameday.slot_ids.filtered(lambda record: record.state == "available")[:1]

        assign_result = self.service.assign_match_to_slot(match.id, slot.id)

        self.assertTrue(assign_result["ok"])
        self.assertTrue(assign_result["planner"]["can_undo"])
        self.assertFalse(assign_result["planner"]["can_redo"])
        self.assertEqual(
            assign_result["planner"]["operation_history"][0]["operation_type"],
            "assign",
        )

        undo_result = self.service.undo_last_planner_operation(
            gameday.id,
            assign_result["planner"]["gameday"]["planner_revision"],
        )

        self.assertTrue(undo_result["ok"])
        match.invalidate_recordset()
        self.assertFalse(match.slot_id)
        self.assertTrue(undo_result["planner"]["can_redo"])
        self.assertEqual(
            undo_result["planner"]["operation_history"][0]["state"],
            "undone",
        )

        redo_result = self.service.redo_last_planner_operation(
            gameday.id,
            undo_result["planner"]["gameday"]["planner_revision"],
        )

        self.assertTrue(redo_result["ok"])
        match.invalidate_recordset()
        self.assertEqual(match.slot_id, slot)
        self.assertTrue(redo_result["planner"]["can_undo"])
        self.assertFalse(redo_result["planner"]["can_redo"])

    def test_bulk_assign_matches_uses_batch_undo_and_redo(self):
        division, gameday = self._prepare_planned_division("Bulk Assign Division")
        matches = division.match_ids.sorted(lambda record: record.id)[:2]

        bulk_result = self.service.bulk_assign_matches(gameday.id, matches.ids)

        self.assertTrue(bulk_result["ok"])
        self.assertEqual(bulk_result["operation_count"], 2)
        for match in matches:
            match.invalidate_recordset()
            self.assertTrue(match.slot_id)

        undo_result = self.service.undo_last_planner_operation(
            gameday.id,
            bulk_result["planner"]["gameday"]["planner_revision"],
        )

        self.assertTrue(undo_result["ok"])
        for match in matches:
            match.invalidate_recordset()
            self.assertFalse(match.slot_id)

        redo_result = self.service.redo_last_planner_operation(
            gameday.id,
            undo_result["planner"]["gameday"]["planner_revision"],
        )

        self.assertTrue(redo_result["ok"])
        for match in matches:
            match.invalidate_recordset()
            self.assertTrue(match.slot_id)

    def test_swap_history_supports_batch_undo_and_redo(self):
        division, gameday = self._prepare_planned_division("Swap History Division")
        match_a = division.match_ids[:1]
        match_b = division.match_ids.filtered(
            lambda match: match != match_a
            and match.home_team_id not in (match_a.home_team_id, match_a.away_team_id)
            and match.away_team_id not in (match_a.home_team_id, match_a.away_team_id)
        )[:1]
        slots = gameday.slot_ids.filtered(lambda slot: slot.state == "available").sorted(
            lambda slot: (slot.start_datetime, slot.playing_area_id.id)
        )

        self.assertTrue(self.service.assign_match_to_slot(match_a.id, slots[0].id)["ok"])
        self.assertTrue(self.service.assign_match_to_slot(match_b.id, slots[1].id)["ok"])

        swap_result = self.service.assign_match_to_slot(match_a.id, slots[1].id)

        self.assertTrue(swap_result["ok"])

        undo_result = self.service.undo_last_planner_operation(
            gameday.id,
            swap_result["planner"]["gameday"]["planner_revision"],
        )

        self.assertTrue(undo_result["ok"])
        match_a.invalidate_recordset()
        match_b.invalidate_recordset()
        self.assertEqual(match_a.slot_id, slots[0])
        self.assertEqual(match_b.slot_id, slots[1])
        self.assertTrue(undo_result["planner"]["can_redo"])

        redo_result = self.service.redo_last_planner_operation(
            gameday.id,
            undo_result["planner"]["gameday"]["planner_revision"],
        )

        self.assertTrue(redo_result["ok"])
        match_a.invalidate_recordset()
        match_b.invalidate_recordset()
        self.assertEqual(match_a.slot_id, slots[1])
        self.assertEqual(match_b.slot_id, slots[0])

    def test_bulk_assign_matches_rejects_when_slots_are_insufficient(self):
        division, _participants = self._create_division("Tight Slots Division", 4)
        division.action_lock_team_entries()
        self.service.generate_round_robin(division.id)
        gameday_id = self.service.create_gameday(
            {
                "division_id": division.id,
                "name": "Tight Slots Day",
                "round_date": "2026-10-10",
                "venue_id": self.venue.id,
            }
        )["gameday_id"]
        gameday = self.env["federation.tournament.round"].browse(gameday_id)
        self.service.generate_slots(
            gameday.id,
            [self.court_1.id],
            "09:00",
            "09:30",
            30,
            0,
            [],
            False,
        )

        result = self.service.bulk_assign_matches(gameday.id, division.match_ids[:2].ids)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["validation"]["blocking"][0]["code"],
            "insufficient_open_slots",
        )

    def test_bulk_unassign_matches_records_history(self):
        division, gameday = self._prepare_planned_division("Bulk Unassign Division")
        matches = division.match_ids.sorted(lambda record: record.id)[:2]

        assign_result = self.service.bulk_assign_matches(gameday.id, matches.ids)
        self.assertTrue(assign_result["ok"])

        unassign_result = self.service.bulk_unassign_matches(
            gameday.id,
            matches.ids,
            assign_result["planner"]["gameday"]["planner_revision"],
        )

        self.assertTrue(unassign_result["ok"])
        self.assertEqual(unassign_result["operation_count"], 2)
        self.assertEqual(
            unassign_result["planner"]["operation_history"][0]["operation_type"],
            "unassign",
        )
        for match in matches:
            match.invalidate_recordset()
            self.assertFalse(match.slot_id)

    def test_workspace_payload_can_skip_planner_payload(self):
        division, gameday = self._prepare_planned_division("Lazy Payload Division")

        payload = self.service.get_competition_workspace_data(
            self.edition.id,
            division.id,
            {"include_planner": False},
        )
        payload_with_planner = self.service.get_competition_workspace_data(
            self.edition.id,
            division.id,
            {"include_planner": True, "gameday_id": gameday.id},
        )

        self.assertFalse(payload["planner"])
        self.assertEqual(payload_with_planner["planner"]["gameday"]["id"], gameday.id)
        self.assertIsInstance(
            payload_with_planner["planner"]["gameday"]["planner_revision"],
            int,
        )

    def test_gameday_planner_data_limits_unscheduled_matches(self):
        division, gameday = self._prepare_planned_division("Paginated Planner Division")

        planner = self.service.get_gameday_planner_data(
            gameday.id,
            {"unscheduled_limit": 2},
        )

        self.assertEqual(planner["division"]["id"], division.id)
        self.assertEqual(planner["unscheduled_total_count"], 6)
        self.assertEqual(planner["unscheduled_loaded_count"], 2)
        self.assertTrue(planner["unscheduled_has_more"])
        self.assertEqual(len(planner["unscheduled_matches"]), 2)

    def test_workspace_payload_forwards_planner_filters_and_can_trim_reference_data(self):
        division, gameday = self._prepare_planned_division(
            "Trimmed Planner Payload Division"
        )

        payload = self.service.get_competition_workspace_data(
            self.edition.id,
            division.id,
            {
                "include_planner": True,
                "include_planner_reference_data": False,
                "gameday_id": gameday.id,
                "planner_filters": {
                    "round_number": 1,
                    "unscheduled_limit": 1,
                },
            },
        )

        self.assertEqual(payload["planner"]["unscheduled_total_count"], 2)
        self.assertEqual(payload["planner"]["unscheduled_loaded_count"], 1)
        self.assertTrue(payload["planner"]["unscheduled_has_more"])
        self.assertEqual(len(payload["planner"]["unscheduled_matches"]), 1)
        self.assertEqual(payload["planner"]["unscheduled_matches"][0]["round_number"], 1)
        self.assertNotIn("participating_divisions", payload["planner"])
        self.assertNotIn("team_options", payload["planner"])
        self.assertNotIn("courts", payload["planner"])

    def test_gameday_planner_data_ignores_invalid_numeric_filters(self):
        division, gameday = self._prepare_planned_division("Invalid Planner Filter Division")

        planner = self.service.get_gameday_planner_data(
            gameday.id,
            {
                "division_id": "not-a-number",
                "round_number": "oops",
                "team_id": "bad",
            },
        )

        self.assertEqual(planner["division"]["id"], division.id)
        self.assertEqual(planner["unscheduled_total_count"], 6)
        self.assertEqual(planner["unscheduled_loaded_count"], 6)
        self.assertFalse(planner["unscheduled_has_more"])

    def test_workspace_payload_ignores_invalid_planner_gameday_id(self):
        division, gameday = self._prepare_planned_division("Invalid Planner Target Division")

        payload = self.service.get_competition_workspace_data(
            self.edition.id,
            division.id,
            {
                "include_planner": True,
                "gameday_id": "invalid-gameday-id",
            },
        )

        self.assertTrue(payload["planner"])
        self.assertEqual(payload["planner"]["gameday"]["id"], gameday.id)

    def test_search_available_teams_filters_division_and_club(self):
        division, _participants = self._create_division("Search Division", 2)
        other_club = self.env["federation.club"].create({"name": "Search Club"})
        searchable_same_club = self.env["federation.team"].create(
            {
                "name": "Searchable Alpha",
                "club_id": self.club.id,
            }
        )
        self.env["federation.team"].create(
            {
                "name": "Searchable Beta",
                "club_id": other_club.id,
            }
        )

        results = self.service.search_available_teams(
            division.id,
            {
                "query": "Searchable",
                "club_id": self.club.id,
                "limit": 20,
            },
        )

        self.assertEqual([team["id"] for team in results], [searchable_same_club.id])

    def test_shared_gameday_guest_validation_uses_root_slots(self):
        _host_division, _guest_division, host_gameday, guest_gameday = (
            self._prepare_shared_planned_divisions()
        )

        host_validation = self.service.validate_gameday(host_gameday.id)
        guest_validation = self.service.validate_gameday(guest_gameday.id)

        self.assertEqual(
            {issue["slot_id"] for issue in host_validation["empty_slots"]},
            {issue["slot_id"] for issue in guest_validation["empty_slots"]},
        )
        self.assertEqual(host_validation["blocking"], guest_validation["blocking"])
        self.assertEqual(host_validation["warnings"], guest_validation["warnings"])

    def test_shared_gameday_guest_publish_uses_root_validation(self):
        _host_division, guest_division, host_gameday, guest_gameday = (
            self._prepare_shared_planned_divisions()
        )
        guest_team_matches = guest_division.match_ids.filtered(
            lambda match: match.home_team_id == self.teams[4]
            or match.away_team_id == self.teams[4]
        )
        match_a = guest_team_matches[0]
        match_b = guest_team_matches[1]
        first_row_slots = host_gameday.slot_ids.filtered(
            lambda slot: slot.start_datetime
            == min(host_gameday.slot_ids.mapped("start_datetime"))
        ).sorted(lambda slot: slot.playing_area_id.id)

        match_a.write(
            {
                "slot_id": first_row_slots[0].id,
                "round_id": guest_gameday.id,
                "date_scheduled": first_row_slots[0].start_datetime,
            }
        )
        first_row_slots[0].write({"match_id": match_a.id})
        match_b.write(
            {
                "slot_id": first_row_slots[1].id,
                "round_id": guest_gameday.id,
                "date_scheduled": first_row_slots[1].start_datetime,
            }
        )
        first_row_slots[1].write({"match_id": match_b.id})

        root_validation = self.service.validate_gameday(host_gameday.id)
        self.assertIn(
            "team_overlap",
            {issue["code"] for issue in root_validation["blocking"]},
        )

        publish_result = self.service.with_user(self.manager_user).publish_gameday(
            guest_gameday.id
        )

        self.assertFalse(publish_result["ok"])
        self.assertIn(
            "team_overlap",
            {issue["code"] for issue in publish_result["validation"]["blocking"]},
        )

    def test_manager_can_publish_competition_schedule(self):
        division, _participants = self._create_division("Publish Division", 2)
        division.action_lock_team_entries()
        self.service.generate_round_robin(division.id)
        gameday_id = self.service.create_gameday(
            {
                "division_id": division.id,
                "name": "Publish Day",
                "round_date": "2026-10-12",
                "venue_id": self.venue.id,
            }
        )["gameday_id"]
        gameday = self.env["federation.tournament.round"].browse(gameday_id)
        self.service.generate_slots(
            gameday.id,
            [self.court_1.id],
            "09:00",
            "10:00",
            30,
            0,
            [],
            False,
        )
        match = division.match_ids[:1]
        slot = gameday.slot_ids[:1]
        self.assertTrue(self.service.assign_match_to_slot(match.id, slot.id)["ok"])

        publish_result = self.service.with_user(self.manager_user).publish_competition_schedule(
            self.edition.id,
            division.id,
        )

        self.assertTrue(publish_result["ok"])
        division.invalidate_recordset()
        gameday.invalidate_recordset()
        self.assertEqual(division.workspace_state, "published")
        self.assertEqual(gameday.planner_state, "published")

    def test_competition_republish_requires_override_reason_once_live_revision_exists(
        self,
    ):
        division, _participants = self._create_division("Republish Guard Division", 2)
        division.action_lock_team_entries()
        self.service.generate_round_robin(division.id)
        gameday_id = self.service.create_gameday(
            {
                "division_id": division.id,
                "name": "Republish Guard Day",
                "round_date": "2026-10-12",
                "venue_id": self.venue.id,
            }
        )["gameday_id"]
        gameday = self.env["federation.tournament.round"].browse(gameday_id)
        self.service.generate_slots(
            gameday.id,
            [self.court_1.id],
            "09:00",
            "10:00",
            30,
            0,
            [],
            False,
        )
        match = division.match_ids[:1]
        slot = gameday.slot_ids[:1]
        self.assertTrue(
            self.service.with_user(self.manager_user).assign_match_to_slot(match.id, slot.id)[
                "ok"
            ]
        )

        first_publish = self.service.with_user(self.manager_user).publish_competition_schedule(
            self.edition.id,
            division.id,
        )
        self.assertTrue(first_publish["ok"])

        republish_without_reason = self.service.with_user(
            self.manager_user
        ).publish_competition_schedule(
            self.edition.id,
            division.id,
        )
        self.assertFalse(republish_without_reason["ok"])
        self.assertEqual(
            republish_without_reason["validation"]["blocking"][0]["code"],
            "override_reason_required",
        )

        republish_with_reason = self.service.with_user(
            self.manager_user
        ).publish_competition_schedule(
            self.edition.id,
            division.id,
            override_reason="Republished after governance confirmation.",
        )
        self.assertTrue(republish_with_reason["ok"])

    def test_published_match_cannot_be_moved_by_planner_user(self):
        division, gameday = self._prepare_planned_division("Locked Publish Division")
        match = division.match_ids[:1]
        slot = gameday.slot_ids.filtered(lambda record: record.state == "available")[:1]
        self.assertTrue(
            self.service.with_user(self.manager_user).assign_match_to_slot(match.id, slot.id)["ok"]
        )
        self.assertTrue(
            self.service.with_user(self.manager_user).publish_gameday(gameday.id)["ok"]
        )

        with self.assertRaises(ValidationError):
            self.service.with_user(self.planner_user).unassign_match(match.id)

    def test_regular_user_cannot_access_workspace_service(self):
        with self.assertRaises(AccessError):
            self.service.with_user(self.regular_user).get_competition_workspace_data(
                self.edition.id,
                False,
            )
