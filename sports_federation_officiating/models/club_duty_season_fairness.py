"""Engage season-fair rebalancing in the reviewed club-duty workflow.

The review, publication and governed club-duty runs all build their proposal
through ``federation.schedule._duty_proposal``. Refining that proposal here keeps
the three paths identical: the season ledger and targets feed
``duty_season_balance.rebalance_season``, the targets join the review
fingerprint, and the balance is shown in the review and kept in run summaries.
"""

from html import escape

from odoo import _, models

from ..duty_allocation import fingerprint
from ..duty_season_balance import rebalance_season, role_minutes

LEDGER_SEASON_PATH = "match_id.schedule_publication_id.schedule_id.edition_id.season_id"


class FederationScheduleSeasonFairDuties(models.Model):
    _inherit = "federation.schedule"

    def _club_duty_season_load(self):
        """Committed duty minutes per club in this schedule's season.

        Counts every club duty that is not rejected on a match published from a
        schedule of the same season. The duration comes from the match's
        operational slot, or its published slot. Keys are club ids as strings.
        """
        self.ensure_one()
        season = self.edition_id.season_id
        if not season:
            return {}
        duties = self.env["federation.match.club.referee.duty"].search(
            [(LEDGER_SEASON_PATH, "=", season.id), ("state", "!=", "rejected")]
        )
        ledger = {}
        for duty in duties:
            match = duty.match_id
            slot = match.operational_slot_id or match.published_slot_id
            minutes = 0
            if (
                slot.start_datetime
                and slot.end_datetime
                and slot.end_datetime > slot.start_datetime
            ):
                delta = slot.end_datetime - slot.start_datetime
                minutes = int(delta.total_seconds() // 60)
            key = str(duty.club_id.id)
            ledger[key] = ledger.get(key, 0) + minutes
        return ledger

    def _club_duty_target_minutes(self):
        self.ensure_one()
        return {
            str(club): int(minutes)
            for club, minutes in self._club_duty_season_targets().items()
        }

    def _duty_fingerprint(self, policy):
        signature = super()._duty_fingerprint(policy)
        targets = self._club_duty_target_minutes()
        if not targets:
            return signature
        return fingerprint({"allocation": signature, "season_targets": targets})

    def _duty_proposal(self, policy):
        proposal = super()._duty_proposal(policy)
        return self._club_duty_fairness_rebalance(proposal, policy)

    def _club_duty_fairness_rebalance(self, allocation, policy=None):
        """Refine a feasible allocation toward the season duty-minute targets."""
        self.ensure_one()
        targets = self._club_duty_target_minutes()
        if not targets:
            return allocation
        if allocation.get("issues"):
            allocation["fairness"] = {"engaged": False, "reason": "blocking_issues"}
            return allocation
        if not allocation.get("rows"):
            allocation["fairness"] = {"engaged": False, "reason": "no_new_duties"}
            return allocation
        policy = policy or self.club_duty_policy or {}
        before = allocation["rows"]
        rows, report = rebalance_season(
            before,
            self._duty_geometry(),
            capacities=self._club_duty_capacity_policy(),
            avoid_playing=bool(policy.get("avoid", True)),
            allow_fallback=bool(policy.get("fallback", False)),
            season_minutes=self._club_duty_season_load(),
            targets=targets,
            fixed_rows=allocation.get("preserved") or [],
        )
        load = dict(allocation.get("load") or {})
        minute_load = dict(allocation.get("minute_load") or {})
        for old, new in zip(before, rows):
            if old["club"] == new["club"]:
                continue
            source, target = str(old["club"]), str(new["club"])
            for totals, amount in (
                (load, len(old["roles"])),
                (minute_load, role_minutes(old)),
            ):
                totals[source] = totals.get(source, 0) - amount
                totals[target] = totals.get(target, 0) + amount
        allocation.update(
            rows=rows, load=load, minute_load=minute_load, fairness=report
        )
        return allocation


class ClubDutyReviewSeasonFairness(models.TransientModel):
    _inherit = "federation.schedule.club.duty.review"

    def action_preview(self):
        action = super().action_preview()
        sections = []
        for schedule in self.schedule_ids:
            proposal = (self.preview or {}).get(str(schedule.id)) or {}
            if proposal.get("fairness"):
                sections.append(
                    self._season_balance_html(schedule, proposal["fairness"])
                )
        if sections:
            html = str(self.preview_html or "") + "".join(sections)
            self.write({"preview_html": html})
        return action

    def _season_balance_html(self, schedule, fairness):
        title = escape(_("Season duty balance: %s") % schedule.display_name)
        if not fairness.get("engaged"):
            reasons = {
                "blocking_issues": _(
                    "Season balancing runs once the allocation has no blocking "
                    "issues."
                ),
                "no_new_duties": _("There are no new duties to balance."),
            }
            reason = reasons.get(fairness.get("reason"), "")
            return "<h5>%s</h5><p>%s</p>" % (title, escape(reason))
        labels = (
            _("Club"),
            _("Season so far"),
            _("Planned now"),
            _("Projected"),
            _("Target"),
            _("Deviation"),
        )
        header = "".join("<th>%s</th>" % escape(label) for label in labels)
        lines = []
        for key in sorted(fairness["projected_minutes"], key=int):
            deviation = fairness["deviation_minutes"].get(key)
            cells = (
                self.env["federation.club"].browse(int(key)).display_name,
                fairness["season_minutes"].get(key, 0),
                fairness["planned_minutes"].get(key, 0),
                fairness["projected_minutes"][key],
                fairness["targets"].get(key) or _("None"),
                "%+d" % deviation if deviation is not None else "",
            )
            lines.append(
                "<tr>%s</tr>"
                % "".join("<td>%s</td>" % escape(str(cell)) for cell in cells)
            )
        summary = _(
            "%(moved)s fixture(s) moved toward the targets. Squared deviation: "
            "%(before)s before balancing, %(after)s after."
        ) % {
            "moved": len(fairness.get("moved_fixtures") or []),
            "before": fairness.get("objective_before", 0),
            "after": fairness.get("objective_after", 0),
        }
        return (
            '<h5>%s</h5><table class="table table-sm"><tr>%s</tr>%s</table>'
            "<p>%s</p>" % (title, header, "".join(lines), escape(summary))
        )


class FederationClubDutyPlanRunSeasonFairness(models.Model):
    _inherit = "federation.schedule.plan.run"

    def _prepare_plan(self):
        values = super()._prepare_plan()
        if len(self) != 1 or self.plan_type != "club_duty":
            return values
        fairness = ((values or {}).get("proposal") or {}).get("fairness")
        if fairness:
            values["summary"] = dict(
                values.get("summary") or {}, season_fairness=fairness
            )
        return values
