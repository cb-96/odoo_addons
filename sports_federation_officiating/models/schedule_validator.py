from odoo import _, api, models


class FederationScheduleOfficiatingValidator(models.AbstractModel):
    _inherit = "federation.schedule.validator"

    @api.model
    def validate_map(self, schedule, assignment_map):
        """Use the reviewed duty allocator everywhere a schedule is validated."""
        result = super().validate_map(schedule, assignment_map)
        if not schedule.club_duty_policy:
            return result
        proposal = schedule._duty_proposal(schedule.club_duty_policy)
        for detail in proposal.get("issue_details", []):
            result["errors"].append(
                {
                    "code": "club_duty_%s" % detail.get("code", "conflict"),
                    "message": detail.get("message")
                    or _("Club-duty allocation is not feasible."),
                    "fixture_id": detail.get("fixture"),
                    "club_id": detail.get("club"),
                    "resolution": _(
                        "Adjust capacity, qualifications, buffers or the manual pin, then review club duties again."
                    ),
                }
            )
        result["valid"] = not result["errors"] and not result["unassigned_fixture_ids"]
        return result
