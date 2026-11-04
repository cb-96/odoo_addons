"""One-click publication of every ready game-day schedule of a competition.

The bulk command does not bypass any governance: each schedule still goes
through ``action_submit_for_review`` and therefore through the schedule
validator, the review record, the policy-driven approval and the immutable
publication snapshot.  It only removes the per-game-day clicking.
"""
from odoo import _, models
from odoo.exceptions import AccessError, UserError, ValidationError


class FederationCompetitionEditionPublish(models.Model):
    _inherit = "federation.competition.edition"

    def _publishable_schedules(self):
        """Return the current working schedule of every active game day."""
        self.ensure_one()
        schedules = self.env["federation.schedule"].search(
            [("edition_id", "=", self.id), ("state", "!=", "superseded")],
            order="matchday_id,revision desc,id desc",
        )
        current = self.env["federation.schedule"]
        seen = set()
        for schedule in schedules:
            day = schedule.matchday_id
            if not day or day.id in seen or day.state == "cancelled":
                continue
            seen.add(day.id)
            current |= schedule
        return current

    def action_publish_competition_schedule(self):
        """Submit (and, in Streamlined mode, approve and publish) all game days."""
        self.ensure_one()
        self.check_access("read")
        commands = self.env["federation.schedule.approval.commands"]
        submitted = published = 0
        waiting = []
        skipped = []
        for schedule in self._publishable_schedules():
            day = schedule.matchday_id
            label = day.display_name or schedule.display_name
            try:
                with self.env.cr.savepoint():
                    if schedule.state in ("draft", "changes_requested"):
                        if schedule.unassigned_fixture_count:
                            raise ValidationError(
                                _("%(count)s match(es) still have no court or time.",
                                  count=schedule.unassigned_fixture_count)
                            )
                        schedule.action_submit_for_review()
                        submitted += 1
                    elif schedule.state == "approved":
                        current = day.current_publication_id
                        if current and current.state == "live":
                            continue
                        commands.publish(schedule.id, expected_publication_id=0)
                    else:
                        # ready_for_review is waiting for an independent reviewer;
                        # published needs nothing.
                        if schedule.state == "ready_for_review":
                            waiting.append(label)
                        continue
                    schedule.invalidate_recordset()
                    if schedule.state == "published":
                        published += 1
                    elif schedule.state == "ready_for_review":
                        waiting.append(label)
            except (AccessError, UserError, ValidationError) as error:
                skipped.append("%s: %s" % (label, getattr(error, "args", [error])[0]))

        lines = []
        if published:
            lines.append(_("%(count)s game day(s) published.", count=published))
        if waiting:
            lines.append(
                _("%(count)s game day(s) wait for independent review.", count=len(waiting))
            )
        if skipped:
            lines.append(_("Not published:") + "\n" + "\n".join(skipped))
        if not lines:
            lines.append(
                _("Nothing to publish: every planned game day is already published.")
                if not submitted
                else _("%(count)s schedule(s) submitted.", count=submitted)
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Publish schedule"),
                "message": "\n".join(lines),
                "type": "warning" if skipped else "success",
                "sticky": bool(skipped),
                "next": self.action_open_competition_planner(),
            },
        }
