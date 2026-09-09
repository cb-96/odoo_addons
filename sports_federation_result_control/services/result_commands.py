"""Explicit command boundary for privileged result mutations."""

from odoo import _, api, models
from odoo.exceptions import AccessError, ValidationError

_RESULT_COMMAND_TOKEN = object()
_RESULT_COMMAND_CONTEXT_KEY = "result_command_token"


def is_result_command_context(env):
    """Return whether *env* was elevated by this module's command service."""
    return env.context.get(_RESULT_COMMAND_CONTEXT_KEY) is _RESULT_COMMAND_TOKEN


class FederationResultCommands(models.AbstractModel):
    _name = "federation.result.commands"
    _description = "Federation Result Commands"

    @api.model
    def _portal_scope_domain(self, actor):
        if "portal_club_scope_ids" not in actor._fields:
            raise AccessError(
                _("Portal result commands require an explicit club scope.")
            )
        club_ids = actor.portal_club_scope_ids.ids
        if not club_ids:
            return [("id", "=", False)]
        return [
            "|",
            ("home_team_id.club_id", "in", club_ids),
            ("away_team_id.club_id", "in", club_ids),
        ]

    @api.model
    def _authorized_match(self, match_id, actor):
        actor = actor.exists()[:1]
        if not actor or actor._name != "res.users":
            raise AccessError(_("A valid portal actor is required."))
        domain = [("id", "=", int(match_id))] + self._portal_scope_domain(actor)
        match = (
            self.env["federation.match"].with_user(actor).sudo().search(domain, limit=1)
        )
        if not match:
            raise AccessError(_("You do not have access to this match result."))
        return match

    @api.model
    def _command_match(self, match, actor):
        return (
            match.with_user(actor)
            .sudo()
            .with_context(**{_RESULT_COMMAND_CONTEXT_KEY: _RESULT_COMMAND_TOKEN})
        )

    @api.model
    def approve_portal_result(self, match_id, actor):
        """Approve one verified result inside the actor's current club scope."""
        with self.env.cr.savepoint():
            match = self._authorized_match(match_id, actor)
            if match.result_state != "verified":
                raise ValidationError(_("Only verified results can be approved."))
            command_match = self._command_match(match, actor)
            return command_match.action_approve_result()

    @api.model
    def contest_portal_result(self, match_id, reason, actor):
        """Contest one visible result with an audited, scoped command."""
        with self.env.cr.savepoint():
            reason = (reason or "").strip()
            if not reason:
                raise ValidationError(_("A contest reason is required."))
            match = self._authorized_match(match_id, actor)
            if match.result_state not in ("submitted", "verified", "approved"):
                raise ValidationError(
                    _(
                        "Only submitted, verified, or approved results can be "
                        "contested."
                    )
                )
            command_match = self._command_match(match, actor)
            command_match.write({"result_contest_reason": reason})
            return command_match.action_contest_result()
