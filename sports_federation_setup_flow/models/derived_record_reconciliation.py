from odoo import api, models


class FederationDerivedRecordReconciliation(models.AbstractModel):
    """Read-only health report for cross-addon competition records.

    Detection is deliberately separated from repair. Repair helpers are explicit
    and narrow, and only create/relink records through the domain owners.
    """

    _name = "federation.derived.record.reconciliation"
    _description = "Federation Derived Record Reconciliation"

    HEALTHY = "healthy"
    MISSING = "missing"
    ORPHANED = "orphaned"
    CONFLICTING = "conflicting"

    @api.model
    def _issue(self, status, relation, source, detail, repairable=False):
        return {
            "status": status,
            "relation": relation,
            "source_model": source._name,
            "source_id": source.id,
            "source_name": source.display_name,
            "detail": detail,
            "repairable": bool(repairable),
        }

    @api.model
    def report(self, edition=None):
        """Report materialization defects without changing domain records."""
        issues = []
        edition_domain = [("edition_id", "=", edition.id)] if edition else []

        ParticipantSet = self.env["federation.participant.set"].sudo()
        for participant_set in ParticipantSet.search(
            edition_domain + [("state", "=", "finalized")]
        ):
            tournament = participant_set.division_id
            expected = set(participant_set.line_ids.mapped("team_id").ids)
            actual_rows = (
                self.env["federation.tournament.participant"]
                .sudo()
                .search(
                    [("tournament_id", "=", tournament.id), ("state", "=", "confirmed")]
                )
            )
            actual = set(actual_rows.mapped("team_id").ids)
            if expected != actual:
                issues.append(
                    self._issue(
                        self.MISSING if expected - actual else self.ORPHANED,
                        "participant_set_to_tournament_participant",
                        participant_set,
                        "Confirmed tournament participants do not match the finalized participant set.",
                        repairable=True,
                    )
                )

        fixture_domain = (
            [("structure_id.edition_id", "=", edition.id)] if edition else []
        )
        fixtures = self.env["federation.fixture"].sudo().search(fixture_domain)
        for fixture in fixtures:
            playable = (
                fixture.state != "cancelled"
                and not fixture.bye_team_id
                and fixture.home_team_id
                and fixture.away_team_id
            )
            linked = (
                self.env["federation.match"]
                .sudo()
                .search([("logical_fixture_id", "=", fixture.id)])
            )
            if playable and not linked:
                issues.append(
                    self._issue(
                        self.MISSING,
                        "fixture_to_operational_match",
                        fixture,
                        "Resolved playable fixture has no operational match.",
                        repairable=True,
                    )
                )
            elif len(linked) > 1 or (
                fixture.operational_match_id
                and linked
                and fixture.operational_match_id not in linked
            ):
                issues.append(
                    self._issue(
                        self.CONFLICTING,
                        "fixture_to_operational_match",
                        fixture,
                        "Logical fixture has conflicting operational match links.",
                    )
                )

        match_domain = (
            [("tournament_id.edition_id", "=", edition.id)] if edition else []
        )
        matches = self.env["federation.match"].sudo().search(match_domain)
        Sheet = self.env["federation.match.sheet"].sudo()
        for match in matches.filtered(
            lambda item: item.home_team_id and item.away_team_id
        ):
            sheets = Sheet.search([("match_id", "=", match.id)])
            expected_teams = {match.home_team_id.id, match.away_team_id.id}
            actual_teams = set(sheets.mapped("team_id").ids)
            if expected_teams - actual_teams:
                issues.append(
                    self._issue(
                        self.MISSING,
                        "operational_match_to_match_sheets",
                        match,
                        "Operational match is missing a team match sheet.",
                        repairable=True,
                    )
                )
            duplicates = any(
                len(sheets.filtered(lambda sheet, team=team: sheet.team_id == team)) > 1
                for team in (match.home_team_id, match.away_team_id)
            )
            if duplicates:
                issues.append(
                    self._issue(
                        self.CONFLICTING,
                        "operational_match_to_match_sheets",
                        match,
                        "Operational match has duplicate team match sheets.",
                    )
                )
            if match.schedule_publication_id and (
                not match.published_slot_id
                or not match.date_scheduled
                or not getattr(match, "venue_id", False)
                or not getattr(match, "playing_area_id", False)
            ):
                issues.append(
                    self._issue(
                        self.MISSING,
                        "published_schedule_to_match",
                        match,
                        "Published match is missing its slot, kickoff, venue or playing area.",
                    )
                )

        roster_domain = []
        if edition:
            roster_domain = [
                ("competition_id", "=", edition.competition_id.id),
                ("season_id", "=", edition.season_id.id),
            ]
        rosters = self.env["federation.team.roster"].sudo().search(roster_domain)
        active_keys = {}
        for roster in rosters.filtered(lambda item: item.status == "active"):
            key = (
                roster.team_id.id,
                roster.season_id.id,
                roster.competition_id.id or False,
            )
            active_keys.setdefault(key, self.env["federation.team.roster"])
            active_keys[key] |= roster
        for group in active_keys.values():
            if len(group) > 1:
                issues.append(
                    self._issue(
                        self.CONFLICTING,
                        "team_to_primary_roster",
                        group[0],
                        "Team has multiple active rosters in the same season and competition scope.",
                    )
                )

        return {"healthy": not issues, "issues": issues}

    @api.model
    def repair(self, issue):
        """Perform only explicitly safe materialization repairs."""
        relation = issue.get("relation")
        source = self.env[issue["source_model"]].browse(issue["source_id"]).exists()
        if not source or not issue.get("repairable"):
            return False
        if relation == "participant_set_to_tournament_participant":
            window = source.window_id
            window._sync_tournament_participants(source)
            return True
        if relation == "fixture_to_operational_match":
            source.action_materialize_match()
            return True
        if relation == "operational_match_to_match_sheets":
            source._create_auto_match_sheets()
            return True
        return False
