"""
Tests for federation.eligibility.service (Phase 3).

Coverage:
- age_min rule: under-age player rejected, old-enough player passes
- age_max rule: over-age player rejected
- gender rule: wrong gender rejected, correct gender passes
- suspension rule: suspended player rejected
- no birth_date → age rules return ineligible with reason
- placeholder rule is skipped
- player passing all rules returns eligible=True with empty reasons
- check_roster_eligibility returns per-player results
- check_match_eligibility uses match → tournament chain rule set
"""

from datetime import date
from unittest import SkipTest
from odoo.tests.common import TransactionCase


class TestEligibilityService(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        if "federation.tournament" not in cls.env:
            raise SkipTest("federation.tournament not available (installed later)")
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Elig Test Club",
                "code": "ETC",
            }
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Elig Team",
                "club_id": cls.club.id,
                "code": "ET",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Elig Season",
                "code": "ES24",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Elig Tournament",
                "code": "ETOUR",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
            }
        )
        # Rule set with several eligibility rules
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Eligibility Test Rules",
                "code": "ETRULES",
            }
        )
        cls.service = cls.env["federation.eligibility.service"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_player(self, gender="male", state="active", birth_date=None):
        """Exercise make player."""
        name_suffix = birth_date or "noBD"
        player = self.env["federation.player"].create(
            {
                "first_name": f"Player {name_suffix}",
                "last_name": "Test",
                "gender": gender,
                "state": state,
                "birth_date": birth_date,
            }
        )
        return player

    def _make_rule(
        self, etype, age_limit=None, allowed_categories=None, placeholder=False
    ):
        """Exercise make rule."""
        vals = {
            "rule_set_id": self.rule_set.id,
            "name": f"Rule {etype}",
            "eligibility_type": etype,
            "is_placeholder": placeholder,
        }
        if age_limit is not None:
            vals["age_limit"] = age_limit
        if allowed_categories is not None:
            vals["allowed_categories"] = allowed_categories
        return self.env["federation.eligibility.rule"].create(vals)

    # ------------------------------------------------------------------
    # age_min tests
    # ------------------------------------------------------------------

    def test_age_min_pass(self):
        """Player old enough passes age_min rule."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Age Min RS",
                "code": "AMRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Min 16",
                "eligibility_type": "age_min",
                "age_limit": 16,
            }
        )
        # 20-year-old player
        bd = date.today().replace(year=date.today().year - 20)
        player = self._make_player(birth_date=bd.isoformat())
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertTrue(result["eligible"])
        self.assertEqual(result["reasons"], [])

    def test_age_min_fail(self):
        """Player too young is rejected with reason."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Age Min Fail RS",
                "code": "AMFRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Min 18",
                "eligibility_type": "age_min",
                "age_limit": 18,
            }
        )
        # 15-year-old player
        bd = date.today().replace(year=date.today().year - 15)
        player = self._make_player(birth_date=bd.isoformat())
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertFalse(result["eligible"])
        self.assertTrue(result["reasons"])

    def test_age_min_no_birthdate_fails(self):
        """Player with no birth date fails age_min rule."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Age Min No BD",
                "code": "AMNBD",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Min 16",
                "eligibility_type": "age_min",
                "age_limit": 16,
            }
        )
        player = self._make_player(birth_date=None)
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertFalse(result["eligible"])
        self.assertTrue(result["reasons"])

    # ------------------------------------------------------------------
    # age_max tests
    # ------------------------------------------------------------------

    def test_age_max_pass(self):
        """Player younger than max passes."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Age Max RS",
                "code": "AMXRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Max 20",
                "eligibility_type": "age_max",
                "age_limit": 20,
            }
        )
        bd = date.today().replace(year=date.today().year - 18)
        player = self._make_player(birth_date=bd.isoformat())
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertTrue(result["eligible"])

    def test_age_max_fail(self):
        """Player older than max is rejected."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Age Max Fail RS",
                "code": "AMXFRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Max U19",
                "eligibility_type": "age_max",
                "age_limit": 19,
            }
        )
        bd = date.today().replace(year=date.today().year - 25)
        player = self._make_player(birth_date=bd.isoformat())
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertFalse(result["eligible"])
        self.assertTrue(result["reasons"])

    # ------------------------------------------------------------------
    # gender tests
    # ------------------------------------------------------------------

    def test_gender_pass(self):
        """Player with matching gender passes."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Gender RS",
                "code": "GRRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Male Only",
                "eligibility_type": "gender",
                "allowed_categories": "male",
            }
        )
        player = self._make_player(gender="male")
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertTrue(result["eligible"])

    def test_gender_fail(self):
        """Player with wrong gender is rejected."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Gender Fail RS",
                "code": "GFRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Female Only",
                "eligibility_type": "gender",
                "allowed_categories": "female",
            }
        )
        player = self._make_player(gender="male")
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertFalse(result["eligible"])
        self.assertTrue(result["reasons"])

    # ------------------------------------------------------------------
    # suspension tests
    # ------------------------------------------------------------------

    def test_suspension_rejects_suspended_player(self):
        """Suspended player fails suspension rule."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Suspension RS",
                "code": "SUSRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "No Suspended Players",
                "eligibility_type": "suspension",
            }
        )
        player = self._make_player(state="suspended")
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertFalse(result["eligible"])
        self.assertTrue(result["reasons"])

    def test_suspension_allows_active_player(self):
        """Active player passes suspension rule."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Suspension Pass RS",
                "code": "SUSPRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "No Suspended Players",
                "eligibility_type": "suspension",
            }
        )
        player = self._make_player(state="active")
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertTrue(result["eligible"])

    def test_suspension_rejects_player_with_active_suspension_window(self):
        """Date-bounded active suspensions must block eligibility checks."""
        Suspension = self.env.get("federation.suspension")
        Case = self.env.get("federation.disciplinary.case")
        if not Suspension or not Case:
            self.skipTest("Discipline module not installed.")

        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Suspension Window RS",
                "code": "SUSWRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "No Active Suspensions",
                "eligibility_type": "suspension",
            }
        )
        player = self._make_player(state="active")
        case = Case.create(
            {
                "name": "Eligibility Suspension Case",
                "subject_player_id": player.id,
                "summary": "Suspension should block eligibility during its active window.",
            }
        )
        suspension = Suspension.create(
            {
                "name": "Windowed Suspension",
                "case_id": case.id,
                "player_id": player.id,
                "date_start": "2024-06-10",
                "date_end": "2024-06-20",
            }
        )
        suspension.action_activate()

        result = self.service.check_player_eligibility(
            player,
            rule_set,
            context={"match_date": date(2024, 6, 15)},
        )

        self.assertFalse(result["eligible"])
        self.assertIn("2024-06-10", result["reasons"][0])

    def test_suspension_ignores_out_of_window_active_suspension(self):
        """Past or future suspension windows should not block the current date."""
        Suspension = self.env.get("federation.suspension")
        Case = self.env.get("federation.disciplinary.case")
        if not Suspension or not Case:
            self.skipTest("Discipline module not installed.")

        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Suspension Window Pass RS",
                "code": "SUSWPRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "No Active Suspensions",
                "eligibility_type": "suspension",
            }
        )
        player = self._make_player(state="active")
        case = Case.create(
            {
                "name": "Old Suspension Case",
                "subject_player_id": player.id,
                "summary": "Old suspension should not block later eligibility checks.",
            }
        )
        suspension = Suspension.create(
            {
                "name": "Expired Window",
                "case_id": case.id,
                "player_id": player.id,
                "date_start": "2024-05-01",
                "date_end": "2024-05-05",
            }
        )
        suspension.action_activate()

        result = self.service.check_player_eligibility(
            player,
            rule_set,
            context={"match_date": date(2024, 6, 15)},
        )

        self.assertTrue(result["eligible"])

    # ------------------------------------------------------------------
    # placeholder skipped
    # ------------------------------------------------------------------

    def test_placeholder_rule_is_skipped(self):
        """Placeholder rules are not evaluated and do not affect outcome."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Placeholder RS",
                "code": "PHRS",
            }
        )
        # Placeholder rule that would fail (wrong gender) but is a placeholder
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Placeholder Female Only",
                "eligibility_type": "gender",
                "allowed_categories": "female",
                "is_placeholder": True,
            }
        )
        player = self._make_player(gender="male")
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertTrue(result["eligible"], "Placeholder rule should not be enforced.")

    # ------------------------------------------------------------------
    # Multiple rules — compound failure
    # ------------------------------------------------------------------

    def test_multiple_failures_accumulate_reasons(self):
        """When two rules fail, both reasons are returned."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Multi Fail RS",
                "code": "MFRS",
            }
        )
        # Age min: must be 18
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Min 18",
                "eligibility_type": "age_min",
                "age_limit": 18,
            }
        )
        # Gender: female only
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Female Only",
                "eligibility_type": "gender",
                "allowed_categories": "female",
            }
        )

        # 15-year-old male player — fails both
        bd = date.today().replace(year=date.today().year - 15)
        player = self._make_player(gender="male", birth_date=bd.isoformat())
        result = self.service.check_player_eligibility(player, rule_set)
        self.assertFalse(result["eligible"])
        self.assertEqual(len(result["reasons"]), 2, "Two separate reasons expected.")

    # ------------------------------------------------------------------
    # check_roster_eligibility
    # ------------------------------------------------------------------

    def test_check_roster_eligibility_returns_per_player(self):
        """check_roster_eligibility returns a dict keyed by player ID."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Roster Elig RS",
                "code": "RRSRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "No Suspension",
                "eligibility_type": "suspension",
            }
        )
        # Need roster model — skip if not available
        Roster = self.env.get("federation.team.roster")
        if not Roster:
            self.skipTest("federation.team.roster not available.")

        bd = date.today().replace(year=date.today().year - 22)
        player = self._make_player(state="active", birth_date=bd.isoformat())
        suspended = self._make_player(state="suspended")

        roster = Roster.create(
            {
                "name": "Test Roster",
                "team_id": self.team.id,
                "season_id": self.season.id,
                "rule_set_id": rule_set.id,
            }
        )
        RosterLine = self.env["federation.team.roster.line"]
        RosterLine.create({"roster_id": roster.id, "player_id": player.id})
        RosterLine.create({"roster_id": roster.id, "player_id": suspended.id})

        results = self.service.check_roster_eligibility(roster)
        self.assertIn(player.id, results)
        self.assertIn(suspended.id, results)
        self.assertTrue(results[player.id]["eligible"])
        self.assertFalse(results[suspended.id]["eligible"])

    # ------------------------------------------------------------------
    # check_match_eligibility
    # ------------------------------------------------------------------

    def test_check_match_eligibility(self):
        """check_match_eligibility uses rule set from tournament and checks players."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Match Elig RS",
                "code": "MERS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "No Suspension",
                "eligibility_type": "suspension",
            }
        )
        self.tournament.write({"rule_set_id": rule_set.id})

        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team.id,
                "away_team_id": self.team.id,
                "state": "draft",
            }
        )

        bd = date.today().replace(year=date.today().year - 22)
        active_player = self._make_player(state="active", birth_date=bd.isoformat())
        susp_player = self._make_player(state="suspended")
        players = active_player | susp_player

        results = self.service.check_match_eligibility(match, self.team, players)
        self.assertTrue(results[active_player.id]["eligible"])
        self.assertFalse(results[susp_player.id]["eligible"])

    def test_no_rule_set_returns_eligible(self):
        """Without a rule set every player is considered eligible."""
        player = self._make_player(state="suspended")  # would fail suspension
        result = self.service.check_player_eligibility(
            player, self.env["federation.rule.set"].browse([])
        )
        self.assertTrue(result["eligible"])

    def test_license_rule_respects_season_and_club_context(self):
        """License validation must respect the workflow season and club context."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "License Context RS",
                "code": "LCRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Active Seasonal License",
                "eligibility_type": "license_valid",
            }
        )
        other_season = self.env["federation.season"].create(
            {
                "name": "Other Elig Season",
                "code": "OES24",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        other_club = self.env["federation.club"].create(
            {
                "name": "Other Elig Club",
                "code": "OEC",
            }
        )
        player = self._make_player(state="active")
        self.env["federation.player.license"].create(
            {
                "name": "LIC-CONTEXT",
                "player_id": player.id,
                "season_id": self.season.id,
                "club_id": self.club.id,
                "issue_date": "2024-01-01",
                "expiry_date": "2024-12-31",
                "state": "active",
            }
        )

        good = self.service.check_player_eligibility(
            player,
            rule_set,
            context={
                "season_id": self.season.id,
                "club_id": self.club.id,
                "match_date": date(2024, 6, 1),
            },
        )
        self.assertTrue(good["eligible"])

        wrong_season = self.service.check_player_eligibility(
            player,
            rule_set,
            context={
                "season_id": other_season.id,
                "club_id": self.club.id,
                "match_date": date(2024, 6, 1),
            },
        )
        self.assertFalse(wrong_season["eligible"])
        self.assertIn("no active license", wrong_season["reasons"][0].lower())

        wrong_club = self.service.check_player_eligibility(
            player,
            rule_set,
            context={
                "season_id": self.season.id,
                "club_id": other_club.id,
                "match_date": date(2024, 6, 1),
            },
        )
        self.assertFalse(wrong_club["eligible"])
        self.assertIn("no active license", wrong_club["reasons"][0].lower())

    def test_registration_rule_requires_team_season_registration(self):
        """Registration eligibility should follow the team season-registration model."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Registration RS",
                "code": "REGRS",
            }
        )
        self.env["federation.eligibility.rule"].create(
            {
                "rule_set_id": rule_set.id,
                "name": "Season Registration Required",
                "eligibility_type": "registration",
            }
        )
        player = self._make_player(state="active")

        missing = self.service.check_player_eligibility(
            player,
            rule_set,
            context={
                "season_id": self.season.id,
                "team_id": self.team.id,
            },
        )
        self.assertFalse(missing["eligible"])
        self.assertIn("not registered for season", missing["reasons"][0].lower())

        self.env["federation.season.registration"].create(
            {
                "name": "REG-TEAM",
                "team_id": self.team.id,
                "season_id": self.season.id,
                "state": "confirmed",
            }
        )
        registered = self.service.check_player_eligibility(
            player,
            rule_set,
            context={
                "season_id": self.season.id,
                "team_id": self.team.id,
            },
        )
        self.assertTrue(registered["eligible"])
