from odoo import api, fields, models

from ..duty_fairness import rebalance_quadratic


class FederationClubOfficiatingCapacityFairness(models.Model):
    _inherit = "federation.club.officiating.capacity"

    season_target_minutes = fields.Integer(
        default=0,
        help="Fair-share duty minutes this club should carry across the season. "
        "Zero disables season targeting for the club.",
    )


class FederationScheduleDutyFairness(models.Model):
    _inherit = "federation.schedule"

    def _club_duty_season_load(self):
        """Season-to-date duty minutes already committed per club (ledger)."""
        self.ensure_one()
        season = self.edition_id.season_id
        duties = self.env["federation.match.club.referee.duty"].search(
            [("match_id.edition_id.season_id", "=", season.id)]
        )
        ledger = {}
        for duty in duties:
            minutes = duty._duty_minutes() if hasattr(duty, "_duty_minutes") else 60
            ledger[duty.club_id.id] = ledger.get(duty.club_id.id, 0) + minutes
        return ledger

    def _club_duty_season_targets(self):
        self.ensure_one()
        rows = self.env["federation.club.officiating.capacity"].search(
            [("season_id", "=", self.edition_id.season_id.id), ("active", "=", True)]
        )
        return {
            r.club_id.id: r.season_target_minutes
            for r in rows
            if r.season_target_minutes
        }

    def _club_duty_fairness_rebalance(self, allocation):
        """Refine an ``allocate`` result toward quadratic season fairness.

        Preserves simultaneous-capacity, role and pin constraints; only applied
        when at least one club defines a non-zero season target.
        """
        self.ensure_one()
        targets = self._club_duty_season_targets()
        if not targets or not allocation.get("rows"):
            return allocation
        capacities = self._club_duty_capacity_policy()
        pins = self._club_duty_pins()
        assignment, report = rebalance_quadratic(
            allocation["rows"],
            capacities=capacities,
            pins=pins,
            season_minutes=self._club_duty_season_load(),
            targets=targets,
        )
        by_fixture = {row["fixture"]: row for row in allocation["rows"]}
        for fixture, club in assignment.items():
            by_fixture[fixture]["club"] = club
        allocation["fairness"] = report
        return allocation
