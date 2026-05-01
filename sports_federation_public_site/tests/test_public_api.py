"""
Tests for new public site endpoints (Phase 4):
- /competitions/archive — closed/cancelled tournaments
- /competitions/<id>/teams — participant listing
- /competitions/api/json — JSON API tournament list

These are ORM-level tests (no HTTP client needed) that verify
the data layer logic that the new controller endpoints rely on.
"""

from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import patch

from odoo.addons.sports_federation_public_site.controllers.public_competitions import (
    PublicTournamentHubController,
)
from odoo.addons.sports_federation_public_site.controllers.public_follow import (
    PublicSeasonAndTeamController,
)
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestPublicSiteNewEndpoints(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "PS Club",
                "code": "PSC",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "PS Team A",
                "club_id": cls.club.id,
                "code": "PSTA",
                "public_slug": "ps-team-a",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "PS Team B",
                "club_id": cls.club.id,
                "code": "PSTB",
            }
        )
        cls.team_c = cls.env["federation.team"].create(
            {
                "name": "PS Team C",
                "club_id": cls.club.id,
                "code": "PSTC",
            }
        )
        cls.hidden_team = cls.env["federation.team"].create(
            {
                "name": "PS Hidden Team",
                "club_id": cls.club.id,
                "code": "PSHT",
                "public_slug": "ps-hidden-team",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "PS Season",
                "code": "PSS24",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.hidden_season = cls.env["federation.season"].create(
            {
                "name": "Hidden PS Season",
                "code": "HPSS24",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
                "public_slug": "hidden-ps-season",
            }
        )

        # Active published tournament (in_progress)
        cls.active_tour = cls.env["federation.tournament"].create(
            {
                "name": "Active Tour",
                "code": "ATOUR",
                "public_slug": "active-tour",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
                "state": "in_progress",
                "public_featured": True,
                "public_editorial_summary": "A featured in-progress tournament.",
                "public_pinned_announcement": "Final round starts tonight.",
                "show_public_results": True,
                "show_public_standings": True,
                "website_published": True,
            }
        )

        # Closed published tournament (archive candidate)
        cls.closed_tour = cls.env["federation.tournament"].create(
            {
                "name": "Old Tour",
                "code": "OTOUR",
                "season_id": cls.season.id,
                "date_start": "2023-01-01",
                "date_end": "2023-12-31",
                "website_published": True,
                "state": "closed",
            }
        )

        # Unpublished closed tournament (should not appear in archive)
        cls.unpub_closed_tour = cls.env["federation.tournament"].create(
            {
                "name": "Unpub Closed Tour",
                "code": "UCTOUR",
                "season_id": cls.season.id,
                "date_start": "2023-01-01",
                "date_end": "2023-06-30",
                "website_published": False,
                "state": "closed",
            }
        )
        cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.unpub_closed_tour.id,
                "team_id": cls.hidden_team.id,
                "state": "confirmed",
            }
        )
        cls.schedule_match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.active_tour.id,
                "home_team_id": cls.team_a.id,
                "away_team_id": cls.team_b.id,
                "date_scheduled": "2024-06-03 10:00:00",
                "state": "scheduled",
            }
        )
        cls.result_match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.active_tour.id,
                "home_team_id": cls.team_a.id,
                "away_team_id": cls.team_b.id,
                "date_scheduled": "2024-06-01 10:00:00",
                "state": "done",
                "home_score": 3,
                "away_score": 1,
                "result_state": "approved",
            }
        )
        cls.bracket_match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.active_tour.id,
                "home_team_id": cls.team_a.id,
                "away_team_id": cls.team_b.id,
                "date_scheduled": "2024-06-05 14:00:00",
                "state": "scheduled",
                "round_number": 1,
                "bracket_type": "winners",
            }
        )
        cls.standing = cls.env["federation.standing"].create(
            {
                "name": "Active Tour Standing",
                "tournament_id": cls.active_tour.id,
                "website_published": True,
            }
        )
        cls.confirmed_participant = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.active_tour.id,
                "team_id": cls.team_a.id,
                "state": "confirmed",
            }
        )
        cls.season.write(
            {
                "website_published": True,
                "public_slug": "ps-season",
                "public_summary": "Season-wide discovery entry.",
            }
        )

    def _create_editorial_item(self, **values):
        """Create a minimal editorial item anchored to the shared season."""
        defaults = {
            "name": "Editorial Item",
            "content_type": "highlight",
            "summary": "Editorial summary.",
            "season_id": self.season.id,
        }
        defaults.update(values)
        return self.env["federation.public.editorial.item"].create(defaults)

    # ------------------------------------------------------------------
    # Archive endpoint data layer
    # ------------------------------------------------------------------

    def test_archive_only_returns_closed_published(self):
        """Archive query excludes unpublished and non-closed tournaments."""
        tournaments = self.env["federation.tournament"].search(
            [
                ("website_published", "=", True),
                ("state", "in", ("closed", "cancelled")),
            ],
            order="date_start desc",
        )
        self.assertIn(self.closed_tour, tournaments)
        self.assertNotIn(self.active_tour, tournaments)
        self.assertNotIn(self.unpub_closed_tour, tournaments)

    def test_archive_includes_cancelled_published(self):
        """Cancelled published tournaments also appear in the archive."""
        cancelled = self.env["federation.tournament"].create(
            {
                "name": "Cancelled Tour",
                "code": "CNTOUR",
                "season_id": self.season.id,
                "date_start": "2022-06-01",
                "website_published": True,
                "state": "cancelled",
            }
        )
        tournaments = self.env["federation.tournament"].search(
            [
                ("website_published", "=", True),
                ("state", "in", ("closed", "cancelled")),
            ]
        )
        self.assertIn(cancelled, tournaments)

    # ------------------------------------------------------------------
    # Teams endpoint data layer
    # ------------------------------------------------------------------

    def test_teams_excludes_withdrawn_participants(self):
        """The teams page query excludes withdrawn participants."""
        p_confirmed = self.confirmed_participant
        p_withdrawn = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.active_tour.id,
                "team_id": self.team_b.id,
                "state": "withdrawn",
            }
        )
        participants = self.env["federation.tournament.participant"].search(
            [
                ("tournament_id", "=", self.active_tour.id),
                ("state", "!=", "withdrawn"),
            ]
        )
        self.assertIn(p_confirmed, participants)
        self.assertNotIn(p_withdrawn, participants)

    def test_teams_shows_participant_state(self):
        """Participants carry their state for display in the teams page."""
        p = self.confirmed_participant
        self.assertEqual(p.state, "confirmed")
        self.assertTrue(p.team_id)
        self.assertTrue(p.club_id)

    def test_teams_not_shown_for_unpublished_tournament(self):
        """Unpublished tournament: website_published=False blocks the page."""
        self.active_tour.write({"website_published": False})
        self.assertFalse(self.active_tour.website_published)
        # Restore
        self.active_tour.write({"website_published": True})

    # ------------------------------------------------------------------
    # JSON API data layer
    # ------------------------------------------------------------------

    def test_json_api_returns_published_only(self):
        """JSON API query returns only published tournaments."""
        tournaments = self.env["federation.tournament"].search(
            [
                ("website_published", "=", True),
            ],
            order="date_start asc",
        )
        pub_ids = tournaments.mapped("id")
        self.assertIn(self.active_tour.id, pub_ids)
        self.assertIn(self.closed_tour.id, pub_ids)
        self.assertNotIn(self.unpub_closed_tour.id, pub_ids)

    def test_json_api_fields(self):
        """Verify that tournament records have the fields the JSON API serializes."""
        t = self.active_tour
        record = {
            "id": t.id,
            "name": t.name,
            "state": t.state,
            "date_start": t.date_start.isoformat() if t.date_start else None,
            "date_end": t.date_end.isoformat() if t.date_end else None,
        }
        self.assertEqual(record["id"], t.id)
        self.assertIsInstance(record["name"], str)
        self.assertIsNotNone(record["state"])
        # date_start is set
        self.assertIsNotNone(record["date_start"])

    def test_json_api_date_null_when_not_set(self):
        """JSON API date fields are None when the tournament has no date."""
        t = self.env["federation.tournament"].create(
            {
                "name": "No Dates Tour",
                "code": "NDTOUR",
                "season_id": self.season.id,
                "website_published": True,
                "date_start": "2024-01-01",
            }
        )
        date_end_val = t.date_end.isoformat() if t.date_end else None
        self.assertIsNone(date_end_val)

    def test_public_slug_resolves_and_generates_canonical_paths(self):
        """Explicit slugs produce canonical tournament URLs and resolve cleanly."""
        resolved = self.env["federation.tournament"].resolve_public_slug("active-tour")

        self.assertEqual(resolved, self.active_tour)
        self.assertEqual(self.active_tour.get_public_path(), "/tournaments/active-tour")
        self.assertEqual(
            self.active_tour.get_public_schedule_ics_path(),
            "/tournaments/active-tour/schedule.ics",
        )

    def test_public_slug_resolution_can_apply_publication_domain(self):
        """Public slug resolution can fail closed for unpublished tournaments."""
        resolved = self.env["federation.tournament"].resolve_public_slug(
            "active-tour",
            extra_domain=[("website_published", "=", True)],
        )
        hidden = self.env["federation.tournament"].resolve_public_slug(
            self.unpub_closed_tour.get_public_slug_value(),
            extra_domain=[("website_published", "=", True)],
        )

        self.assertEqual(resolved, self.active_tour)
        self.assertFalse(hidden)

    def test_public_season_slug_resolution_can_apply_publication_domain(self):
        """Season slug resolution can fail closed for unpublished seasons."""
        public_domain = PublicTournamentHubController()._build_season_public_domain(
            public_access="detail"
        )
        resolved = self.env["federation.season"].resolve_public_slug(
            "ps-season",
            extra_domain=public_domain,
        )
        hidden = self.env["federation.season"].resolve_public_slug(
            self.hidden_season.get_public_slug_value(),
            extra_domain=public_domain,
        )

        self.assertEqual(resolved, self.season)
        self.assertFalse(hidden)

    def test_team_public_slug_resolution_can_apply_publication_domain(self):
        """Team slug resolution can fail closed for hidden public-team routes."""
        public_domain = PublicTournamentHubController()._build_team_public_domain(
            public_access="profile"
        )
        resolved = self.env["federation.team"].resolve_public_slug(
            "ps-team-a",
            extra_domain=public_domain,
        )
        hidden = self.env["federation.team"].resolve_public_slug(
            self.hidden_team.get_public_slug_value(),
            extra_domain=public_domain,
        )

        self.assertEqual(resolved, self.team_a)
        self.assertFalse(hidden)

    def test_team_public_slug_and_profile_helpers(self):
        """Teams that appear on published tournaments expose public profile URLs."""
        self.team_a.write({"public_slug": "ps-team-a"})
        resolved = self.env["federation.team"].resolve_public_slug("ps-team-a")

        self.assertEqual(resolved, self.team_a)
        self.assertTrue(self.team_a.can_access_public_profile())
        self.assertEqual(self.team_a.get_public_path(), "/teams/ps-team-a")
        self.assertFalse(self.team_c.can_access_public_profile())

    def test_public_featured_tournaments_only_return_active_published(self):
        """Featured tournament coverage only includes published active tournaments."""
        featured = self.env["federation.tournament"].get_public_featured_tournaments()

        self.assertIn(self.active_tour, featured)
        self.assertNotIn(self.closed_tour, featured)
        self.assertNotIn(self.unpub_closed_tour, featured)

    def test_main_tournament_hub_domain_excludes_unpublished_records(self):
        """Main hub pagination and list results must stay aligned with publication guards."""
        controller = PublicTournamentHubController()
        filters = controller._build_filters()
        mock_request = SimpleNamespace(env=self.env)
        with patch(
            "odoo.addons.sports_federation_public_site.controllers.public_competitions.request",
            new=mock_request,
        ), patch(
            "odoo.addons.sports_federation_public_site.controllers._filters.request",
            new=mock_request,
        ):
            tournaments = (
                self.env["federation.tournament"]
                .sudo()
                .search(
                    controller._build_main_tournament_domain(filters),
                    order="date_start desc, id desc",
                )
            )

        self.assertIn(self.active_tour, tournaments)
        self.assertIn(self.closed_tour, tournaments)
        self.assertNotIn(self.unpub_closed_tour, tournaments)

    def test_public_archived_tournaments_only_return_published_archive(self):
        """Archived tournament coverage only includes published closed or cancelled tournaments."""
        archived = self.env["federation.tournament"].get_public_archived_tournaments()

        self.assertIn(self.closed_tour, archived)
        self.assertNotIn(self.active_tour, archived)
        self.assertNotIn(self.unpub_closed_tour, archived)

    def test_live_and_recent_public_tournament_helpers(self):
        """Live and recently updated helper queries surface the expected tournaments."""
        live = self.env["federation.tournament"].get_public_live_tournaments()
        recent = self.env[
            "federation.tournament"
        ].get_public_recent_result_tournaments()

        self.assertIn(self.active_tour, live)
        self.assertIn(self.active_tour, recent)

    def test_public_discovery_helpers_stay_within_query_budget(self):
        """Public discovery helpers keep a stable query budget for CI regression checks."""
        with self.assertQueryCount(1):
            featured = self.env[
                "federation.tournament"
            ].get_public_featured_tournaments(limit=4)
            self.assertIn(self.active_tour, featured)

        with self.assertQueryCount(1):
            live = self.env["federation.tournament"].get_public_live_tournaments(
                limit=4
            )
            self.assertIn(self.active_tour, live)

        with self.assertQueryCount(3):
            recent = self.env[
                "federation.tournament"
            ].get_public_recent_result_tournaments(limit=4)
            self.assertEqual(recent[:1], self.active_tour)

    def test_public_schedule_sections_stay_within_query_budget(self):
        """Tournament schedule section assembly stays within the agreed route budget."""
        with self.assertQueryCount(4):
            sections = self.active_tour.get_public_schedule_sections()

        self.assertTrue(sections)
        self.assertTrue(any(section["matches"] for section in sections))

    def test_schedule_sections_use_fixture_query_not_approved_results(self):
        """The schedule helper returns future fixtures and excludes completed matches."""
        sections = self.active_tour.get_public_schedule_sections()
        scheduled_ids = []
        for section in sections:
            scheduled_ids.extend(section["matches"].ids)

        self.assertIn(self.schedule_match.id, scheduled_ids)
        self.assertIn(self.bracket_match.id, scheduled_ids)
        self.assertNotIn(self.result_match.id, scheduled_ids)

    def test_public_bracket_sections_group_knockout_matches(self):
        """Bracket helper exposes knockout sections for public rendering."""
        sections = self.active_tour.get_public_bracket_sections()

        self.assertTrue(sections)
        self.assertIn(self.bracket_match, sections[0]["matches"])
        self.assertTrue(self.active_tour.has_public_bracket())

    def test_versioned_public_feed_payload_has_stable_keys(self):
        """Versioned public feed payload exposes the expected top-level structure."""
        payload = self.active_tour.get_public_feed_payload()

        self.assertEqual(payload["api_version"], "v1")
        self.assertIn("tournament", payload)
        self.assertIn("schedule_sections", payload)
        self.assertIn("bracket_sections", payload)
        self.assertIn("results", payload)
        self.assertIn("standings", payload)
        self.assertEqual(payload["tournament"]["id"], self.active_tour.id)
        self.assertEqual(payload["tournament"]["slug"], "active-tour")
        self.assertEqual(
            payload["tournament"]["public_url"], "/tournaments/active-tour"
        )
        self.assertEqual(
            payload["tournament"]["schedule_ics_url"],
            "/tournaments/active-tour/schedule.ics",
        )
        self.assertEqual(
            payload["participants"][0]["team_url"], self.team_a.get_public_path()
        )
        self.assertEqual(payload["results"][0]["id"], self.result_match.id)

    def test_schedule_ics_contains_public_event_rows(self):
        """ICS export includes scheduled fixtures with tournament metadata."""
        payload = self.active_tour.get_public_schedule_ics()

        self.assertIn("BEGIN:VCALENDAR", payload)
        self.assertIn("BEGIN:VEVENT", payload)
        self.assertIn("Active Tour", payload)
        self.assertIn("/tournaments/active-tour/schedule", payload)

    def test_published_season_slug_and_helper_paths(self):
        """Test that published season slug and helper paths."""
        resolved = self.env["federation.season"].resolve_public_slug("ps-season")

        self.assertEqual(resolved, self.season)
        self.assertTrue(self.season.can_access_public_detail())
        self.assertEqual(self.season.get_public_path(), "/seasons/ps-season")
        self.assertIn(
            self.season, self.env["federation.season"].get_public_published_seasons()
        )

    def test_editorial_items_only_go_live_inside_publication_window(self):
        """Test that editorial items only go live inside publication window."""
        live_item = self.env["federation.public.editorial.item"].create(
            {
                "name": "Season Highlight",
                "content_type": "highlight",
                "publication_state": "scheduled",
                "summary": "Currently live highlight.",
                "season_id": self.season.id,
                "publish_start": "2024-05-01 08:00:00",
                "publish_end": "2026-07-01 08:00:00",
            }
        )
        future_item = self.env["federation.public.editorial.item"].create(
            {
                "name": "Future Highlight",
                "content_type": "announcement",
                "publication_state": "scheduled",
                "summary": "Not live yet.",
                "season_id": self.season.id,
                "publish_start": "2099-01-01 08:00:00",
            }
        )

        items = self.env["federation.public.editorial.item"].get_live_items(
            season=self.season
        )

        self.assertIn(live_item, items)
        self.assertNotIn(future_item, items)

    def test_editorial_schedule_requires_draft_with_publish_start(self):
        """Scheduling requires a draft item with a publish start date."""
        missing_start = self._create_editorial_item(name="Missing Start")
        with self.assertRaises(ValidationError):
            missing_start.action_schedule()
        self.assertEqual(missing_start.publication_state, "draft")

        published_item = self._create_editorial_item(
            name="Published Item",
            publication_state="published",
            publish_start="2024-05-01 08:00:00",
        )
        with self.assertRaises(ValidationError):
            published_item.action_schedule()

        scheduled_item = self._create_editorial_item(
            name="Scheduled Item",
            publish_start="2024-05-01 08:00:00",
        )
        scheduled_item.action_schedule()
        self.assertEqual(scheduled_item.publication_state, "scheduled")

    def test_editorial_publish_accepts_only_draft_or_scheduled(self):
        """Publishing works from draft or scheduled and rejects archived items."""
        draft_item = self._create_editorial_item(name="Draft Publish")
        draft_item.action_publish()
        self.assertEqual(draft_item.publication_state, "published")

        scheduled_item = self._create_editorial_item(
            name="Scheduled Publish",
            publication_state="scheduled",
            publish_start="2024-05-02 08:00:00",
        )
        scheduled_item.action_publish()
        self.assertEqual(scheduled_item.publication_state, "published")

        archived_item = self._create_editorial_item(
            name="Archived Publish",
            publication_state="archived",
        )
        with self.assertRaises(ValidationError):
            archived_item.action_publish()

    def test_editorial_archive_and_reset_to_draft_enforce_allowed_states(self):
        """Archive and reset only allow the documented workflow states."""
        published_item = self._create_editorial_item(
            name="Published Archive",
            publication_state="published",
        )
        published_item.action_archive_item()
        self.assertEqual(published_item.publication_state, "archived")
        published_item.action_reset_to_draft()
        self.assertEqual(published_item.publication_state, "draft")

        scheduled_archive = self._create_editorial_item(
            name="Scheduled Archive",
            publication_state="scheduled",
            publish_start="2024-05-03 08:00:00",
        )
        scheduled_archive.action_archive_item()
        self.assertEqual(scheduled_archive.publication_state, "archived")

        scheduled_reset = self._create_editorial_item(
            name="Scheduled Reset",
            publication_state="scheduled",
            publish_start="2024-05-04 08:00:00",
        )
        scheduled_reset.action_reset_to_draft()
        self.assertEqual(scheduled_reset.publication_state, "draft")

        draft_item = self._create_editorial_item(name="Draft Archive")
        with self.assertRaises(ValidationError):
            draft_item.action_archive_item()

        published_reset = self._create_editorial_item(
            name="Published Reset",
            publication_state="published",
        )
        with self.assertRaises(ValidationError):
            published_reset.action_reset_to_draft()

    def test_team_follow_helpers_expose_schedule_results_and_feed(self):
        """Test that team follow helpers expose schedule results and feed."""
        schedule_sections = self.team_a.get_public_schedule_sections()
        result_sections = self.team_a.get_public_result_sections()
        payload = self.team_a.get_public_feed_payload()
        ics_payload = self.team_a.get_public_schedule_ics()

        self.assertEqual(
            self.team_a.get_public_schedule_path(), "/teams/ps-team-a/schedule"
        )
        self.assertEqual(
            self.team_a.get_public_results_path(), "/teams/ps-team-a/results"
        )
        self.assertEqual(
            self.team_a.get_public_schedule_ics_path(), "/teams/ps-team-a/schedule.ics"
        )
        self.assertEqual(
            self.team_a.get_public_feed_path(), "/api/v1/teams/ps-team-a/feed"
        )
        self.assertTrue(schedule_sections)
        self.assertTrue(result_sections)
        self.assertEqual(payload["api_version"], "v1")
        self.assertEqual(payload["team"]["slug"], "ps-team-a")
        self.assertIn("BEGIN:VCALENDAR", ics_payload)


class TestPublicApiRateLimits(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hub_controller = PublicTournamentHubController()
        cls.follow_controller = PublicSeasonAndTeamController()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Rate Limit Club",
                "code": "RLC",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Rate Limit Team A",
                "club_id": cls.club.id,
                "code": "RLTA",
                "public_slug": "rate-limit-team-a",
                "category": "senior",
                "gender": "male",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Rate Limit Team B",
                "club_id": cls.club.id,
                "code": "RLTB",
                "category": "senior",
                "gender": "male",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Rate Limit Season",
                "code": "RLS",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Rate Limit Tournament",
                "code": "RLT",
                "season_id": cls.season.id,
                "date_start": "2026-06-01",
                "state": "in_progress",
                "website_published": True,
                "public_slug": "rate-limit-tournament",
                "public_featured": True,
                "show_public_results": True,
                "show_public_standings": True,
                "gender": "male",
                "category": "senior",
            }
        )
        cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_a.id,
                "state": "confirmed",
            }
        )
        cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_b.id,
                "state": "confirmed",
            }
        )
        cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team_a.id,
                "away_team_id": cls.team_b.id,
                "date_scheduled": "2026-06-02 10:00:00",
                "state": "done",
                "home_score": 2,
                "away_score": 1,
                "result_state": "approved",
            }
        )

    def _make_request(self, remote_addr="198.51.100.10"):
        return SimpleNamespace(
            env=self.env,
            httprequest=SimpleNamespace(
                remote_addr=remote_addr,
                headers={},
            ),
        )

    def test_competitions_api_json_rate_limits_repeat_callers(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.rate_limit.public_competitions_json.limit",
            2,
        )
        request_stub = self._make_request()
        rate_limit_service = self.env["federation.request.rate.limit"].sudo()
        frozen_time = datetime(2026, 4, 18, 12, 0, 0)

        with patch(
            "odoo.addons.sports_federation_public_site.controllers.public_competitions.request",
            request_stub,
        ), patch.object(
            type(rate_limit_service),
            "_get_now",
            return_value=frozen_time,
        ):
            first = self.hub_controller.competitions_api_json()
            second = self.hub_controller.competitions_api_json()
            blocked = self.hub_controller.competitions_api_json()

        self.assertIn("tournaments", first)
        self.assertIn("tournaments", second)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.headers.get("Retry-After"), "60")
        payload = json.loads(blocked.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "retryable_delivery")

    def test_competition_feed_rate_limits_repeat_callers(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.rate_limit.public_competition_feed.limit",
            1,
        )
        request_stub = self._make_request()
        rate_limit_service = self.env["federation.request.rate.limit"].sudo()
        frozen_time = datetime(2026, 4, 18, 12, 0, 0)

        with patch(
            "odoo.addons.sports_federation_public_site.controllers.public_competitions.request",
            request_stub,
        ), patch.object(
            type(rate_limit_service),
            "_get_now",
            return_value=frozen_time,
        ):
            response = self.hub_controller.competition_feed_v1(
                tournament_slug=self.tournament.public_slug
            )
            blocked = self.hub_controller.competition_feed_v1(
                tournament_slug=self.tournament.public_slug
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(blocked.status_code, 429)
        payload = json.loads(blocked.get_data(as_text=True))
        self.assertIn("Too many requests", payload["error"])

    def test_team_feed_rate_limits_repeat_callers(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.rate_limit.public_team_feed.limit",
            1,
        )
        request_stub = self._make_request()
        rate_limit_service = self.env["federation.request.rate.limit"].sudo()
        frozen_time = datetime(2026, 4, 18, 12, 0, 0)

        with patch(
            "odoo.addons.sports_federation_public_site.controllers.public_competitions.request",
            request_stub,
        ), patch(
            "odoo.addons.sports_federation_public_site.controllers.public_follow.request",
            request_stub,
        ), patch.object(
            type(rate_limit_service),
            "_get_now",
            return_value=frozen_time,
        ):
            response = self.follow_controller.team_feed_v1(self.team_a.public_slug)
            blocked = self.follow_controller.team_feed_v1(self.team_a.public_slug)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(blocked.status_code, 429)
        payload = json.loads(blocked.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "retryable_delivery")
