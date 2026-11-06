import json
from unittest.mock import patch
from uuid import uuid4

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_competition_lifecycle", "sf_release_confidence")
class TestCompetitionLifecycleE2E(TransactionCase):
    """Exercise the contracted competition release path through Odoo commands."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env.ref
        internal = group("base.group_user")
        federation_manager = group("sports_federation_base.group_federation_manager")
        federation_user = group("sports_federation_base.group_federation_user")
        competition_administrator = group(
            "sports_federation_competition_core.group_competition_administrator"
        )
        registration_manager = group(
            "sports_federation_registration.group_registration_manager"
        )
        competition_designer = group(
            "sports_federation_format.group_competition_designer"
        )
        calendar_planner = group("sports_federation_calendar.group_calendar_planner")
        schedule_planner = group(
            "sports_federation_scheduling.group_schedule_planner"
        )
        schedule_approver = group(
            "sports_federation_schedule_approval.group_schedule_approver"
        )
        matchday_manager = group("sports_federation_matchday.group_matchday_manager")
        result_validator = group(
            "sports_federation_result_control.group_result_validator"
        )
        result_approver = group(
            "sports_federation_result_control.group_result_approver"
        )
        discipline_manager = group(
            "sports_federation_discipline.group_federation_discipline_manager"
        )

        users = cls.env["res.users"].with_context(no_reset_password=True)

        def make_user(name, suffix, groups):
            return users.create(
                {
                    "name": name,
                    "login": f"{suffix}@competition-lifecycle.invalid",
                    "email": f"{suffix}@competition-lifecycle.invalid",
                    "group_ids": [
                        Command.set(list({internal.id, federation_user.id, *groups}))
                    ],
                }
            )

        cls.organizer = make_user(
            "Lifecycle Organizer",
            "lifecycle.organizer",
            [
                competition_administrator.id,
                federation_manager.id,
                registration_manager.id,
                competition_designer.id,
                calendar_planner.id,
                schedule_planner.id,
                schedule_approver.id,
                matchday_manager.id,
                result_validator.id,
                result_approver.id,
                discipline_manager.id,
            ],
        )
        cls.schedule_planner = make_user(
            "Lifecycle Schedule Planner",
            "lifecycle.planner",
            [schedule_planner.id, calendar_planner.id, competition_designer.id],
        )
        cls.schedule_approver = make_user(
            "Lifecycle Schedule Approver", "lifecycle.schedule.approver", [schedule_approver.id]
        )
        cls.matchday_manager = make_user(
            "Lifecycle Match-Day Manager",
            "lifecycle.matchday.manager",
            [matchday_manager.id, calendar_planner.id],
        )
        cls.court_operator = make_user(
            "Lifecycle Court Operator", "lifecycle.court.operator", []
        )
        cls.result_submitter = make_user(
            "Lifecycle Result Submitter",
            "lifecycle.result.submitter",
            [federation_manager.id, competition_designer.id],
        )
        cls.result_validator = make_user(
            "Lifecycle Result Validator", "lifecycle.result.validator", [result_validator.id]
        )
        cls.result_approver = make_user(
            "Lifecycle Result Approver", "lifecycle.result.approver", [result_approver.id]
        )
        cls.discipline_officer = make_user(
            "Lifecycle Discipline Officer",
            "lifecycle.discipline.officer",
            [federation_manager.id, discipline_manager.id],
        )

        cls.season = cls.env["federation.season"].create(
            {
                "name": "Competition Lifecycle Season 2027",
                "code": "LCE27",
                "date_start": "2026-01-01",
                "date_end": "2027-12-31",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Competition Lifecycle Rules",
                "code": "LCE-RULES",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
                "squad_min_size": 1,
                "squad_max_size": 18,
                "gameday_roster_max_size": 14,
                "match_player_max_size": 12,
            }
        )
        cls.env["federation.points.rule"].create(
            [
                {"rule_set_id": cls.rule_set.id, "result_type": "bye", "points": 4},
                {"rule_set_id": cls.rule_set.id, "result_type": "forfeit_win", "points": 7},
                {"rule_set_id": cls.rule_set.id, "result_type": "forfeit_loss", "points": 1},
            ]
        )
        cls.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": cls.rule_set.id,
                "name": "Suspended players cannot participate",
                "eligibility_type": "suspension",
            }
        )
        cls.competition_template = cls.env["federation.competition"].create(
            {
                "name": "Competition Lifecycle Template",
                "competition_type": "league",
            }
        )
        cls.venue = cls.env["federation.venue"].create(
            {"name": "Competition Lifecycle Venue"}
        )
        cls.courts = cls.env["federation.playing.area"].create(
            [
                {"name": "Lifecycle Court 1", "venue_id": cls.venue.id},
                {"name": "Lifecycle Court 2", "venue_id": cls.venue.id},
            ]
        )
        cls.teams = cls.env["federation.team"]
        cls.players_by_team = {}
        for team_index in range(1, 5):
            club = cls.env["federation.club"].create(
                {"name": f"Lifecycle Club {team_index}", "code": f"LC{team_index}"}
            )
            team = cls.env["federation.team"].create(
                {
                    "name": f"Lifecycle Team {team_index}",
                    "club_id": club.id,
                    "category": "senior",
                    "gender": "male",
                }
            )
            cls.teams |= team
            roster = cls.env["federation.team.roster"].create(
                {
                    "name": f"Lifecycle Roster {team_index}",
                    "team_id": team.id,
                    "season_id": cls.season.id,
                    "competition_id": cls.competition_template.id,
                    "rule_set_id": cls.rule_set.id,
                }
            )
            players = cls.env["federation.player"]
            for player_index in range(1, 15):
                player = cls.env["federation.player"].create(
                    {
                        "first_name": f"Team {team_index}",
                        "last_name": f"Player {player_index}",
                        "birth_date": "1995-01-01",
                        "gender": "male",
                        "club_id": club.id,
                        "team_ids": [Command.set([team.id])],
                    }
                )
                license_record = cls.env["federation.player.license"].create(
                    {
                        "name": f"LCE27-{team_index:02d}-{player_index:02d}",
                        "player_id": player.id,
                        "season_id": cls.season.id,
                        "club_id": club.id,
                        "issue_date": "2026-01-01",
                        "expiry_date": "2027-12-31",
                        "category": "senior",
                    }
                )
                license_record.action_activate()
                players |= player
                cls.env["federation.team.roster.line"].create(
                    {
                        "roster_id": roster.id,
                        "player_id": player.id,
                        "license_id": license_record.id,
                    }
                )
            roster.action_activate()
            cls.players_by_team[team.id] = players

    def _create_competition(
        self,
        suffix,
        *,
        format_type="single_round_robin",
        workflow_mode="simple",
        setup_template="league",
        team_count=4,
        day_count=2,
    ):
        wizard = self.env["federation.create.competition.wizard"].with_user(
            self.organizer
        ).create(
            {
                "setup_template": setup_template,
                "competition_id": self.competition_template.id,
                "name": f"Lifecycle {suffix}",
                "season_id": self.season.id,
                "date_start": "2027-03-01",
                "date_end": (
                    "2027-03-01"
                    if setup_template == "tournament_day"
                    else "2027-12-31"
                ),
                "rule_set_id": self.rule_set.id,
                "workflow_mode": workflow_mode,
                "default_venue_id": self.venue.id,
                "default_format_type": format_type,
                "default_start_hour": 9.0,
                "default_end_hour": 18.0,
                "default_slot_duration_minutes": 40,
                "division_line_ids": [
                    Command.create(
                        {
                            "name": f"Lifecycle {suffix} Division",
                            "code": f"{suffix[:8].upper()}-DIV",
                            "category": "senior",
                            "gender": "male",
                            "tournament_type": (
                                "single_day" if setup_template == "tournament_day" else "multi_day"
                            ),
                        }
                    )
                ],
                "role_line_ids": [
                    Command.create({"role": "administrator", "user_id": self.organizer.id}),
                    Command.create({"role": "registration_manager", "user_id": self.organizer.id}),
                    Command.create({"role": "competition_designer", "user_id": self.organizer.id}),
                    Command.create({"role": "calendar_planner", "user_id": self.organizer.id}),
                    Command.create({"role": "schedule_planner", "user_id": self.schedule_planner.id}),
                    Command.create({"role": "schedule_approver", "user_id": self.schedule_approver.id}),
                    Command.create({"role": "matchday_manager", "user_id": self.matchday_manager.id}),
                    Command.create({"role": "competition_director", "user_id": self.organizer.id}),
                ],
            }
        )
        action = wizard.with_user(self.organizer).action_create_competition()
        edition = self.env["federation.competition.edition"].browse(
            action["params"]["edition_id"]
        )
        picker_action = edition.with_user(self.organizer).action_setup_participants()
        picker = self.env[picker_action["res_model"]].with_user(self.organizer).browse(
            picker_action["res_id"]
        )
        picker.write({"team_ids": [Command.set(self.teams[:team_count].ids)]})
        picker.with_user(self.organizer).action_apply()

        format_action = edition.with_user(self.organizer).action_setup_format()
        format_wizard = self.env[format_action["res_model"]].with_user(
            self.organizer
        ).browse(format_action["res_id"])
        format_wizard.write(
            {"format_type": format_type, "preview_confirmed": True}
        )
        format_wizard.with_user(self.organizer).action_apply()

        gameday_action = edition.with_user(self.organizer).action_setup_gamedays()
        gameday_wizard = self.env[gameday_action["res_model"]].with_user(
            self.organizer
        ).browse(gameday_action["res_id"])
        for _index in range(day_count):
            gameday_wizard.with_user(self.organizer).action_add_day()
        gameday_wizard.with_user(self.organizer).action_save_close()
        return edition

    def _plan_schedules(self, edition):
        action = edition.with_user(self.schedule_planner).action_setup_schedule()
        wizard = self.env[action["res_model"]].with_user(self.schedule_planner).browse(
            action["res_id"]
        )
        wizard.with_user(self.schedule_planner).action_preview()
        wizard.with_user(self.schedule_planner).action_apply()
        return self.env["federation.schedule"].search(
            [("edition_id", "=", edition.id)], order="matchday_id,id"
        )

    def _publish_schedules(self, schedules):
        for schedule in schedules:
            action = schedule.with_user(self.schedule_planner).action_submit_for_review()
            if schedule.edition_id.schedule_approval_required:
                review = self.env["federation.schedule.review"].browse(action["res_id"])
                review.with_user(self.schedule_approver).action_approve_schedule()
                publish_action = review.with_user(self.schedule_approver).action_publish_schedule()
                publish_wizard = self.env[publish_action["res_model"]].with_user(
                    self.schedule_approver
                ).browse(publish_action["res_id"])
                publish_wizard.action_publish()
        return schedules

    def _create_court_access(self, matchday):
        courts = matchday.slot_ids.mapped("court_id")
        access = self.env["federation.court.access"].with_user(self.matchday_manager)
        for court in courts:
            access.create(
                {
                    "matchday_id": matchday.id,
                    "court_id": court.id,
                    "user_id": self.court_operator.id,
                }
            )

    def _prepare_gameday_rosters(self, matchday):
        teams = (
            matchday.published_match_ids.mapped("home_team_id")
            | matchday.published_match_ids.mapped("away_team_id")
        ).sorted("id")
        prepared = self.env["federation.team"]
        for _index in range(len(teams)):
            action = matchday.with_user(self.organizer).action_prepare_lineups()
            self.assertEqual(action["res_model"], "federation.gameday.lineup.wizard")
            wizard = self.env[action["res_model"]].with_user(self.organizer).browse(
                action["res_id"]
            )
            self.assertIn(wizard.team_id, teams - prepared)
            self.assertEqual(len(wizard.line_ids), 14)
            team = wizard.team_id
            wizard.with_user(self.organizer).action_save_submit()
            sheets = self.env["federation.match.sheet"].search(
                [
                    ("match_id.schedule_publication_id.matchday_id", "=", matchday.id),
                    ("team_id", "=", team.id),
                ]
            )
            submitted = sheets.filtered(lambda sheet: sheet.state == "submitted")
            if submitted:
                submitted.with_user(self.organizer).action_approve()
            self.assertEqual(set(sheets.mapped("state")), {"approved"})
            expected_players = set(self.players_by_team[team.id].ids)
            self.assertTrue(
                all(
                    set(sheet.line_ids.mapped("player_id").ids) == expected_players
                    for sheet in sheets
                )
            )
            self.assertEqual(len(set(sheets.mapped("roster_id").ids)), 1)
            prepared |= team
        self.assertEqual(prepared, teams)
        return self.env["federation.match.sheet"].search(
            [("match_id.schedule_publication_id.matchday_id", "=", matchday.id)]
        )

    def _cross_out(self, match, team, indexes=(0, 1)):
        sheet = self.env["federation.match.sheet"].search(
            [("match_id", "=", match.id), ("team_id", "=", team.id)], limit=1
        )
        self.assertTrue(sheet)
        player_ids = [sheet.line_ids.sorted("id")[index].player_id.id for index in indexes]
        sheet.with_user(self.organizer).action_set_crossed_out(player_ids)
        return sheet

    def _open_gameday(self, matchday):
        self._create_court_access(matchday)
        result = self.env["federation.matchday.commands"].with_user(
            self.matchday_manager
        ).open_matchday(matchday.id)
        self.assertEqual(matchday.state, "open")
        self.assertTrue(result["session_id"])
        return result

    def _court_command(self, command_service, matchday, match, operation, payload, base):
        return command_service.sync(
            matchday.id,
            (match.operational_slot_id or match.published_slot_id).court_id.id,
            match.id,
            [
                {
                    "key": uuid4().hex,
                    "revision": base["revision"],
                    "operation": operation,
                    "payload": payload,
                    "signature": base["signature"],
                }
            ],
        )

    def _court_result(
        self,
        matchday,
        match,
        *,
        home=2,
        away=1,
        outcome="normal",
        reason="",
        save=True,
    ):
        command_service = self.env["federation.court.commands"].with_user(
            self.court_operator
        )
        slot = match.operational_slot_id or match.published_slot_id
        opened = command_service.open_match(matchday.id, slot.court_id.id, match.id)
        payload = {
            "home": home,
            "away": away,
            "periods": [],
            "outcome": outcome,
            "reason": reason,
            "zero_confirmed": False,
        }
        base = opened
        if save:
            base = self._court_command(
                command_service, matchday, match, "save", payload, opened
            )["current"]
        return self._court_command(
            command_service, matchday, match, "submit", payload, base
        )

    def _finish_gameday(self, matchday):
        return self.env["federation.matchday.commands"].with_user(
            self.matchday_manager
        ).close_matchday(matchday.id)

    def test_league_runs_from_creation_to_closed_competition(self):
        edition = self._create_competition("full-league", day_count=2)
        division = edition.tournament_ids
        participant_set = self.env["federation.participant.set"].search(
            [("edition_id", "=", edition.id), ("division_id", "=", division.id)]
        )
        self.assertEqual(len(participant_set.line_ids), 4)
        structure = self.env["federation.competition.structure"].search(
            [("edition_id", "=", edition.id)], limit=1
        )
        stage = structure.stage_ids
        self.assertEqual(structure.format_type, "single_round_robin")
        self.assertEqual(len(stage.stage_fixture_ids), 6)

        matchdays = self.env["federation.matchday"].search(
            [("edition_id", "=", edition.id)], order="date,id"
        )
        self.assertEqual(len(matchdays), 2)
        self.assertEqual(set(matchdays.mapped("venue_id").ids), {self.venue.id})
        self.assertTrue(all(day.planning_court_ids == self.courts for day in matchdays))
        schedules = self._plan_schedules(edition)
        self.assertTrue(schedules)
        self._publish_schedules(schedules)
        self.assertEqual(set(matchdays.mapped("current_publication_id.state")), {"live"})
        self.assertEqual(edition.state, "open")
        self.assertEqual(
            self.env["federation.competition.event"].search_count(
                [("edition_id", "=", edition.id), ("event_type", "=", "schedule_published")]
            ),
            2,
        )

        for day_index, matchday in enumerate(matchdays):
            self._prepare_gameday_rosters(matchday)
            self._open_gameday(matchday)
            if day_index == 0:
                self.assertEqual(edition.state, "in_progress")
            for match_index, match in enumerate(matchday.published_match_ids.sorted("id")):
                for team in match.home_team_id | match.away_team_id:
                    start = (match_index * 2) % 12
                    self._cross_out(match, team, (start, start + 1))
                self._court_result(matchday, match)
                self.assertEqual(match.result_state, "approved")
                self.assertTrue(match.include_in_official_standings)
                self.assertEqual(match.state, "done")
                self.assertEqual(
                    set(match.result_audit_ids.mapped("event_type")),
                    {"submitted", "verified", "approved"},
                )
            self._finish_gameday(matchday)
            self.assertEqual(matchday.state, "closed")

        standing = self.env["federation.standing"].search(
            [("structure_stage_id", "=", stage.id)], limit=1
        )
        self.assertTrue(standing)
        self.assertEqual(len(standing.line_ids), 4)
        self.assertEqual(sum(standing.line_ids.mapped("played")), 12)
        self.assertEqual(sum(standing.line_ids.mapped("points")), 18)
        standing.with_user(self.organizer).action_freeze()
        self.assertEqual(standing.state, "frozen")

        division.with_user(self.organizer).write(
            {
                "website_published": True,
                "public_slug": "lifecycle-full-league-division",
            }
        )
        edition.with_user(self.organizer).write(
            {"public_slug": "lifecycle-full-league"}
        )
        edition.with_user(self.organizer).action_publish_website()
        edition.with_user(self.organizer).action_open_planner_operation(
            "close_competition"
        )
        self.assertEqual(edition.state, "closed")
        self.assertEqual(edition.get_public_site_state_label(), "Completed")
        archived = self.env["federation.public.competition.queries"].list_editions(
            archived=True, search=edition.name
        )
        self.assertIn(edition, archived)

    def test_independent_review_is_enforced_in_controlled_mode(self):
        edition = self._create_competition(
            "controlled-review", workflow_mode="controlled", day_count=1
        )
        schedules = self._plan_schedules(edition)
        self.assertEqual(len(schedules), 1)
        schedule = schedules[0]
        action = schedule.with_user(self.schedule_planner).action_submit_for_review()
        review = self.env["federation.schedule.review"].browse(action["res_id"])
        self.assertEqual(review.state, "pending")
        before = (
            review.state,
            review.reviewer_id.id,
            schedule.state,
            schedule.revision,
            len(edition.event_ids),
            schedule.matchday_id.current_publication_id.id,
        )
        with self.assertRaises(ValidationError):
            review.with_user(self.schedule_planner).action_approve_schedule()
        review.invalidate_recordset()
        schedule.invalidate_recordset()
        self.assertEqual(
            (
                review.state,
                review.reviewer_id.id,
                schedule.state,
                schedule.revision,
                len(edition.event_ids),
                schedule.matchday_id.current_publication_id.id,
            ),
            before,
        )

        review.with_user(self.schedule_approver).action_approve_schedule()
        publish_action = review.with_user(self.schedule_approver).action_publish_schedule()
        publish_wizard = self.env[publish_action["res_model"]].with_user(
            self.schedule_approver
        ).browse(publish_action["res_id"])
        publish_wizard.action_publish()
        self.assertEqual(review.state, "approved")
        self.assertEqual(schedule.matchday_id.current_publication_id.state, "live")

        before_publish_attempt = (
            review.state,
            schedule.state,
            schedule.revision,
            schedule.matchday_id.current_publication_id.id,
            len(edition.event_ids),
        )
        with self.assertRaises(ValidationError):
            review.with_user(self.schedule_planner).action_publish_schedule()
        review.invalidate_recordset()
        schedule.invalidate_recordset()
        self.assertEqual(
            (
                review.state,
                schedule.state,
                schedule.revision,
                schedule.matchday_id.current_publication_id.id,
                len(edition.event_ids),
            ),
            before_publish_attempt,
        )

        match = schedule.matchday_id.published_match_ids[:1]
        match.with_user(self.result_submitter).write({"home_score": 2, "away_score": 1})
        match.with_user(self.result_submitter).action_submit_result()
        self.assertEqual(match.result_state, "submitted")
        self.assertFalse(match.include_in_official_standings)
        result_snapshot = (
            match.result_state,
            match.result_verified_by_id.id,
            match.result_approved_by_id.id,
            match.include_in_official_standings,
            sorted(match.result_audit_ids.ids),
        )
        with self.assertRaises(ValidationError):
            match.with_user(self.result_submitter).action_verify_result()
        match.invalidate_recordset()
        self.assertEqual(
            (
                match.result_state,
                match.result_verified_by_id.id,
                match.result_approved_by_id.id,
                match.include_in_official_standings,
                sorted(match.result_audit_ids.ids),
            ),
            result_snapshot,
        )

        match.with_user(self.result_validator).action_verify_result()
        self.assertEqual(match.result_state, "verified")
        result_snapshot = (
            match.result_state,
            match.result_verified_by_id.id,
            match.result_approved_by_id.id,
            match.include_in_official_standings,
            sorted(match.result_audit_ids.ids),
        )
        with self.assertRaises(ValidationError):
            match.with_user(self.result_submitter).action_approve_result()
        match.invalidate_recordset()
        self.assertEqual(
            (
                match.result_state,
                match.result_verified_by_id.id,
                match.result_approved_by_id.id,
                match.include_in_official_standings,
                sorted(match.result_audit_ids.ids),
            ),
            result_snapshot,
        )
        match.with_user(self.result_approver).action_approve_result()
        self.assertEqual(match.result_state, "approved")
        self.assertTrue(match.include_in_official_standings)
        self.assertEqual(match.result_submitted_by_id, self.result_submitter)
        self.assertEqual(match.result_verified_by_id, self.result_validator)
        self.assertEqual(match.result_approved_by_id, self.result_approver)
        self.assertEqual(match.state, "done")

    def test_tournament_day_runs_groups_then_knockout_from_one_publication(self):
        edition = self._create_competition(
            "tournament-day",
            setup_template="tournament_day",
            format_type="pool_knockout",
            team_count=4,
            day_count=1,
        )
        format_wizard_action = edition.with_user(self.organizer).action_setup_format()
        format_wizard = self.env[format_wizard_action["res_model"]].browse(
            format_wizard_action["res_id"]
        )
        choices = dict(format_wizard._fields["format_type"].selection)
        self.assertIn(
            "pool_knockout",
            choices,
            "BLOCKER: Choose Format does not expose a groups-then-knockout structure.",
        )
        structure = self.env["federation.competition.structure"].search(
            [("edition_id", "=", edition.id)], limit=1
        )
        pool_stages = structure.stage_ids.filtered(lambda stage: stage.stage_type == "pool")
        knockout = structure.stage_ids.filtered(
            lambda stage: stage.stage_type == "knockout"
        )
        self.assertEqual(len(pool_stages), 2)
        self.assertEqual(len(knockout), 1)
        self.assertEqual(set(pool_stages.mapped("stage_participant_ids.team_id").ids), set(self.teams.ids))
        self.assertTrue(
            all(len(stage.stage_participant_ids) == 2 for stage in pool_stages)
        )
        self.assertEqual(len(knockout.stage_fixture_ids), 3)
        self.assertTrue(
            all(
                not fixture.operational_match_id
                and (fixture.home_source_seed or fixture.away_source_seed)
                for fixture in knockout.stage_fixture_ids.filtered(
                    lambda item: item.round_number == 1
                )
            )
        )

        schedules = self._plan_schedules(edition)
        self.assertEqual(len(schedules), 1)
        schedule = schedules[0]
        self.assertEqual(set(schedule.assignment_ids.fixture_id.ids), set(structure.fixture_ids.ids))
        self._publish_schedules(schedules)
        matchday = schedule.matchday_id
        publication = matchday.current_publication_id
        self.assertEqual(publication.state, "live")
        publication_id = publication.id
        publication_digest = publication.snapshot_digest
        assignment_fixture_ids = set(schedule.assignment_ids.fixture_id.ids)
        self.assertEqual(len(assignment_fixture_ids), 5)

        self._prepare_gameday_rosters(matchday)
        self._open_gameday(matchday)
        group_matches = matchday.published_match_ids.sorted("id")
        self.assertEqual(len(group_matches), 2)
        for match in group_matches:
            for team in match.home_team_id | match.away_team_id:
                self._cross_out(match, team)
            self._court_result(matchday, match, home=2, away=1)
            self.assertEqual(match.result_state, "approved")

        for stage in pool_stages.sorted("sequence"):
            stage.with_user(self.organizer).action_freeze_standings()
        self.assertEqual(len(knockout.stage_participant_ids), 4)
        semifinal_fixtures = knockout.stage_fixture_ids.filtered(
            lambda fixture: fixture.round_number == 1
        ).sorted("sequence")
        self.assertEqual(len(semifinal_fixtures), 2)
        self.assertTrue(all(fixture.operational_match_id for fixture in semifinal_fixtures))
        tie_match = semifinal_fixtures[0].operational_match_id
        tie_advancing_team = tie_match.home_team_id
        self.assertTrue(tie_match.is_format_knockout)
        self.assertTrue(
            all(
                set(match.match_sheet_ids.mapped("state")) == {"approved"}
                for match in semifinal_fixtures.mapped("operational_match_id")
            ),
            "New knockout matches should inherit each team's approved gameday roster.",
        )

        for fixture in semifinal_fixtures:
            match = fixture.operational_match_id
            for team in match.home_team_id | match.away_team_id:
                self._cross_out(match, team)
            if match == tie_match:
                match.with_user(self.organizer).write(
                    {
                        "resolution_type": "tiebreak",
                        "advancing_team_id": tie_advancing_team.id,
                    }
                )
                self._court_result(matchday, match, home=1, away=1)
            else:
                self._court_result(matchday, match, home=2, away=1)
            self.assertEqual(match.result_state, "approved")

        final_fixture = knockout.stage_fixture_ids.filtered(
            lambda fixture: fixture.round_number == 2
        )
        self.assertEqual(len(final_fixture), 1)
        final_fixture = final_fixture[0]
        final_match = final_fixture.operational_match_id
        self.assertTrue(final_match)
        self.assertIn(tie_advancing_team, final_match.home_team_id | final_match.away_team_id)
        self.assertEqual(final_fixture.placement_from, 1)
        self.assertEqual(final_fixture.placement_to, 2)
        for team in final_match.home_team_id | final_match.away_team_id:
            self._cross_out(final_match, team)
        self._court_result(matchday, final_match, home=2, away=1)
        self.assertEqual(final_match.result_state, "approved")
        self.assertEqual(final_fixture.state, "completed")
        final_placement = final_match._get_result_team("winner")
        self.assertIn(final_placement, final_match.home_team_id | final_match.away_team_id)

        self.assertEqual(matchday.current_publication_id.id, publication_id)
        self.assertEqual(matchday.current_publication_id.snapshot_digest, publication_digest)
        self.assertEqual(set(schedule.assignment_ids.fixture_id.ids), assignment_fixture_ids)
        self.assertEqual(
            self.env["federation.schedule.publication"].search_count(
                [("schedule_id", "=", schedule.id), ("state", "=", "live")]
            ),
            1,
        )
        self._finish_gameday(matchday)
        self.assertEqual(matchday.state, "closed")

    def test_correcting_a_progressed_result_rolls_back_the_next_round(self):
        edition = self._create_competition(
            "knockout-correction", format_type="knockout", day_count=1
        )
        schedules = self._plan_schedules(edition)
        self.assertEqual(len(schedules), 1)
        self._publish_schedules(schedules)
        matchday = schedules[0].matchday_id
        self._prepare_gameday_rosters(matchday)
        self._open_gameday(matchday)
        first_round = schedules[0].structure_id.fixture_ids.filtered(
            lambda fixture: fixture.round_number == 1 and fixture.operational_match_id
        ).sorted("sequence")
        self.assertEqual(len(first_round), 2)
        for fixture in first_round:
            match = fixture.operational_match_id
            for team in match.home_team_id | match.away_team_id:
                self._cross_out(match, team)
            self._court_result(matchday, match, home=2, away=0)
            self.assertEqual(match.result_state, "approved")

        final_fixture = schedules[0].structure_id.fixture_ids.filtered(
            lambda fixture: fixture.round_number == 2
        )
        self.assertEqual(len(final_fixture), 1)
        final_fixture = final_fixture[0]
        original_follow_up = final_fixture.operational_match_id
        self.assertTrue(original_follow_up)
        source_match = first_round[0].operational_match_id
        original_winner = source_match.home_team_id
        corrected_winner = source_match.away_team_id
        source_match.with_user(self.organizer).write(
            {"result_correction_reason": "Video review reversed the semifinal result."}
        )
        source_match.with_user(self.organizer).action_correct_result()
        self.assertEqual(source_match.result_state, "corrected")
        self.assertFalse(final_fixture.operational_match_id)
        self.assertFalse(final_fixture.home_team_id == original_winner or final_fixture.away_team_id == original_winner)
        withdrawal = edition.event_ids.filtered(
            lambda event: event.event_type == "follow_up_match_withdrawn"
        )
        self.assertEqual(len(withdrawal), 1)
        self.assertEqual(json.loads(withdrawal.payload_json)["match_id"], original_follow_up.id)
        self.assertEqual(json.loads(withdrawal.payload_json)["source_fixture_id"], first_round[0].id)

        source_match.with_user(self.organizer).write(
            {"home_score": 0, "away_score": 2, "result_correction_reason": "Corrected semifinal score."}
        )
        source_match.with_user(self.organizer).action_submit_result()
        self.assertEqual(source_match.result_state, "approved")
        self.assertTrue(source_match.include_in_official_standings)
        self.assertTrue(final_fixture.operational_match_id)
        self.assertIn(
            corrected_winner,
            final_fixture.home_team_id | final_fixture.away_team_id,
        )
        self.assertNotIn(
            original_winner,
            final_fixture.home_team_id | final_fixture.away_team_id,
        )

        follow_up = final_fixture.operational_match_id
        for team in follow_up.home_team_id | follow_up.away_team_id:
            self._cross_out(follow_up, team)
        follow_up.with_user(self.organizer).action_start()
        self.assertEqual(follow_up.state, "in_progress")
        source_match.with_user(self.organizer).write(
            {"result_correction_reason": "A correction after follow-up start must be refused."}
        )
        unchanged = (
            source_match.result_state,
            source_match.state,
            source_match.include_in_official_standings,
            source_match.result_audit_ids.ids,
            final_fixture.operational_match_id.id,
            final_fixture.home_team_id.id,
            final_fixture.away_team_id.id,
            follow_up.state,
        )
        with self.assertRaises(ValidationError):
            source_match.with_user(self.organizer).action_correct_result()
        source_match.invalidate_recordset()
        final_fixture.invalidate_recordset()
        follow_up.invalidate_recordset()
        self.assertEqual(
            (
                source_match.result_state,
                source_match.state,
                source_match.include_in_official_standings,
                source_match.result_audit_ids.ids,
                final_fixture.operational_match_id.id,
                final_fixture.home_team_id.id,
                final_fixture.away_team_id.id,
                follow_up.state,
            ),
            unchanged,
        )

    def test_competition_cannot_close_while_work_is_unfinished(self):
        edition = self._create_competition(
            "close-blockers", workflow_mode="controlled", team_count=2, day_count=1
        )
        schedules = self._plan_schedules(edition)
        self._publish_schedules(schedules)
        matchday = schedules[0].matchday_id
        match = matchday.published_match_ids[:1]
        self._prepare_gameday_rosters(matchday)
        self._open_gameday(matchday)
        for team in match.home_team_id | match.away_team_id:
            self._cross_out(match, team)
        self._court_result(matchday, match, home=2, away=1)
        self.assertEqual(match.result_state, "submitted")

        blockers = edition.with_user(self.organizer)._get_close_blockers()
        joined_blockers = "\n".join(blockers).lower()
        self.assertIn("not finished", joined_blockers)
        self.assertIn("need approval", joined_blockers)
        self.assertIn("close or cancel", joined_blockers)
        self.assertIn("freeze", joined_blockers)
        standing = self.env["federation.standing"].search(
            [("tournament_id", "=", edition.tournament_ids.id)], limit=1
        )
        self.assertTrue(standing)
        before = (
            edition.state,
            match.state,
            match.result_state,
            match.result_audit_ids.ids,
            matchday.state,
            standing.state,
            len(edition.event_ids),
        )
        with self.assertRaises(ValidationError):
            edition.with_user(self.organizer).action_close()
        edition.invalidate_recordset()
        match.invalidate_recordset()
        matchday.invalidate_recordset()
        standing.invalidate_recordset()
        self.assertEqual(
            (
                edition.state,
                match.state,
                match.result_state,
                match.result_audit_ids.ids,
                matchday.state,
                standing.state,
                len(edition.event_ids),
            ),
            before,
        )
        with self.assertRaises(ValidationError):
            edition.with_user(self.organizer).action_draft()
        edition.invalidate_recordset()
        self.assertEqual(edition.state, before[0])

        match.with_user(self.result_validator).action_verify_result()
        match.with_user(self.result_approver).action_approve_result()
        self.assertEqual(match.state, "done")
        self._finish_gameday(matchday)
        self.assertEqual(matchday.state, "closed")
        standing.with_user(self.organizer).action_freeze()
        self.assertEqual(standing.state, "frozen")
        edition.with_user(self.organizer).action_open_planner_operation(
            "close_competition"
        )
        self.assertEqual(edition.state, "closed")
        self.assertFalse(edition._get_close_blockers())

    def test_forfeit_and_bye_points_follow_the_rule_set(self):
        edition = self._create_competition(
            "forfeit-bye", format_type="knockout", team_count=3, day_count=1
        )
        schedules = self._plan_schedules(edition)
        self.assertEqual(len(schedules), 1)
        self._publish_schedules(schedules)
        structure = schedules[0].structure_id
        stage = structure.stage_ids
        bye_fixture = stage.stage_fixture_ids.filtered("bye_team_id")
        self.assertEqual(len(bye_fixture), 1)
        self.assertEqual(bye_fixture.bye_team_id, self.teams[0])
        self.assertEqual(len(stage.stage_fixture_ids), 3)
        matchday = schedules[0].matchday_id
        self._open_gameday(matchday)
        forfeit_fixture = stage.stage_fixture_ids.filtered(
            lambda fixture: fixture.round_number == 1 and fixture.operational_match_id
        )
        self.assertEqual(len(forfeit_fixture), 1)
        forfeit_match = forfeit_fixture.operational_match_id
        result = self._court_result(
            matchday,
            forfeit_match,
            home=0,
            away=50,
            outcome="forfeit_home",
            reason="The home team did not field an eligible squad.",
        )
        self.assertTrue(result["current"]["submitted"])
        self.assertEqual(forfeit_match.result_state, "approved")
        self.assertEqual(forfeit_match._get_forfeit_winner(), forfeit_match.away_team_id)
        final_fixture = stage.stage_fixture_ids.filtered(
            lambda fixture: fixture.round_number == 2
        )
        self.assertEqual(len(final_fixture), 1)
        self.assertTrue(final_fixture.operational_match_id)
        final_match = final_fixture.operational_match_id
        if final_match.home_team_id == forfeit_match.away_team_id:
            final_home_score, final_away_score = 1, 0
        else:
            final_home_score, final_away_score = 0, 1
        self._court_result(
            matchday, final_match, home=final_home_score, away=final_away_score
        )
        stage.with_user(self.organizer).action_freeze_standings()
        points = {
            line.team_id.id: line.points
            for line in stage.standing_snapshot_id.line_ids
        }
        self.assertEqual(len(points), 3)
        bye_team_id = bye_fixture.bye_team_id.id
        forfeiting_team_id = forfeit_match.home_team_id.id
        advancing_forfeit_team_id = forfeit_match.away_team_id.id
        self.assertEqual(points[bye_team_id], 4)
        self.assertEqual(points[forfeiting_team_id], 1)
        self.assertEqual(points[advancing_forfeit_team_id], 10)
        self.assertEqual(sum(stage.standing_snapshot_id.line_ids.mapped("played")), 4)

    def test_suspension_dates_and_match_count_control_eligibility(self):
        edition = self._create_competition(
            "suspension-eligibility", team_count=4, day_count=1
        )
        schedules = self._plan_schedules(edition)
        self._publish_schedules(schedules)
        matchday = schedules[0].matchday_id
        matches = matchday.published_match_ids.sorted("id")
        self._prepare_gameday_rosters(matchday)
        self._open_gameday(matchday)
        first_match = matches[0]
        second_match = matches.filtered(lambda item: item != first_match)[:1]
        self.assertTrue(second_match)

        future_player = self.players_by_team[first_match.home_team_id.id][4]
        future_case = self.env["federation.disciplinary.case"].create(
            {
                "name": "Future lifecycle suspension",
                "subject_player_id": future_player.id,
                "summary": "Verify a future suspension starts only on its effective date.",
            }
        )
        future_suspension = self.env["federation.suspension"].create(
            {
                "name": "Future dated lifecycle suspension",
                "case_id": future_case.id,
                "player_id": future_player.id,
                "date_start": "2027-03-15",
                "date_end": "2027-04-15",
            }
        )
        with patch(
            "odoo.fields.Date.context_today",
            return_value=fields.Date.to_date("2027-03-14"),
        ):
            future_suspension.with_user(self.discipline_officer).action_activate()
        self.assertEqual(future_suspension.state, "scheduled")
        self.assertEqual(future_player.state, "active")

        count_player = self.players_by_team[first_match.home_team_id.id][5]
        count_case = self.env["federation.disciplinary.case"].create(
            {
                "name": "Match-count lifecycle suspension",
                "subject_player_id": count_player.id,
                "summary": "Expire after one completed team match.",
            }
        )
        count_suspension = self.env["federation.suspension"].create(
            {
                "name": "One match lifecycle suspension",
                "case_id": count_case.id,
                "player_id": count_player.id,
                "date_start": "2027-01-01",
                "match_count": 1,
            }
        )
        with patch(
            "odoo.fields.Date.context_today",
            return_value=fields.Date.to_date("2027-03-01"),
        ):
            count_suspension.with_user(self.discipline_officer).action_activate()
        self.assertEqual(count_suspension.state, "active")
        for team in first_match.home_team_id | first_match.away_team_id:
            sheet = self.env["federation.match.sheet"].search(
                [("match_id", "=", first_match.id), ("team_id", "=", team.id)],
                limit=1,
            )
            required_player = count_player if team == first_match.home_team_id else sheet.line_ids[0].player_id
            ids = [required_player.id]
            ids.extend(
                line.player_id.id
                for line in sheet.line_ids
                if line.player_id.id not in ids
            )
            sheet.with_user(self.organizer).action_set_crossed_out(ids[:2])
        self._court_result(matchday, first_match)
        self.assertEqual(first_match.state, "done")
        self.assertEqual(count_suspension.state, "expired")
        self.assertEqual(count_suspension.matches_served, 1)
        self.assertEqual(count_player.state, "active")

        with patch(
            "odoo.fields.Date.context_today",
            return_value=fields.Date.to_date("2027-03-15"),
        ):
            self.env["federation.suspension"].with_user(
                self.discipline_officer
            )._cron_update_suspensions()
        self.assertEqual(future_suspension.state, "active")
        self.assertEqual(future_player.state, "suspended")

        started_player = self.players_by_team[second_match.home_team_id.id][6]
        self.assertTrue(
            self.env["federation.match.sheet"].search(
                [
                    ("match_id", "=", second_match.id),
                    ("team_id", "=", second_match.home_team_id.id),
                    ("line_ids.player_id", "=", started_player.id),
                    ("state", "=", "approved"),
                ],
                limit=1,
            )
        )
        self._cross_out(second_match, second_match.home_team_id, (0, 1))
        self._cross_out(second_match, second_match.away_team_id, (0, 1))
        started_case = self.env["federation.disciplinary.case"].create(
            {
                "name": "Post-roster lifecycle suspension",
            }
        )
        started_suspension = self.env["federation.suspension"].create(
            {
                "name": "Post-roster match suspension",
                "case_id": started_case.id,
                "player_id": started_player.id,
                "date_start": "2027-01-01",
                "date_end": "2027-12-31",
            }
        )
        with patch(
            "odoo.fields.Date.context_today",
            return_value=fields.Date.to_date("2027-03-01"),
        ):
            started_suspension.with_user(self.discipline_officer).action_activate()
        self.assertEqual(started_player.state, "suspended")
        previous_state = second_match.state
        with self.assertRaises(ValidationError) as error:
            second_match.with_user(self.organizer).action_start()
        self.assertIn(started_player.display_name, str(error.exception))
        second_match.invalidate_recordset()
        self.assertEqual(second_match.state, previous_state)

    def test_gameday_roster_limits_hold_through_result_submission(self):
        edition = self._create_competition(
            "fourteen-twelve", team_count=4, day_count=1
        )
        schedules = self._plan_schedules(edition)
        self._publish_schedules(schedules)
        matchday = schedules[0].matchday_id
        matches = matchday.published_match_ids.sorted("id")
        self.assertEqual(len(matches), 6)
        self._prepare_gameday_rosters(matchday)
        self._open_gameday(matchday)
        first_match = matches[0]
        home_sheet = self.env["federation.match.sheet"].search(
            [("match_id", "=", first_match.id), ("team_id", "=", first_match.home_team_id.id)],
            limit=1,
        )
        self.assertEqual(len(home_sheet.line_ids), 14)
        self.assertEqual(home_sheet.match_participant_limit, 12)
        command_service = self.env["federation.court.commands"].with_user(
            self.court_operator
        )
        slot = first_match.operational_slot_id or first_match.published_slot_id
        opened = command_service.open_match(matchday.id, slot.court_id.id, first_match.id)
        payload = {
            "home": 2,
            "away": 1,
            "periods": [],
            "outcome": "normal",
            "reason": "",
            "zero_confirmed": False,
        }
        saved = self._court_command(
            command_service, matchday, first_match, "save", payload, opened
        )["current"]
        before = (
            first_match.state,
            first_match.result_state,
            first_match.home_score,
            first_match.away_score,
            first_match.result_audit_ids.ids,
        )
        capture = self.env["federation.court.capture"].search(
            [("match_id", "=", first_match.id)], limit=1
        )
        with self.assertRaisesRegex(ValidationError, "at most 12"):
            self._court_command(
                command_service, matchday, first_match, "submit", payload, saved
            )
        first_match.invalidate_recordset()
        capture.invalidate_recordset()
        self.assertEqual(
            (
                first_match.state,
                first_match.result_state,
                first_match.home_score,
                first_match.away_score,
                first_match.result_audit_ids.ids,
            ),
            before,
        )
        self.assertEqual(capture.revision, 1)
        self.assertFalse(capture.submitted)

        first_home_sheet = self._cross_out(first_match, first_match.home_team_id)
        first_away_sheet = self._cross_out(first_match, first_match.away_team_id)
        repeated_team = first_match.home_team_id
        next_match = matches.filtered(
            lambda item: item != first_match
            and repeated_team in (item.home_team_id | item.away_team_id)
        )[:1]
        self.assertTrue(next_match)
        next_sheet = self.env["federation.match.sheet"].search(
            [("match_id", "=", next_match.id), ("team_id", "=", repeated_team.id)],
            limit=1,
        )
        self.assertEqual(len(next_sheet.line_ids), 14)
        self._cross_out(next_match, repeated_team, (2, 3))
        self.assertNotEqual(
            set(first_home_sheet.line_ids.filtered("crossed_out").mapped("player_id").ids),
            set(next_sheet.line_ids.filtered("crossed_out").mapped("player_id").ids),
        )
        self.assertEqual(first_home_sheet.participant_count, 12)
        self.assertEqual(first_away_sheet.participant_count, 12)
        self.assertEqual(next_sheet.participant_count, 12)
        self._court_result(matchday, first_match, save=False)
        self.assertEqual(first_match.result_state, "approved")
        self.assertEqual(first_match.state, "done")