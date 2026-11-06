"""Single owner of operation-task projection and synchronization."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .. import task_policy


class FederationTaskProjection(models.AbstractModel):
    _name = "federation.task.projection"
    _description = "Federation Task Projection"

    @api.model
    def synchronize(self, user=None):
        """Collect every domain first, then apply one complete projection.

        Review handoffs change the audience of the existing line-up key. They
        are specifications, not a second mutation pass after synchronization.
        """
        user = user or self.env.user
        task_model = self.env["federation.operation.task"]
        specs, scope_domain = task_model._project_task_specs(user=user)
        scope = self.env["federation.portal.archive.scope"]
        hidden_rosters = set(scope.hidden_roster_ids())
        hidden_registrations = set(scope.hidden_registration_ids())
        specs = [
            spec for spec in specs
            if not (
                (spec.get("source_model") == "federation.team.roster"
                 and spec.get("source_record_id") in hidden_rosters)
                or spec.get("roster_id") in hidden_rosters
                or (spec.get("source_model") == "federation.season.registration"
                    and spec.get("source_record_id") in hidden_registrations)
            )
        ]
        self._apply(specs, scope_domain)
        return task_model.sudo().search(
            task_model._portal_get_domain(user) + [("state", "!=", "done")]
        )

    @api.model
    def _apply(self, specs, scope_domain):
        """Only synchronization writer; validate the entire set before mutation."""
        by_spec = {}
        for spec in specs:
            errors = task_policy.validate_spec(spec)
            if errors:
                raise ValidationError(
                    _("Invalid task projection %(key)s: %(errors)s")
                    % {"key": spec.get("source_key", "?"), "errors": ", ".join(errors)}
                )
            key = spec["source_key"]
            if key in by_spec and by_spec[key] != spec:
                raise ValidationError(
                    _("Conflicting task projections for %(key)s") % {"key": key}
                )
            by_spec[key] = spec
        Task = self.env["federation.operation.task"].sudo()
        wanted = set(by_spec)
        existing = Task.search(scope_domain)
        by_key = {
            task.source_key: task
            for task in Task.search([("source_key", "in", list(wanted))])
        }
        for key, values in by_spec.items():
            task = by_key.get(key)
            if not task:
                Task.create(values)
                continue
            changes = dict(values)
            if task.state == "done":
                changes.update(state="open", completed_on=False, digest_sent_on=False)
            task.write(changes)
        stale = existing.filtered(
            lambda task: task.source_key not in wanted and task.state != "done"
        )
        if stale:
            stale.write({"state": "done", "completed_on": fields.Datetime.now()})
        return True
