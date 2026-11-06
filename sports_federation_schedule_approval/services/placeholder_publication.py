from odoo import models


class FederationFixtureMaterializerPublication(models.AbstractModel):
    """Matches created for scheduled placeholders join the live publication.

    A placeholder fixture ("Winner R1 M2") can be published before its teams
    are known. When the deciding result is approved the format engine creates
    its match; this hook puts that match into the slot that was published.
    """

    _inherit = "federation.fixture.materializer"

    def materialize(self, fixtures):
        matches = super().materialize(fixtures)
        self.env["federation.schedule.approval.commands"].link_placeholder_matches(
            matches
        )
        return matches
