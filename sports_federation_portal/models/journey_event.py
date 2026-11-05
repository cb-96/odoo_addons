import logging
from datetime import timedelta

from odoo import api, fields, models

from .. import journey_instrumentation as instrumentation

_logger = logging.getLogger(__name__)
RETENTION_PARAMETER = "federation.journey_event_retention_days"
DEFAULT_RETENTION_DAYS = 180


def current_session():
    """The current web session id, or ``None`` outside an HTTP request."""
    try:
        from odoo.http import request

        return request.session.sid if request and request.session else None
    except RuntimeError:
        return None


class FederationJourneyEvent(models.Model):
    """One anonymised instrumentation event. Never holds names or record data."""

    _name = "federation.journey.event"
    _description = "Portal Journey Instrumentation Event"
    _order = "id desc"

    journey = fields.Char(required=True, index=True)
    event = fields.Selection(
        [
            ("entry", "Entered"),
            ("action", "Action taken"),
            ("validation_error", "Validation error"),
            ("retry", "Retry"),
        ],
        required=True,
        index=True,
    )
    screen = fields.Char()
    session_key = fields.Char(index=True)
    user_id = fields.Many2one("res.users", ondelete="set null", index=True)
    occurred_on = fields.Datetime(default=fields.Datetime.now, required=True, index=True)

    # ------------------------------------------------------------------
    # Recording: instrumentation must never break a request
    # ------------------------------------------------------------------

    @api.model
    def record(self, journey, event, screen=None, session=None, dedupe_seconds=0, user=None):
        """Record one event; returns the event id, or ``False`` when skipped."""
        if event not in instrumentation.EVENTS:
            return False
        user = user or self.env.user
        if user._is_public():
            return False
        key = instrumentation.session_key(session) if session else False
        try:
            with self.env.cr.savepoint():
                events = self.sudo()
                if dedupe_seconds and key:
                    since = fields.Datetime.now() - timedelta(seconds=dedupe_seconds)
                    if events.search_count(
                        [
                            ("journey", "=", journey),
                            ("event", "=", event),
                            ("session_key", "=", key),
                            ("occurred_on", ">=", since),
                        ]
                    ):
                        return False
                return events.create(
                    {
                        "journey": journey[:120],
                        "event": event,
                        "screen": (screen or False) and screen[:60],
                        "session_key": key,
                        "user_id": user.id,
                    }
                ).id
        except Exception:  # pylint: disable=broad-except
            _logger.warning("Journey event %s/%s was not recorded", journey, event, exc_info=True)
            return False

    @api.model
    def record_attempt(self, journey, session=None):
        """Record a retry when this user just failed the same command."""
        user = self.env.user
        if user._is_public():
            return False
        since = fields.Datetime.now() - instrumentation.RETRY_WINDOW
        try:
            with self.env.cr.savepoint():
                failed = self.sudo().search_count(
                    [
                        ("journey", "=", journey),
                        ("event", "=", "validation_error"),
                        ("user_id", "=", user.id),
                        ("occurred_on", ">=", since),
                    ]
                )
        except Exception:  # pylint: disable=broad-except
            _logger.warning("Journey retry check failed for %s", journey, exc_info=True)
            return False
        if failed:
            return self.record(journey, "retry", session=session)
        return False

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @api.model
    def _task_closure(self, since, now):
        """Per task type: created, closed and overdue-open, straight from the tasks."""
        Task = self.env["federation.operation.task"].sudo()
        labels = dict(Task._fields["task_type"]._description_selection(self.env))
        result = {}
        for task_type, label in labels.items():
            created = Task.search_count(
                [("task_type", "=", task_type), ("create_date", ">=", since)]
            )
            closed = Task.search_count(
                [("task_type", "=", task_type), ("state", "=", "done"), ("completed_on", ">=", since)]
            )
            overdue = Task.search_count(
                [("task_type", "=", task_type), ("state", "!=", "done"), ("deadline", "<", now)]
            )
            result[task_type] = {
                "label": label,
                "created": created,
                "closed": closed,
                "open_overdue": overdue,
            }
        return result

    @api.model
    def report(self, days=30, grace_minutes=instrumentation.DEFAULT_GRACE_MINUTES, limit=100000):
        """Instrumentation summary for the last ``days`` days."""
        now = fields.Datetime.now()
        since = now - timedelta(days=days)
        rows = self.sudo().search_read(
            [("occurred_on", ">=", since)],
            ["journey", "event", "screen", "session_key", "occurred_on"],
            order="id asc",
            limit=limit,
        )
        result = instrumentation.summarize(rows, now, grace_minutes)
        result["truncated"] = len(rows) >= limit
        result["task_closure"] = self._task_closure(since, now)
        return result

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    @api.model
    def _retention_days(self):
        value = self.env["ir.config_parameter"].sudo().get_param(RETENTION_PARAMETER)
        try:
            days = int(value)
        except (TypeError, ValueError):
            return DEFAULT_RETENTION_DAYS
        return days if days > 0 else DEFAULT_RETENTION_DAYS

    @api.model
    def _cron_prune(self, batch=5000):
        """Delete events older than the retention period."""
        cutoff = fields.Datetime.now() - timedelta(days=self._retention_days())
        old = self.sudo().search([("occurred_on", "<", cutoff)], limit=batch)
        count = len(old)
        old.unlink()
        return count
