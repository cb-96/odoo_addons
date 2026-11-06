from odoo import _, api, models
from odoo.addons.sports_federation_base import readiness_vocabulary as vocabulary


class FederationMatchdayReadinessCompliance(models.AbstractModel):
    """Compliance of the clubs and the venue taking part in a game day."""

    _inherit = "federation.matchday.readiness"

    @api.model
    def _readiness_providers(self):
        providers = super()._readiness_providers()
        providers.append(("compliance", "_readiness_compliance"))
        return providers

    @api.model
    def _readiness_compliance(self, scope):
        day = scope["matchday"]
        clubs = scope["teams"].mapped("club_id")
        domain = []
        if clubs and day.venue_id:
            domain = [
                "|",
                ("club_id", "in", clubs.ids),
                ("venue_id", "=", day.venue_id.id),
            ]
        elif clubs:
            domain = [("club_id", "in", clubs.ids)]
        elif day.venue_id:
            domain = [("venue_id", "=", day.venue_id.id)]
        checks = (
            self.env["federation.compliance.check"].sudo().search(domain)
            if domain
            else self.env["federation.compliance.check"]
        )
        if not checks:
            return self._ready_component(
                "compliance",
                _("No compliance requirements apply"),
                vocabulary.NOT_APPLICABLE,
            )
        grouped = {
            status: checks.filtered(
                lambda check, status=status: vocabulary.status_for(
                    "compliance", check.status
                )
                == status
            )
            for status in (
                vocabulary.BLOCKED,
                vocabulary.ACTION_NEEDED,
                vocabulary.WAITING_REVIEW,
            )
        }
        deadline = self._iso(scope["first_kickoff"] or day.date)
        blockers = []
        texts = {
            vocabulary.BLOCKED: (
                _("%(count)s compliance requirement is not met."),
                _("%(count)s compliance requirements are not met."),
                _("Resolve the failed requirement or ask for a governed override."),
                _("Compliance officer"),
            ),
            vocabulary.ACTION_NEEDED: (
                _("%(count)s compliance document is missing or expired."),
                _("%(count)s compliance documents are missing or expired."),
                _("Upload a current document."),
                None,
            ),
            vocabulary.WAITING_REVIEW: (
                _("%(count)s compliance document is waiting for review."),
                _("%(count)s compliance documents are waiting for review."),
                _("Review and decide on the submitted document."),
                _("Compliance officer"),
            ),
        }
        for status, records in grouped.items():
            if not records:
                continue
            singular, plural, action, owner = texts[status]
            if owner is None:
                owner = self._compliance_owner(records)
            blockers.append(
                vocabulary.make_blocker(
                    key="compliance-%s" % status,
                    status=status,
                    problem=self._count_text(len(records), singular, plural),
                    action=action,
                    destination=self._records_destination(records),
                    owner=owner,
                    deadline=deadline,
                    count=len(records),
                    details=self._details(
                        "%s: %s"
                        % (
                            check.target_display or check.name,
                            check.requirement_id.display_name,
                        )
                        for check in records
                    ),
                )
            )
        total = len(checks)
        ready = total - sum(len(records) for records in grouped.values())
        return self._counter_component("compliance", ready, total, blockers)

    @api.model
    def _compliance_owner(self, checks):
        clubs = checks.mapped("club_id")
        if len(clubs) == 1:
            return _("Club representative: %(club)s") % {"club": clubs.display_name}
        if clubs:
            return _("Club representatives")
        return _("Venue manager") if checks.mapped("venue_id") else None
