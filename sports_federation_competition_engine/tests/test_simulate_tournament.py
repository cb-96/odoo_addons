import random

from odoo.tests.common import TransactionCase


class TestSimulateTournament(TransactionCase):
    """End-to-end simulation: portal team creation -> RR -> Knockout."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Re-usable refs
        cls.portal_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )

        # Create 10 clubs and portal users; first two clubs will create 2 teams each
        cls.clubs = []
        cls.users = []
        cls.teams = []

        for i in range(10):
            club = cls.env["federation.club"].create(
                {
                    "name": f"Sim Club {i+1}",
                    "code": f"SC{i+1:02d}",
                }
            )
            cls.clubs.append(club)

            user = (
                cls.env["res.users"]
                .with_context(no_reset_password=True)
                .create(
                    {
                        "name": f"Portal User {i+1}",
                        "login": f"portal.user.{i+1}@example.com",
                        "email": f"portal.user.{i+1}@example.com",
                        "group_ids": [(6, 0, [cls.portal_group.id])],
                    }
                )
            )
            cls.users.append(user)

            # Create a representative linking the portal user to the club
            cls.env["federation.club.representative"].create(
                {
                    "club_id": club.id,
                    "partner_id": user.partner_id.id,
                    "user_id": user.id,
                    "role_type_id": cls.role_type.id,
                }
            )

        # Create teams through the portal helper: 2 teams for first two clubs, 1 for others
        for idx, club in enumerate(cls.clubs):
            user = cls.users[idx]
            num_teams = 2 if idx < 2 else 1
            for tnum in range(num_teams):
                team = cls.env["federation.team"]._portal_create_team(
                    club,
                    values={
                        "name": f"{club.name} Team {tnum+1}",
                        "category": "senior",
                        "gender": "male",
                        "email": f"team.{idx+1}.{tnum+1}@example.com",
                    },
                    user=user,
                )
                cls.teams.append(team)

    def test_full_tournament_simulation(self):
        random.seed(0)

        # Create a season and tournament
        season = self.env["federation.season"].create(
            {
                "name": "Sim Season",
                "code": "SIM2026",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )

        tournament = self.env["federation.tournament"].create(
            {
                "name": "Simulation Cup",
                "code": "SIMCUP",
                "season_id": season.id,
                "date_start": "2026-04-01",
                "category": "senior",
                "gender": "male",
            }
        )

        # Open tournament for portal registrations
        tournament.action_open()

        # Create stages: Round Robin (group) then Knockout
        stage_rr = self.env["federation.tournament.stage"].create(
            {
                "name": "Round Robin",
                "tournament_id": tournament.id,
                "sequence": 1,
                "stage_type": "group",
            }
        )
        stage_ko = self.env["federation.tournament.stage"].create(
            {
                "name": "Knockout",
                "tournament_id": tournament.id,
                "sequence": 2,
                "stage_type": "knockout",
            }
        )

        # Single group containing all teams
        group = self.env["federation.tournament.group"].create(
            {
                "name": "All Teams",
                "stage_id": stage_rr.id,
                "sequence": 1,
                "max_participants": len(self.teams),
            }
        )

        # Submit portal registrations for each team (using the club's portal user)
        Registration = self.env["federation.tournament.registration"]
        created_regs = []
        for team in self.teams:
            # find a user representing this team.club
            user = None
            for u in self.users:
                reps = self.env["federation.club.representative"].search(
                    [("user_id", "=", u.id), ("club_id", "=", team.club_id.id)]
                )
                if reps:
                    user = u
                    break
            if not user:
                user = self.users[0]

            reg = Registration._portal_submit_registration_request(
                tournament, team, notes="Sim registration", user=user
            )
            # Confirm as federation staff (create participant)
            reg.action_confirm()
            participant = reg.participant_id
            # Assign participant to the RR stage and the group
            participant.write({"stage_id": stage_rr.id, "group_id": group.id})
            created_regs.append(reg)

        participants = self.env["federation.tournament.participant"].search(
            [("tournament_id", "=", tournament.id), ("stage_id", "=", stage_rr.id)]
        )
        self.assertEqual(len(participants), len(self.teams))

        # Pre-create gamedays for the round-robin stage (enough for any team count)
        for i in range(1, 21):
            self.env["federation.tournament.round"].create(
                {
                    "stage_id": stage_rr.id,
                    "group_id": group.id,
                    "sequence": i,
                    "name": f"Gameday {i}",
                }
            )

        # Generate round-robin schedule across 4 gamedays by using 8h round intervals
        rr_service = self.env["federation.round.robin.service"]
        rr_options = {
            "double_round": False,
            "schedule_by_round": True,
            "round_interval_hours": 8,
            "start_datetime": "2026-04-01 10:00:00",
            "interval_hours": 0,
            "group": group,
            "overwrite": True,
        }

        rr_matches = rr_service.generate(tournament, stage_rr, participants, rr_options)
        self.assertTrue(rr_matches)

        # Simulate results for round-robin matches (no draws: deterministic scores)
        for idx, match in enumerate(rr_matches):
            match.action_schedule()
            home_score = (idx % 5) + 1
            away_score = (idx + 2) % 5
            if home_score == away_score:
                away_score = (away_score + 1) % 6
            match.write({"home_score": home_score, "away_score": away_score})
            match.action_done()

        # Compute standings for the group
        standing = self.env["federation.standing"].create(
            {
                "name": "RR Standing",
                "tournament_id": tournament.id,
                "stage_id": stage_rr.id,
                "group_id": group.id,
            }
        )
        standing.action_recompute()
        self.assertEqual(standing.state, "computed")

        # Create progression rule: advance top 8 teams to knockout and execute
        prog = self.env["federation.stage.progression"].create(
            {
                "tournament_id": tournament.id,
                "source_stage_id": stage_rr.id,
                "source_group_id": group.id,
                "target_stage_id": stage_ko.id,
                "rank_from": 1,
                "rank_to": 8,
                "seeding_method": "keep_rank",
                "auto_advance": False,
            }
        )
        # Execute progression to create confirmed participants in the knockout stage
        prog.action_execute()

        ko_participants = self.env["federation.tournament.participant"].search(
            [("tournament_id", "=", tournament.id), ("stage_id", "=", stage_ko.id)]
        )
        self.assertTrue(len(ko_participants) >= 2)

        # Generate knockout bracket from qualified participants
        ko_service = self.env["federation.knockout.service"]
        ko_options = {
            "start_datetime": "2026-04-06 10:00:00",
            "interval_hours": 1,
            "bracket_size": "power_of_two",
            "seeding": "seed",
            "overwrite": True,
        }
        ko_matches = ko_service.generate(
            tournament, stage_ko, ko_participants, ko_options
        )
        self.assertTrue(ko_matches)

        # Simulate knockout: iterate by round and finish matches when both teams present
        all_ko_matches = self.env["federation.match"].search(
            [("stage_id", "=", stage_ko.id)],
            order="round_number asc, bracket_position asc",
        )
        max_round = max(m.round_number for m in all_ko_matches)
        for rnd in range(1, max_round + 1):
            round_matches = all_ko_matches.filtered(lambda m: m.round_number == rnd)
            for idx, m in enumerate(round_matches):
                # Some placeholder matches will be filled after earlier rounds
                if not m.home_team_id or not m.away_team_id:
                    continue
                # deterministic winner assignment
                h = (rnd + idx) % 3 + 1
                a = idx % 2
                if h == a:
                    a = 0
                m.write({"home_score": h, "away_score": a})
                m.action_done()

        # Final match should have been played
        final_matches = all_ko_matches.filtered(lambda m: m.round_number == max_round)
        self.assertTrue(final_matches)
        final = final_matches[0]
        self.assertEqual(final.state, "done")
        winner = (
            final.home_team_id
            if final.home_score > final.away_score
            else final.away_team_id
        )
        self.assertTrue(winner)
