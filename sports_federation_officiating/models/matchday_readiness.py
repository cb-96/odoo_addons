from odoo import _, api, models
from odoo.addons.sports_federation_base import readiness_vocabulary as vocabulary


class FederationMatchdayReadinessOfficiating(models.AbstractModel):
    """Referee coverage of a game day.

    Installations with the duty-coverage addon replace this provider with the
    richer acceptance-aware one; the component key stays the same.
    """

    _inherit = "federation.matchday.readiness"

    @api.model
    def _readiness_providers(self):
        providers = super()._readiness_providers()
        providers.append(("officials", "_readiness_officials"))
        return providers

    @api.model
    def _readiness_officials(self, scope):
        matches = scope["matches"].filtered(lambda match: match.required_referee_count)
        if not matches:
            return self._ready_component(
                "officials", _("No officials required"), vocabulary.NOT_APPLICABLE
            )
        required = sum(matches.mapped("required_referee_count"))
        covered = sum(
            min(match.confirmed_referee_count, match.required_referee_count)
            for match in matches
        )
        missing = matches.filtered(lambda match: match.missing_referees_count)
        pending_duties = matches.filtered(lambda match: match.club_duty_pending_count)
        other = matches.filtered(
            lambda match: not match.is_officially_ready
            and match not in missing
            and match not in pending_duties
        )
        deadline = self._iso(scope["first_kickoff"] or scope["matchday"].date)
        blockers = []
        if missing:
            positions = sum(missing.mapped("missing_referees_count"))
            blockers.append(
                vocabulary.make_blocker(
                    key="officials-missing",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        positions,
                        _("%(count)s referee position still needs coverage."),
                        _("%(count)s referee positions still need coverage."),
                    ),
                    action=_("Assign and confirm a referee for each open position."),
                    destination=self._records_destination(missing),
                    owner=_("Officials coordinator"),
                    deadline=deadline,
                    count=positions,
                    details=self._details(missing.mapped("display_name")),
                )
            )
        if pending_duties:
            duties = sum(pending_duties.mapped("club_duty_pending_count"))
            blockers.append(
                vocabulary.make_blocker(
                    key="officials-club-duties",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        duties,
                        _("%(count)s club referee duty is not confirmed yet."),
                        _("%(count)s club referee duties are not confirmed yet."),
                    ),
                    action=_("Ask the club to nominate and confirm a referee."),
                    destination=self._records_destination(pending_duties),
                    owner=_("Officials coordinator"),
                    deadline=deadline,
                    count=duties,
                    details=self._details(pending_duties.mapped("display_name")),
                )
            )
        if other:
            blockers.append(
                vocabulary.make_blocker(
                    key="officials-issues",
                    status=vocabulary.ACTION_NEEDED,
                    problem=self._count_text(
                        len(other),
                        _("%(count)s match has an official readiness issue."),
                        _("%(count)s matches have official readiness issues."),
                    ),
                    action=_("Open the match and resolve its official issues."),
                    destination=self._records_destination(other),
                    owner=_("Officials coordinator"),
                    deadline=deadline,
                    count=len(other),
                    details=self._details(
                        (match.official_readiness_issues or "").splitlines()[0]
                        for match in other
                        if match.official_readiness_issues
                    ),
                )
            )
        return self._counter_component("officials", covered, required, blockers)
