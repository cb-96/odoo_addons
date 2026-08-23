from collections import defaultdict

from odoo import models


class PublicFormatQueries(models.AbstractModel):
    _name = "federation.public.format.queries"
    _description = "Public Competition Format Queries"

    def structures(self, edition, division=False):
        domain = [("edition_id", "=", edition.id), ("state", "=", "frozen")]
        if division:
            domain.append(("division_id", "=", division.id))
        structures = (
            self.env["federation.competition.structure"]
            .sudo()
            .search(domain, order="division_id,version desc,id desc")
        )
        latest = {}
        for structure in structures:
            latest.setdefault(structure.division_id.id, structure)
        return self.env["federation.competition.structure"].browse(
            [s.id for s in latest.values()]
        )

    def current_stage(self, edition, division=False):
        stages = (
            self.structures(edition, division)
            .mapped("stage_ids")
            .sorted(lambda s: (s.sequence, s.id))
        )
        return (
            stages.filtered(lambda s: s.graph_state == "active")[:1]
            or stages.filtered(lambda s: s.graph_state in ("ready", "waiting"))[:1]
            or stages[-1:]
        )

    def stage_cards(self, edition, division=False):
        stages = (
            self.structures(edition, division)
            .mapped("stage_ids")
            .sorted(lambda s: (s.sequence, s.id))
        )
        cards = []
        for stage in stages:
            rounds = defaultdict(list)
            for fixture in stage.stage_fixture_ids.sorted(
                lambda f: (f.round_number, f.sequence, f.id)
            ):
                rounds[fixture.round_number].append(fixture)
            cards.append(
                {
                    "stage": stage,
                    "standings": (
                        stage.standing_snapshot_id.line_ids
                        if stage.standing_snapshot_id
                        else self.env["federation.stage.standing.line"].browse([])
                    ),
                    "rounds": list(rounds.items()),
                    "progressions": stage.outgoing_progression_ids.sorted(
                        lambda p: (p.rank_from, p.id)
                    ),
                }
            )
        return cards
