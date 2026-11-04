"""One-click publication of every ready game-day schedule of a competition.

The bulk command does not bypass any governance: each schedule still goes
through ``action_submit_for_review`` and therefore through the schedule
validator, the review record, the policy-driven approval and the immutable
publication snapshot.  It only removes the per-game-day clicking.
"""
from html import escape

from odoo import _, fields, models
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

    def action_publish_competition_schedule(self, warning_override_reason=False):
        """Submit (and, in Streamlined mode, approve and publish) all game days.

        ``warning_override_reason`` accepts schedule warnings (for example a
        team playing twice on one day) with an audited reason; without it, game
        days with warnings are reported instead of published.
        """
        self.ensure_one()
        if not warning_override_reason and not self.env.context.get("skip_warning_days"):
            details = self._schedule_warning_details()
            if details:
                return self._open_publish_confirmation(details)
        summary = self._publish_competition_schedule(warning_override_reason)
        return self._publish_notification(summary)

    def _schedule_warning_details(self):
        """Short-rest warnings of every schedule that is about to be submitted.

        Returns ``[(schedule, [line, ...]), ...]`` with plain-language lines
        such as "Falcons 1: 10:20 and 11:00 (0 min rest)".
        """
        self.ensure_one()
        validator = self.env["federation.schedule.validator"]
        details = []
        for schedule in self._publishable_schedules():
            if schedule.state not in ("draft", "changes_requested"):
                continue
            slot_by_fixture = {
                assignment.fixture_id.id: assignment.slot_id
                for assignment in schedule.assignment_ids
            }
            if not slot_by_fixture:
                continue
            validation = validator.validate_map(
                schedule, {fid: slot.id for fid, slot in slot_by_fixture.items()}
            )
            lines = []
            seen = set()
            for warning in validation.get("warnings") or []:
                first = slot_by_fixture.get(warning.get("fixture_id"))
                second = slot_by_fixture.get(warning.get("related_fixture_id"))
                if not first or not second:
                    lines.append(warning.get("message") or _("Schedule warning"))
                    continue
                early, late = sorted((first, second), key=lambda slot: slot.start_datetime)
                team = (warning.get("message") or "").split(" has ")[0]
                key = (team, early.id, late.id)
                if key in seen:
                    continue
                seen.add(key)
                gap = max(0, int((late.start_datetime - early.end_datetime).total_seconds() // 60))
                lines.append(
                    _(
                        "%(team)s: %(first)s and %(second)s (%(gap)s min rest)",
                        team=team,
                        first=fields.Datetime.context_timestamp(self, early.start_datetime).strftime("%H:%M"),
                        second=fields.Datetime.context_timestamp(self, late.start_datetime).strftime("%H:%M"),
                        gap=gap,
                    )
                )
            if lines:
                details.append((schedule, lines))
        return details

    def _open_publish_confirmation(self, details):
        self.ensure_one()
        sections = []
        for schedule, lines in details:
            rest = schedule.preferred_rest_minutes
            sections.append(
                "<p class='mb-1'><strong>%s</strong> &#8212; %s</p><ul>%s</ul>"
                % (
                    escape(schedule.matchday_id.display_name or schedule.display_name),
                    escape(_("preferred rest %(rest)s min", rest=rest)),
                    "".join("<li>%s</li>" % escape(line) for line in lines),
                )
            )
        wizard = self.env["federation.schedule.publish.confirm.wizard"].create(
            {
                "edition_id": self.id,
                "details_html": "".join(sections),
                "warning_day_count": len(details),
                "reason": _("Short rest between matches accepted by %(user)s.",
                            user=self.env.user.name),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Publish schedule"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }

    def _publish_competition_schedule(self, warning_override_reason=False):
        self.ensure_one()
        self.check_access("read")
        commands = self.env["federation.schedule.approval.commands"]
        submitted = published = 0
        waiting = []
        skipped = []
        short_rest = self.env["federation.schedule"]
        if not warning_override_reason:
            for schedule, _lines in self._schedule_warning_details():
                short_rest |= schedule
        for schedule in self._publishable_schedules():
            day = schedule.matchday_id
            label = day.display_name or schedule.display_name
            if schedule in short_rest:
                skipped.append(
                    _(
                        "%(day)s: some teams have less than the preferred rest between "
                        "matches. Publish again and accept the short rest, or "
                        "regenerate the schedule.",
                        day=label,
                    )
                )
                continue
            try:
                with self.env.cr.savepoint():
                    if schedule.state in ("draft", "changes_requested"):
                        if schedule.unassigned_fixture_count:
                            raise ValidationError(
                                _("%(count)s match(es) still have no court or time.",
                                  count=schedule.unassigned_fixture_count)
                            )
                        schedule.action_submit_for_review(
                            warning_override_reason=warning_override_reason
                        )
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

        return {
            "submitted": submitted,
            "published": published,
            "waiting": waiting,
            "skipped": skipped,
        }

    def _publish_notification(self, summary):
        submitted = summary["submitted"]
        published = summary["published"]
        waiting = summary["waiting"]
        skipped = summary["skipped"]
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
