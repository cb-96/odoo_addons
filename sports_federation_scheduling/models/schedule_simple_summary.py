import logging

from markupsafe import Markup

from odoo import _, api, fields, models

from .. import simple_status

_logger = logging.getLogger(__name__)

EDITABLE_STATES = ("draft", "changes_requested")


class FederationScheduleSimpleSummary(models.Model):
    """The default scheduling screen: how many matches, what to fix, what to improve.

    Everything here is a read-only projection of the existing schedule validator.
    Fairness weights, candidate comparison and the other optimisation tools stay
    available to advanced operators; they are simply not the default view.
    """

    _inherit = "federation.schedule"

    simple_checked = fields.Boolean(compute="_compute_simple_summary")
    simple_scheduled_count = fields.Integer(compute="_compute_simple_summary")
    must_fix_count = fields.Integer(compute="_compute_simple_summary")
    could_improve_count = fields.Integer(compute="_compute_simple_summary")
    simple_summary = fields.Char(compute="_compute_simple_summary")
    must_fix_html = fields.Html(compute="_compute_simple_summary", sanitize=False)
    could_improve_html = fields.Html(compute="_compute_simple_summary", sanitize=False)

    @api.model
    def _simple_list_html(self, messages):
        if not messages:
            return False
        items = Markup("").join(Markup("<li>%s</li>") % text for text in messages)
        return Markup('<ul class="mb-0">%s</ul>') % items

    def _simple_validation(self):
        """Validate in a savepoint; a failing check must never look like a pass."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                return self._submission_validation(), False
        except Exception:  # pylint: disable=broad-except
            _logger.exception("Schedule status check failed for schedule %s", self.id)
            return False, True

    @api.depends("assignment_ids", "state", "revision", "matchday_id")
    def _compute_simple_summary(self):
        for schedule in self:
            persisted = schedule._origin
            scheduled = len(persisted.assignment_ids) if persisted else 0
            values = dict(
                simple_checked=False,
                simple_scheduled_count=scheduled,
                must_fix_count=0,
                could_improve_count=0,
                simple_summary=False,
                must_fix_html=False,
                could_improve_html=False,
            )
            if persisted and persisted.state in EDITABLE_STATES:
                validation, failed = persisted._simple_validation()
                if failed:
                    values.update(
                        simple_checked=True,
                        must_fix_count=1,
                        simple_summary=_("The schedule could not be checked."),
                        must_fix_html=self._simple_list_html(
                            [_("The schedule check failed. Ask an administrator to check the server log.")]
                        ),
                    )
                else:
                    must_fix, could_improve = simple_status.split_validation(validation)
                    blockers, warnings = simple_status.counts(validation)
                    values.update(
                        simple_checked=True,
                        must_fix_count=blockers,
                        could_improve_count=warnings,
                        simple_summary=simple_status.summary(scheduled, warnings, blockers),
                        must_fix_html=self._simple_list_html(must_fix),
                        could_improve_html=self._simple_list_html(could_improve),
                    )
            schedule.update(values)
