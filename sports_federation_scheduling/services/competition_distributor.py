from collections import defaultdict

from odoo import models
from odoo.exceptions import ValidationError


class FederationCompetitionScheduleDistributor(models.AbstractModel):
    _name = "federation.competition.schedule.distributor"
    _description = "Competition Fixture to Match-Day Distributor"

    def distribute(self, fixtures, capacities):
        days = sorted(capacities, key=lambda item: (item["date"], item["matchday_id"]))
        remaining = {item["matchday_id"]: item["capacity"] for item in days}
        team_days = defaultdict(set)
        assignments = defaultdict(list)
        fixtures = fixtures.sorted(
            key=lambda fixture: (fixture.round_number, fixture.sequence, fixture.id)
        )
        for fixture in fixtures:
            team_ids = {fixture.home_team_id.id, fixture.away_team_id.id} - {False}
            candidates = [day for day in days if remaining[day["matchday_id"]] > 0]
            if not candidates:
                raise ValidationError(
                    "The selected game days do not provide enough playable slots."
                )
            candidates.sort(
                key=lambda day: (
                    bool(team_ids & team_days[day["matchday_id"]]),
                    -remaining[day["matchday_id"]],
                    day["date"],
                    day["matchday_id"],
                )
            )
            day_id = candidates[0]["matchday_id"]
            assignments[day_id].append(fixture.id)
            remaining[day_id] -= 1
            team_days[day_id].update(team_ids)
        return {"assignments": dict(assignments), "remaining_capacity": remaining}
