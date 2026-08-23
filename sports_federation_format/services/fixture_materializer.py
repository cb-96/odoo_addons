from odoo import api, models
from odoo.exceptions import ValidationError


class FederationFixtureMaterializer(models.AbstractModel):
    _name = "federation.fixture.materializer"
    _description = "Logical Fixture to Operational Match Materializer"

    @api.model
    def materialize(self, fixtures):
        fixtures = fixtures.exists()
        matches = self.env["federation.match"]
        for fixture in fixtures.sorted("id"):
            self.env.cr.execute(
                "SELECT id FROM federation_fixture WHERE id = %s FOR UPDATE",
                [fixture.id],
            )
            fixture.invalidate_recordset(["operational_match_id"])
            if fixture.operational_match_id:
                matches |= fixture.operational_match_id
                continue
            if fixture.state == "cancelled":
                raise ValidationError("Cancelled fixtures cannot be materialized.")
            if fixture.bye_team_id:
                raise ValidationError(
                    "A structural bye does not create an operational match."
                )
            if not fixture.home_team_id or not fixture.away_team_id:
                raise ValidationError(
                    "Resolve both fixture participants before materializing an operational match."
                )
            existing = self.env["federation.match"].search(
                [("logical_fixture_id", "=", fixture.id)], limit=1
            )
            if existing:
                fixture.operational_match_id = existing
                matches |= existing
                continue
            match = self.env["federation.match"].create(
                {
                    "tournament_id": fixture.division_id.id,
                    "home_team_id": fixture.home_team_id.id,
                    "away_team_id": fixture.away_team_id.id,
                    "round_number": fixture.round_number,
                    "state": "draft",
                    "logical_fixture_id": fixture.id,
                }
            )
            fixture.operational_match_id = match
            matches |= match
        return matches
