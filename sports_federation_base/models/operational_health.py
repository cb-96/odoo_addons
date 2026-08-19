import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class FederationOperationalHealth(models.AbstractModel):
    _name = "federation.operational.health"
    _description = "Federation Operational Health"

    @api.model
    def snapshot(self):
        """Return a sanitized readiness snapshot without record payloads or secrets."""
        checks = []

        def add(code, ok, message, metric=None):
            checks.append(
                {
                    "code": code,
                    "ok": bool(ok),
                    "message": message,
                    "metric": metric,
                }
            )

        self.env.cr.execute("SELECT 1")
        add(
            "database",
            self.env.cr.fetchone()[0] == 1,
            _("Database connection is ready."),
        )

        required_models = (
            "federation.club",
            "federation.team",
            "federation.tournament",
            "federation.match",
        )
        missing = [name for name in required_models if name not in self.env]
        add(
            "registry",
            not missing,
            (
                _("Required federation models are registered.")
                if not missing
                else _("Required models are missing.")
            ),
            len(missing),
        )

        if "federation.operation.task" in self.env:
            Task = self.env["federation.operation.task"].sudo()
            overdue = Task.search_count(
                [
                    ("state", "!=", "done"),
                    ("deadline", "<", fields.Datetime.now()),
                ]
            )
            add(
                "overdue_actions",
                True,
                _("Open overdue actions were counted."),
                overdue,
            )

        if "federation.competition.integrity.service" in self.env:
            results = self.env[
                "federation.competition.integrity.service"
            ].scan_active_divisions()
            blocking = sum(1 for result in results if not result["valid"])
            add(
                "competition_integrity",
                blocking == 0,
                _("Active competition integrity was checked."),
                blocking,
            )

        ready = all(check["ok"] for check in checks)
        return {
            "ready": ready,
            "checked_on": fields.Datetime.now(),
            "checks": checks,
        }

    @api.model
    def log_snapshot(self):
        result = self.snapshot()
        logger = _logger.info if result["ready"] else _logger.error
        logger(
            "federation_health ready=%s checks=%s",
            result["ready"],
            [(item["code"], item["ok"], item["metric"]) for item in result["checks"]],
        )
        return result
