from collections import defaultdict

from odoo import models


class FederationCompetitionScheduleDistributor(models.AbstractModel):
    _name = "federation.competition.schedule.distributor"
    _description = "Competition Fixture to Match-Day Distributor"

    def propose(self, fixtures, capacities, pinned=None):
        """Distribute fixtures deterministically using real per-day capacity."""
        pinned = pinned or {}
        days = sorted(capacities, key=lambda item: (item["date"], item["matchday_id"]))
        remaining = {item["matchday_id"]: item["capacity"] for item in days}
        assignments = defaultdict(list)
        team_days = defaultdict(set)
        errors = []
        fixtures_by_id = {fixture.id: fixture for fixture in fixtures}

        for fixture_id, matchday_id in sorted(pinned.items()):
            fixture = fixtures_by_id.get(fixture_id)
            if not fixture or matchday_id not in remaining:
                errors.append("A pinned fixture or game day is outside the selected scope.")
                continue
            if remaining[matchday_id] <= 0:
                errors.append("Pinned fixtures exceed a game day's capacity.")
                continue
            self._assign(fixture, matchday_id, assignments, team_days, remaining)

        unpinned = fixtures.filtered(lambda fixture: fixture.id not in pinned)
        unpinned = unpinned.sorted(
            key=lambda fixture: (fixture.round_number, fixture.sequence, fixture.id)
        )
        for fixture in unpinned:
            team_ids = self._team_ids(fixture)
            candidates = [day for day in days if remaining[day["matchday_id"]] > 0]
            candidates.sort(
                key=lambda day: (
                    len(team_ids & team_days[day["matchday_id"]]),
                    -remaining[day["matchday_id"]],
                    day["date"],
                    day["matchday_id"],
                )
            )
            if not candidates:
                errors.append("No remaining capacity for fixture %s." % fixture.display_name)
                continue
            self._assign(
                fixture,
                candidates[0]["matchday_id"],
                assignments,
                team_days,
                remaining,
            )
        return {
            "assignments": dict(assignments),
            "remaining_capacity": remaining,
            "errors": errors,
            "valid": not errors,
        }

    def distribute(self, fixtures, capacities):
        """Compatibility wrapper for the original competition wizard."""
        proposal = self.propose(fixtures, capacities)
        if proposal["errors"]:
            from odoo.exceptions import ValidationError

            raise ValidationError("\n".join(proposal["errors"]))
        return proposal

    def _assign(self, fixture, day_id, assignments, team_days, remaining):
        assignments[day_id].append(fixture.id)
        remaining[day_id] -= 1
        team_days[day_id].update(self._team_ids(fixture))

    def _team_ids(self, fixture):
        return {fixture.home_team_id.id, fixture.away_team_id.id} - {False}
