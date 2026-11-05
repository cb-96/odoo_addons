from odoo import _, api, models
from odoo.addons.sports_federation_base import readiness_vocabulary as vocabulary


class FederationMatchdayReadinessCoverage(models.AbstractModel):
    """Acceptance-aware officials component of the game-day readiness.

    Duty coverage knows that an assignment is not acceptance and that
    acceptance is not eligibility, so it replaces the basic officiating
    provider. The component key and the shared vocabulary stay the same.
    """

    _inherit = "federation.matchday.readiness"

    @api.model
    def _coverage_owner(self, matches):
        owners = matches.mapped("coverage_owner_id")
        if not owners:
            return None
        if len(owners) == 1 and all(match.coverage_owner_id for match in matches):
            return owners.display_name
        return _("Duty coordinators")

    @api.model
    def _readiness_officials(self, scope):
        snapshots = {
            match.id: match._coverage_snapshot() for match in scope["matches"]
        }
        matches = scope["matches"].filtered(
            lambda match: snapshots[match.id]["state"] != "not_required"
        )
        if not matches:
            return self._ready_component(
                "officials", _("No officials required"), vocabulary.NOT_APPLICABLE
            )
        required = sum(snapshots[match.id]["required"] for match in matches)
        open_positions = sum(
            sum(snapshots[match.id]["ready_missing"].values()) for match in matches
        )
        unconfirmed = matches.filtered(
            lambda match: snapshots[match.id]["state"] == "unchecked"
        )
        uncovered = matches.filtered(
            lambda match: sum(snapshots[match.id]["missing"].values())
        )
        awaiting = matches.filtered(
            lambda match: snapshots[match.id]["state"] == "needs_action"
            and sum(snapshots[match.id]["ready_missing"].values())
            > sum(snapshots[match.id]["missing"].values())
        )
        nominations = matches.filtered(
            lambda match: snapshots[match.id]["state"] == "needs_action"
            and match not in uncovered
            and match not in awaiting
        )
        blockers = []
        if unconfirmed:
            blockers.append(
                vocabulary.make_blocker(
                    key="officials-unconfirmed",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        len(unconfirmed),
                        _("%(count)s match has unconfirmed duty requirements."),
                        _("%(count)s matches have unconfirmed duty requirements."),
                    ),
                    action=_("Configure the duty requirements of the match."),
                    destination=self._records_destination(unconfirmed),
                    owner=self._coverage_owner(unconfirmed),
                    deadline=self._iso(
                        self._earliest(
                            unconfirmed.mapped("coverage_nomination_deadline")
                        )
                    ),
                    count=len(unconfirmed),
                    details=self._details(unconfirmed.mapped("display_name")),
                )
            )
        if uncovered:
            positions = sum(
                sum(snapshots[match.id]["missing"].values()) for match in uncovered
            )
            blockers.append(
                vocabulary.make_blocker(
                    key="officials-uncovered",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        positions,
                        _("%(count)s referee position still needs coverage."),
                        _("%(count)s referee positions still need coverage."),
                    ),
                    action=_("Assign or request an official for each open position."),
                    destination=self._records_destination(uncovered),
                    owner=self._coverage_owner(uncovered),
                    deadline=self._iso(
                        self._earliest(uncovered.mapped("coverage_nomination_deadline"))
                    ),
                    count=positions,
                    details=self._details(uncovered.mapped("display_name")),
                )
            )
        if awaiting:
            positions = sum(
                sum(snapshots[match.id]["ready_missing"].values())
                - sum(snapshots[match.id]["missing"].values())
                for match in awaiting
            )
            blockers.append(
                vocabulary.make_blocker(
                    key="officials-awaiting",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        positions,
                        _(
                            "%(count)s assigned official still has to accept the "
                            "duty or become eligible."
                        ),
                        _(
                            "%(count)s assigned officials still have to accept the "
                            "duty or become eligible."
                        ),
                    ),
                    action=_("Ask the official to respond or resolve the eligibility."),
                    destination=self._records_destination(awaiting),
                    owner=self._coverage_owner(awaiting),
                    deadline=self._iso(
                        self._earliest(awaiting.mapped("coverage_response_deadline"))
                    ),
                    count=positions,
                    details=self._details(awaiting.mapped("display_name")),
                )
            )
        if nominations:
            blockers.append(
                vocabulary.make_blocker(
                    key="officials-nominations",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        len(nominations),
                        _("%(count)s match has an unsettled club nomination."),
                        _("%(count)s matches have unsettled club nominations."),
                    ),
                    action=_("Link, reopen or replace the club nomination."),
                    destination=self._records_destination(nominations),
                    owner=self._coverage_owner(nominations),
                    deadline=self._iso(
                        self._earliest(nominations.mapped("coverage_response_deadline"))
                    ),
                    count=len(nominations),
                    details=self._details(nominations.mapped("display_name")),
                )
            )
        return self._counter_component(
            "officials", required - open_positions, required, blockers
        )
