"""Single owner of operation-task projection and synchronization."""

from odoo import api, fields, models

from .. import task_policy


class FederationTaskProjection(models.AbstractModel):
    _name = "federation.task.projection"
    _description = "Federation Task Projection"

    @api.model
    def providers(self):
        return (
            "_provide_existing_domain_tasks",
            "_provide_review_handoffs",
        )

    @api.model
    def synchronize(self, user=None):
        """Synchronize actionable work once, then return the visible open tasks.

        Existing domain projections remain the source of task specifications;
        this service is now their single writer/entry point. Review hand-offs
        deliberately replace club work instead of creating status tasks.
        """
        user = user or self.env.user
        task_model = self.env["federation.operation.task"]
        specs, scope_domain = self.env["federation.operation.task"]._project_task_specs(
            user=user
        )
        specs = [spec for spec in specs if not task_policy.validate_spec(spec)]
        scope = self.env["federation.portal.archive.scope"]
        hidden_rosters = set(scope.hidden_roster_ids())
        hidden_registrations = set(scope.hidden_registration_ids())
        specs = [
            spec
            for spec in specs
            if not (
                (
                    spec.get("source_model") == "federation.team.roster"
                    and spec.get("source_record_id") in hidden_rosters
                )
                or spec.get("roster_id") in hidden_rosters
                or (
                    spec.get("source_model") == "federation.season.registration"
                    and spec.get("source_record_id") in hidden_registrations
                )
            )
        ]
        self._apply(specs, scope_domain)
        self._sync_review_handoffs(user)
        return task_model.sudo().search(
            task_model._portal_get_domain(user) + [("state", "!=", "done")]
        )

    @api.model
    def _apply(self, specs, scope_domain):
        """Only writer of stored task projections."""
        Task = self.env["federation.operation.task"].sudo()
        wanted = {spec["source_key"] for spec in specs}
        existing = Task.search(scope_domain)
        by_key = {
            task.source_key: task
            for task in Task.search([("source_key", "in", list(wanted))])
        }
        for values in specs:
            task = by_key.get(values["source_key"])
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

    @api.model
    def _provide_existing_domain_tasks(self, user=None):
        """Compatibility/provider marker: specs are produced by owning domains."""
        return True

    @api.model
    def _provide_review_handoffs(self, user=None):
        """Review work is explicit; approved/complete records create no task."""
        return True

    @api.model
    def _sync_review_handoffs(self, user):
        """Move submitted line-ups to reviewer work; close approved line-up work."""
        Task = self.env["federation.operation.task"].sudo()
        sheets = (
            self.env["federation.match.sheet"]
            .sudo()
            .search([("state", "in", ("submitted", "approved", "locked"))])
        )
        for sheet in sheets:
            source_key = "gameday-lineup:%s:%s" % (
                sheet.team_id.id,
                repr(sheet._get_gameday_scope() or ("sheet", sheet.id)),
            )
            current = Task.search([("source_key", "=", source_key)], limit=1)
            if sheet.state in ("approved", "locked"):
                if current and current.state != "done":
                    current.write(
                        {"state": "done", "completed_on": fields.Datetime.now()}
                    )
                continue
            if not current:
                continue
            current.write(
                {
                    "task_type": "lineup_review",
                    "audience": "manager",
                    "name": "Review game-day line-up: %s" % sheet.team_id.display_name,
                    "blocking_reason": "The game-day line-up was submitted and needs approval.",
                    "next_step": "Approve or return the line-up",
                    "source_model": sheet._name,
                    "source_record_id": sheet.id,
                }
            )
