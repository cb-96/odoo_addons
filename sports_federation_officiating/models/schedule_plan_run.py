from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.sports_federation_scheduling.planning_fingerprint import fingerprint


class FederationClubDutyPlanRun(models.Model):
    _inherit = "federation.schedule.plan.run"

    plan_type = fields.Selection(
        selection_add=[("club_duty", "Club-duty allocation")],
        ondelete={"club_duty": "cascade"},
    )

    def _normalized_club_duty_configuration(self):
        self.ensure_one()
        defaults = {
            "officials_per_match": 0,
            "avoid_playing": True,
            "allow_fallback": False,
            "preserve_existing": True,
        }
        unknown = set(self.configuration or {}) - set(defaults)
        if unknown:
            raise ValidationError(
                _("Unsupported club-duty planning options: %s")
                % ", ".join(sorted(unknown))
            )
        defaults.update(self.configuration or {})
        if not 0 <= int(defaults["officials_per_match"]) <= 5:
            raise ValidationError(
                _("Officials per match must be between zero and five.")
            )
        defaults["officials_per_match"] = int(defaults["officials_per_match"])
        for key in ("avoid_playing", "allow_fallback", "preserve_existing"):
            defaults[key] = bool(defaults[key])
        return defaults

    def _check_club_duty_planner(self):
        self.ensure_one()
        self.schedule_id._check_duty_planner()
        if self.schedule_id.state != "draft":
            raise UserError(
                _(
                    "Governed club-duty runs apply to draft schedules. Use the existing "
                    "review action for additive duties on the current publication."
                )
            )

    def _club_duty_wizard(self):
        configuration = self._normalized_club_duty_configuration()
        return self.env["federation.schedule.club.duty.review"].create(
            {
                "schedule_ids": [fields.Command.set(self.schedule_id.ids)],
                **configuration,
            }
        )

    def _club_duty_proposal(self):
        wizard = self._club_duty_wizard()
        wizard.action_preview()
        return wizard, wizard.preview[str(self.schedule_id.id)]

    def _club_duty_source_signature(self, proposal):
        return fingerprint(
            {
                "schedule": self.schedule_id.id,
                "revision": self.schedule_id.revision,
                "configuration": self._normalized_club_duty_configuration(),
                "review_signature": proposal["review_signature"],
            }
        )

    def _club_duty_applied_signature(self):
        schedule = self.schedule_id
        policy = schedule.club_duty_policy or {}
        return fingerprint(
            {
                "policy": policy,
                "plan": schedule.club_duty_plan,
                "stored_signature": schedule.club_duty_signature,
                "current_signature": (
                    schedule._duty_fingerprint(policy) if policy else False
                ),
            }
        )

    def _prepare_plan(self):
        if self.plan_type != "club_duty":
            return super()._prepare_plan()
        self.ensure_one()
        self._check_club_duty_planner()
        _wizard, proposal = self._club_duty_proposal()
        if proposal["issues"]:
            raise UserError("\n".join(proposal["issues"]))
        return {
            "configuration": self._normalized_club_duty_configuration(),
            "proposal": proposal,
            "summary": {
                "proposed_fixture_count": len(proposal["rows"]),
                "preserved_duty_count": len(proposal["preserved"]),
                "issue_count": len(proposal["issues"]),
                "role_load": proposal["load"],
                "minute_load": proposal["minute_load"],
            },
            "before_snapshot": {
                "club_duty_policy": self.schedule_id.club_duty_policy,
                "club_duty_plan": self.schedule_id.club_duty_plan,
                "club_duty_signature": self.schedule_id.club_duty_signature,
            },
            "source_signature": self._club_duty_source_signature(proposal),
            "source_revision": self.schedule_id.revision,
        }

    def _apply_plan(self):
        if self.plan_type != "club_duty":
            return super()._apply_plan()
        self.ensure_one()
        self._check_club_duty_planner()
        if self.source_revision != self.schedule_id.revision:
            raise UserError(_("The schedule changed after this run was prepared."))
        wizard, proposal = self._club_duty_proposal()
        if self.source_signature != self._club_duty_source_signature(proposal):
            raise UserError(_("Club-duty inputs changed. Prepare a new planning run."))
        if self.proposal_signature != fingerprint(proposal):
            raise UserError(
                _("The club-duty proposal changed. Prepare a new planning run.")
            )
        wizard.action_apply()
        return {
            "result_revision": self.schedule_id.revision,
            "applied_signature": self._club_duty_applied_signature(),
        }

    def _rollback_plan(self):
        if self.plan_type != "club_duty":
            return super()._rollback_plan()
        self.ensure_one()
        self._check_club_duty_planner()
        if self.result_revision != self.schedule_id.revision:
            raise UserError(_("The schedule changed after this run was applied."))
        if self.applied_signature != self._club_duty_applied_signature():
            raise UserError(
                _("Club-duty inputs changed; this run cannot be rolled back.")
            )
        self.schedule_id.write(
            {
                "club_duty_policy": self.before_snapshot.get("club_duty_policy"),
                "club_duty_plan": self.before_snapshot.get("club_duty_plan"),
                "club_duty_signature": self.before_snapshot.get("club_duty_signature"),
            }
        )
        return {"result_revision": self.schedule_id.revision}


class FederationScheduleClubDutyRuns(models.Model):
    _inherit = "federation.schedule"

    def action_create_club_duty_plan_run(self):
        self.ensure_one()
        run = self.env["federation.schedule.plan.run"].create(
            {
                "schedule_id": self.id,
                "plan_type": "club_duty",
                "configuration": {
                    "officials_per_match": 0,
                    "avoid_playing": True,
                    "allow_fallback": False,
                    "preserve_existing": True,
                },
            }
        )
        return run.action_prepare()
