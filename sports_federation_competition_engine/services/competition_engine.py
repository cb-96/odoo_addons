import logging
from odoo import models

_logger = logging.getLogger(__name__)


class CompetitionEngineService(models.AbstractModel):
    _name = "federation.competition.engine.service"
    _description = "Competition Engine Service"

    def generate_round_robin_schedule(self, tournament, stage, participants, options):
        """Delegate to round-robin service."""
        service = self.env["federation.round.robin.service"]
        return service.generate(tournament, stage, participants, options)

    def generate_knockout_bracket(self, tournament, stage, participants, options):
        """Delegate to knockout service."""
        service = self.env["federation.knockout.service"]
        return service.generate(tournament, stage, participants, options)

    def generate_standings(self, tournament, stage=None, group=None):
        """
        Compute standings - extension point for future implementation.
        """
        _logger.info(
            "Standings called for tournament %s (stage: %s, group: %s)",
            tournament.name if tournament else "N/A",
            stage.name if stage else "N/A",
            group.name if group else "N/A",
        )

        Standing = self.env["federation.standing"]

        # Build a deterministic name for automated standings so we can
        # find or reuse an existing record for the same tournament/stage/group.
        name_parts = []
        if tournament:
            name_parts.append(tournament.name)
        if stage:
            name_parts.append(stage.name)
        if group:
            name_parts.append(group.name)
        if not name_parts:
            name = "Auto: Standings"
        else:
            name = "Auto: " + " / ".join(name_parts)

        # Search for existing standing for the same tournament/stage/group
        domain = [
            ("tournament_id", "=", tournament.id if tournament else False),
            ("name", "=", name),
        ]
        if stage:
            domain.append(("stage_id", "=", stage.id))
        else:
            domain.append(("stage_id", "=", False))
        if group:
            domain.append(("group_id", "=", group.id))
        else:
            domain.append(("group_id", "=", False))

        standing = Standing.search(domain, limit=1)

        if not standing:
            vals = {
                "name": name,
                "tournament_id": tournament.id if tournament else False,
            }
            if stage:
                vals["stage_id"] = stage.id
            if group:
                vals["group_id"] = group.id
            standing = Standing.create(vals)

        # Recompute the standing. Respect a `force_recompute` flag in context
        # to allow overriding frozen state from callers.
        if self.env.context.get("force_recompute"):
            standing.with_context(force_recompute=True).action_recompute()
        else:
            standing.action_recompute()

        return standing
