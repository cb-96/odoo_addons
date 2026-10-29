class CoverageFixture:
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.portal_official_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_official"
        )
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Portal Official Club",
                "code": "POC",
            }
        )
        cls.home_team = cls.env["federation.team"].create(
            {
                "name": "Portal Official Home",
                "club_id": cls.club.id,
                "code": "POH",
            }
        )
        cls.away_team = cls.env["federation.team"].create(
            {
                "name": "Portal Official Away",
                "club_id": cls.club.id,
                "code": "POA",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Portal Official Season",
                "code": "POS",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {"name": "Portal Official Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Portal Official Edition",
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Portal Official Tournament",
                "code": "POT",
                "season_id": cls.season.id,
                "competition_id": cls.competition.id,
                "edition_id": cls.edition.id,
                "date_start": "2026-06-01",
            }
        )
        participant_set = cls.env["federation.participant.set"].create(
            {
                "name": "Portal Official Participants",
                "edition_id": cls.edition.id,
                "division_id": cls.tournament.id,
                "state": "finalized",
            }
        )
        structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Portal Official Structure",
                "edition_id": cls.edition.id,
                "division_id": cls.tournament.id,
                "participant_set_id": participant_set.id,
                "format_type": "custom",
            }
        )
        stage = cls.env["federation.structure.stage"].create(
            {
                "name": "Portal Official Stage",
                "structure_id": structure.id,
                "stage_type": "league",
                "format_type": "manual",
                "source_type": "manual",
            }
        )
        fixtures = cls.env["federation.fixture"].create(
            [
                {
                    "structure_id": structure.id,
                    "stage_id": stage.id,
                    "round_number": 1,
                    "sequence": 1,
                    "home_team_id": cls.home_team.id,
                    "away_team_id": cls.away_team.id,
                    "state": "ready",
                },
                {
                    "structure_id": structure.id,
                    "stage_id": stage.id,
                    "round_number": 1,
                    "sequence": 2,
                    "home_team_id": cls.away_team.id,
                    "away_team_id": cls.home_team.id,
                    "state": "ready",
                },
            ]
        )
        cls.match = fixtures[0].action_materialize_match()
        cls.other_match = fixtures[1].action_materialize_match()
        cls.match.write({"date_scheduled": "2026-06-15 18:00:00"})
        cls.other_match.write({"date_scheduled": "2026-06-21 14:00:00"})
        venue = cls.env["federation.venue"].create({"name": "Portal Official Venue"})
        matchday = cls.env["federation.matchday"].create(
            {
                "name": "Portal Official Match Day",
                "edition_id": cls.edition.id,
                "date": "2026-06-15",
                "venue_id": venue.id,
            }
        )
        schedule = cls.env["federation.schedule"].create(
            {
                "name": "Portal Official Schedule",
                "edition_id": cls.edition.id,
                "structure_id": structure.id,
                "matchday_id": matchday.id,
                "state": "published",
            }
        )
        snapshot = [{"fixture_id": fixtures[0].id}]
        digest = cls.env["federation.schedule.publication"].digest_snapshot(snapshot)
        review = (
            cls.env["federation.schedule.review"]
            .sudo()
            .create(
                {
                    "schedule_id": schedule.id,
                    "submitted_revision": schedule.revision,
                    "state": "pending",
                    "assignment_snapshot": snapshot,
                    "snapshot_digest": digest,
                    "submitted_by_id": cls.env.user.id,
                }
            )
        )
        review._write_decision({"state": "approved", "reviewer_id": cls.env.user.id})
        publication = cls.env["federation.schedule.publication"].create(
            {
                "schedule_id": schedule.id,
                "version": 1,
                "state": "live",
                "assignment_snapshot": snapshot,
                "snapshot_digest": digest,
                "source_revision": schedule.revision,
                "review_id": review.id,
            }
        )
        matchday.sudo().write({"current_publication_id": publication.id})
        (cls.match | cls.other_match).write({"schedule_publication_id": publication.id})
        cls.official_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Portal Official User",
                    "login": "portal.official@example.com",
                    "email": "portal.official@example.com",
                    "group_ids": [(6, 0, [cls.portal_official_group.id])],
                }
            )
        )
        cls.other_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Other Official User",
                    "login": "portal.other.official@example.com",
                    "email": "portal.other.official@example.com",
                    "group_ids": [(6, 0, [cls.portal_official_group.id])],
                }
            )
        )
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Portal Referee",
                "email": "portal.official@example.com",
                "certification_level": "national",
                "user_id": cls.official_user.id,
            }
        )
        cls.other_referee = cls.env["federation.referee"].create(
            {
                "name": "Other Portal Referee",
                "email": "portal.other.official@example.com",
                "certification_level": "regional",
                "user_id": cls.other_user.id,
            }
        )
        cls.assignment = cls.env["federation.match.referee"].create(
            {
                "match_id": cls.match.id,
                "referee_id": cls.referee.id,
                "role": "head",
            }
        )
        cls.other_assignment = cls.env["federation.match.referee"].create(
            {
                "match_id": cls.other_match.id,
                "referee_id": cls.other_referee.id,
                "role": "assistant_1",
            }
        )

        for ref in (cls.referee, cls.other_referee):
            cls.env["federation.referee.availability"].create(
                {
                    "referee_id": ref.id,
                    "date_start": "2026-01-01 00:00:00",
                    "date_end": "2027-01-01 00:00:00",
                }
            )
        cls.manager = cls.env.ref("base.user_admin")
        cls.manager.write(
            {
                "group_ids": [
                    (
                        4,
                        cls.env.ref(
                            "sports_federation_base.group_federation_manager"
                        ).id,
                    )
                ]
            }
        )
        cls.match.write(
            {
                "coverage_override": True,
                "coverage_head_required": 1,
                "coverage_owner_id": cls.manager.id,
            }
        )

        court = cls.env["federation.playing.area"].create(
            {"name": "Coverage court", "venue_id": venue.id}
        )
        slot = cls.env["federation.schedule.slot"].create(
            {
                "matchday_id": matchday.id,
                "court_id": court.id,
                "start_datetime": "2026-06-15 18:00:00",
                "end_datetime": "2026-06-15 18:30:00",
            }
        )
        cls.match.write({"published_slot_id": slot.id})
        (cls.referee | cls.other_referee).write({"coverage_playing_checked": True})
