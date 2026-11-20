import hashlib
import json
from html import escape

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationResultCorrectionImpact(models.Model):
    _inherit = "federation.match"

    def _result_correction_impact(self):
        self.ensure_one()
        Fixture = self.env.get("federation.fixture")
        dependants = Fixture.browse() if Fixture is not None else []
        matches = self.env["federation.match"].browse()
        if (
            Fixture is not None
            and "logical_fixture_id" in self._fields
            and "operational_match_id" in Fixture._fields
        ):
            fixture = self.logical_fixture_id
            seen = set()
            frontier = fixture
            while frontier:
                rows = Fixture.search(
                    [
                        "|",
                        ("home_source_fixture_id", "in", frontier.ids),
                        ("away_source_fixture_id", "in", frontier.ids),
                    ]
                )
                rows = rows.filtered(lambda item: item.id not in seen)
                if not rows:
                    break
                seen.update(rows.ids)
                dependants |= rows
                frontier = rows
            matches = dependants.mapped("operational_match_id")
        started = matches.filtered(
            lambda match: match.state in ("in_progress", "done")
            or match.result_state != "draft"
        )
        Standing = self.env.get("federation.standing")
        standings = (
            Standing.search([("tournament_id", "=", self.tournament_id.id)])
            if Standing is not None
            else Standing
        )
        Finance = self.env.get("federation.finance.event")
        finance_count = (
            Finance.search_count(
                [
                    ("source_model", "=", self._name),
                    ("source_res_id", "=", self.id),
                    ("state", "!=", "cancelled"),
                ]
            )
            if Finance is not None
            else 0
        )
        publication_ids = (
            matches.mapped("schedule_publication_id").ids
            if "schedule_publication_id" in matches._fields
            else []
        )
        impact = {
            "match_id": self.id,
            "result_state": self.result_state,
            "standing_ids": standings.ids if standings is not None else [],
            "dependent_fixture_ids": dependants.ids if Fixture is not None else [],
            "dependent_match_ids": matches.ids,
            "started_dependent_match_ids": started.ids,
            "finance_event_count": finance_count,
            "publication_ids": publication_ids,
        }
        impact["signature"] = hashlib.sha256(
            json.dumps(impact, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return impact

    def _assert_result_correction_safe(self):
        for match in self:
            impact = match._result_correction_impact()
            if impact["started_dependent_match_ids"]:
                names = (
                    self.env["federation.match"]
                    .browse(impact["started_dependent_match_ids"])
                    .mapped("display_name")
                )
                raise ValidationError(
                    _(
                        "A dependent match has already started or recorded a result "
                        "(%s). Use a governed competition-resolution decision; "
                        "participants cannot be replaced automatically."
                    )
                    % ", ".join(names)
                )
        return True

    def action_open_correction_impact(self):
        self.ensure_one()
        impact = self._result_correction_impact()
        wizard = self.env["federation.result.correction.wizard"].create(
            {
                "match_id": self.id,
                "reason": self.result_correction_reason,
                "impact": impact,
                "impact_signature": impact["signature"],
            }
        )
        return wizard.get_formview_action()


class FederationResultCorrectionWizard(models.TransientModel):
    _name = "federation.result.correction.wizard"
    _description = "Preview Result Correction Impact"

    match_id = fields.Many2one("federation.match", required=True, readonly=True)
    reason = fields.Text(required=True)
    impact = fields.Json(required=True, readonly=True)
    impact_signature = fields.Char(required=True, readonly=True)
    impact_html = fields.Html(compute="_compute_impact_html", sanitize=True)

    def _compute_impact_html(self):
        for wizard in self:
            impact = wizard.impact or {}
            rows = [
                (_("Standings to recompute"), len(impact.get("standing_ids", []))),
                (_("Dependent fixtures"), len(impact.get("dependent_fixture_ids", []))),
                (_("Dependent matches"), len(impact.get("dependent_match_ids", []))),
                (
                    _("Already-started dependent matches"),
                    len(impact.get("started_dependent_match_ids", [])),
                ),
                (_("Finance records to review"), impact.get("finance_event_count", 0)),
                (_("Publications affected"), len(impact.get("publication_ids", []))),
            ]
            wizard.impact_html = "<ul>%s</ul>" % "".join(
                "<li><strong>%s:</strong> %s</li>"
                % (escape(str(label)), escape(str(value)))
                for label, value in rows
            )

    def action_apply(self):
        self.ensure_one()
        current = self.match_id._result_correction_impact()
        if current["signature"] != self.impact_signature:
            raise ValidationError(
                _("The correction impact changed. Open a new preview.")
            )
        if not (self.reason or "").strip():
            raise ValidationError(_("Record the correction reason."))
        self.match_id._assert_result_correction_safe()
        self.match_id.result_correction_reason = self.reason.strip()
        self.match_id.with_context(
            correction_impact_signature=self.impact_signature
        ).action_correct_result()
        return self.match_id.get_formview_action()
