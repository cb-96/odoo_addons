from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationMatchReferee(models.Model):
    _inherit = "federation.match.referee"

    match_kickoff = fields.Datetime(
        related="match_id.date_scheduled",
        string="Match Kickoff",
        store=True,
        index=True,
        readonly=True,
    )
    is_current_publication = fields.Boolean(
        compute="_compute_is_current_publication",
        search="_search_is_current_publication",
    )
    response_note = fields.Text(
        string="Official Response",
        help="Optional acknowledgement or decline note provided by the assigned official.",
    )

    def _compute_is_current_publication(self):
        for assignment in self:
            publication = assignment.publication_id
            assignment.is_current_publication = bool(
                publication
                and publication.matchday_id.current_publication_id == publication
            )

    @api.model
    def _search_is_current_publication(self, operator, value):
        current = (
            self.env["federation.matchday"]
            .sudo()
            .search([("current_publication_id.state", "=", "live")])
            .mapped("current_publication_id")
        )
        positive = (operator in ("=", "==") and value) or (
            operator == "!=" and not value
        )
        return [("publication_id", "in" if positive else "not in", current.ids)]

    @api.model
    def _portal_get_domain(self, user=None):
        """Handle the portal-specific get domain flow."""
        user = user or self.env.user
        return [
            ("referee_id.user_id", "=", user.id),
            ("fixture_id", "!=", False),
            ("publication_id", "!=", False),
        ]

    def _portal_assert_access(self, user=None):
        """Handle the portal-specific assert access flow."""
        user = user or self.env.user
        domain = self._portal_get_domain(user=user)
        self.env["federation.portal.privilege"].portal_assert_in_domain(
            self,
            domain,
            _("You can only review your own officiating assignments."),
            user=user,
        )
        return True

    def _portal_action_confirm(self, user=None, response_note=None):
        """Handle the portal-specific action confirm flow."""
        user = user or self.env.user
        self._portal_assert_access(user=user)
        invalid = self.filtered(lambda assignment: assignment.state != "draft")
        if invalid:
            raise ValidationError(
                _(
                    "Only newly assigned officiating requests can be confirmed from the portal."
                )
            )
        prepared_note = (response_note or "").strip()
        scope_domain = self._portal_get_domain(user=user)
        if prepared_note:
            self.env["federation.portal.privilege"].portal_write(
                self,
                {"response_note": prepared_note},
                scope_domain=scope_domain,
                user=user,
            )
        return self.env["federation.portal.privilege"].portal_call(
            self,
            "action_confirm",
            scope_domain=scope_domain,
            user=user,
        )

    def _portal_action_decline(self, user=None, response_note=None):
        """Handle the portal-specific action decline flow."""
        user = user or self.env.user
        self._portal_assert_access(user=user)
        invalid = self.filtered(lambda assignment: assignment.state != "draft")
        if invalid:
            raise ValidationError(
                _(
                    "Only newly assigned officiating requests can be declined from the portal."
                )
            )
        prepared_note = (response_note or "").strip()
        if not prepared_note:
            raise ValidationError(
                _("Please provide a short reason before declining the assignment.")
            )
        self.env["federation.portal.privilege"].portal_write(
            self,
            {"response_note": prepared_note},
            scope_domain=self._portal_get_domain(user=user),
            user=user,
        )
        return self.env["federation.portal.privilege"].portal_call(
            self,
            "action_cancel",
            scope_domain=self._portal_get_domain(user=user),
            user=user,
        )
