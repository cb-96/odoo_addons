from math import ceil, log2

from odoo import _, api, models


class FederationFormatFeasibility(models.AbstractModel):
    _name = "federation.format.feasibility"
    _description = "Competition Format Feasibility"

    @api.model
    def estimate(self, format_type, participant_count, *, pool_count=1, series_length=1):
        participant_count = int(participant_count or 0)
        pool_count = max(1, int(pool_count or 1))
        series_length = max(1, int(series_length or 1))
        if participant_count < 2:
            return {"feasible": False, "fixture_count": 0, "round_count": 0, "message": _("At least two participants are required.")}
        if format_type == "single_round_robin":
            fixtures = participant_count * (participant_count - 1) // 2
            rounds = participant_count if participant_count % 2 else participant_count - 1
        elif format_type == "double_round_robin":
            fixtures = participant_count * (participant_count - 1)
            rounds = 2 * (participant_count if participant_count % 2 else participant_count - 1)
        elif format_type in ("knockout", "placement_bracket"):
            fixtures = (participant_count - 1) * series_length
            rounds = ceil(log2(participant_count)) * series_length
        elif format_type == "pool_knockout":
            if pool_count > participant_count // 2:
                return {"feasible": False, "fixture_count": 0, "round_count": 0, "message": _("Every pool must contain at least two participants.")}
            sizes = [participant_count // pool_count] * pool_count
            for index in range(participant_count % pool_count):
                sizes[index] += 1
            fixtures = sum(size * (size - 1) // 2 for size in sizes) + min(participant_count, 2 * pool_count) - 1
            rounds = max(size if size % 2 else size - 1 for size in sizes) + ceil(log2(min(participant_count, 2 * pool_count)))
        elif format_type == "split_pools":
            if participant_count < 6:
                return {"feasible": False, "fixture_count": 0, "round_count": 0, "message": _("Split-pool competitions require at least six participants.")}
            upper = ceil(participant_count / 2); lower = participant_count - upper
            fixtures = participant_count * (participant_count - 1) // 2 + upper * (upper - 1) // 2 + lower * (lower - 1) // 2
            rounds = participant_count - 1 + max(upper - 1, lower - 1)
        else:
            return {"feasible": False, "fixture_count": 0, "round_count": 0, "message": _("This format is configured manually and cannot be estimated automatically.")}
        return {"feasible": True, "fixture_count": fixtures, "round_count": rounds, "message": _("The format can be generated for %(teams)s participants.", teams=participant_count)}
