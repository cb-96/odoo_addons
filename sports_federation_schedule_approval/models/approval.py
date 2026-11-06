from html import escape

from odoo import _, api, fields, models


def _assignment_snapshot_html(env, snapshot):
    entries = [
        item
        for item in (snapshot or [])
        if isinstance(item, dict) and not item.get("_empty")
    ]
    if not entries:
        return _("<p>No fixture assignments are recorded in this snapshot.</p>")

    def records_by_id(model_name, key):
        ids = {
            int(item[key])
            for item in entries
            if item.get(key) not in (None, False, "")
        }
        return {
            record.id: record
            for record in env[model_name].sudo().browse(sorted(ids)).exists()
        }

    fixtures = records_by_id("federation.fixture", "fixture_id")
    matches = records_by_id("federation.match", "match_id")
    courts = records_by_id("federation.playing.area", "court_id")
    rows = []
    for item in entries:
        fixture_id = int(item.get("fixture_id") or 0)
        match_id = int(item.get("match_id") or 0)
        court_id = int(item.get("court_id") or 0)
        fixture = fixtures.get(fixture_id)
        match = matches.get(match_id)
        court = courts.get(court_id)
        rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                escape(match.display_name if match else (_("Match #%s") % match_id if match_id else "—")),
                escape(fixture.display_name if fixture else (_("Fixture #%s") % fixture_id if fixture_id else "—")),
                escape(court.display_name if court else (_("Court #%s") % court_id if court_id else "—")),
                escape(str(item.get("start") or "—")),
                escape(str(item.get("end") or "—")),
            )
        )
    return (
        "<div class='table-responsive'><table class='table table-sm table-striped mb-0'>"
        "<thead><tr><th>Match</th><th>Fixture</th><th>Court</th>"
        "<th>Start</th><th>End</th></tr></thead><tbody>%s</tbody></table></div>"
        % "".join(rows)
    )


class FederationScheduleReview(models.Model):
    _name = "federation.schedule.review"
    _description = "Independent Schedule Review"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    schedule_id = fields.Many2one(
        "federation.schedule", required=True, ondelete="cascade", index=True
    )
    edition_id = fields.Many2one(
        related="schedule_id.edition_id", store=True, index=True
    )
    self_approval_allowed = fields.Boolean(
        related="edition_id.schedule_self_approval_allowed", readonly=True
    )
    submitted_revision = fields.Integer(required=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("withdrawn", "Withdrawn"),
            ("changes_requested", "Changes Requested"),
            ("approved", "Approved"),
        ],
        default="pending",
        required=True,
        tracking=True,
        index=True,
    )
    reviewer_id = fields.Many2one("res.users", ondelete="set null")
    review_note = fields.Text()
    assignment_snapshot = fields.Json(required=True)
    assignment_summary_html = fields.Html(
        string="Submitted assignments",
        compute="_compute_assignment_summary_html",
        readonly=True,
        sanitize=True,
    )

    @api.depends("assignment_snapshot")
    def _compute_assignment_summary_html(self):
        for review in self:
            review.assignment_summary_html = _assignment_snapshot_html(
                review.env, review.assignment_snapshot
            )


class FederationSchedulePublication(models.Model):
    _name = "federation.schedule.publication"
    _description = "Immutable Schedule Publication"
    _order = "version desc,id desc"
    schedule_id = fields.Many2one(
        "federation.schedule", required=True, ondelete="restrict", index=True
    )
    edition_id = fields.Many2one(
        related="schedule_id.edition_id", store=True, index=True
    )
    matchday_id = fields.Many2one(
        related="schedule_id.matchday_id", store=True, index=True
    )
    version = fields.Integer(required=True)
    state = fields.Selection(
        [("live", "Live"), ("superseded", "Superseded")],
        default="live",
        required=True,
        index=True,
    )
    published_by_id = fields.Many2one(
        "res.users", default=lambda s: s.env.user, required=True, ondelete="restrict"
    )
    published_at = fields.Datetime(default=fields.Datetime.now, required=True)
    reason = fields.Text()
    assignment_snapshot = fields.Json(required=True)
    assignment_summary_html = fields.Html(
        string="Published assignments",
        compute="_compute_assignment_summary_html",
        readonly=True,
        sanitize=True,
    )

    @api.depends("assignment_snapshot")
    def _compute_assignment_summary_html(self):
        for publication in self:
            publication.assignment_summary_html = _assignment_snapshot_html(
                publication.env, publication.assignment_snapshot
            )
    _unique_version = models.Constraint(
        "unique(matchday_id,version)",
        "Publication versions must be unique per match day.",
    )
