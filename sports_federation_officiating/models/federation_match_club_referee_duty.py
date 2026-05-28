from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FederationMatchClubRefereeDuty(models.Model):
    """Obligation for a club to supply a table/assistant official for a match.

    Workflow: draft → open → nominated → confirmed
                                ↓
                             rejected → nominated (re-nominate)
    """

    _name = "federation.match.club.referee.duty"
    _description = "Club Referee Duty"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "match_id, club_id"
    _rec_name = "display_name"

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    display_name = fields.Char(
        string="Name",
        compute="_compute_display_name",
    )

    match_id = fields.Many2one(
        "federation.match",
        string="Match",
        required=True,
        ondelete="cascade",
        index=True,
    )
    club_id = fields.Many2one(
        "federation.club",
        string="Club",
        required=True,
        ondelete="restrict",
        index=True,
    )
    role = fields.Selection(
        [
            ("head", "Head Referee"),
            ("assistant_1", "Assistant Referee 1"),
            ("assistant_2", "Assistant Referee 2"),
            ("fourth", "Fourth Official"),
            ("table", "Table Official"),
        ],
        string="Role",
        required=True,
        default="table",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Open"),
            ("nominated", "Nominated"),
            ("confirmed", "Confirmed"),
            ("rejected", "Rejected"),
        ],
        string="State",
        default="draft",
        required=True,
        tracking=True,
    )
    nominated_player_id = fields.Many2one(
        "federation.player",
        string="Nominated Player",
        domain="[('club_id', '=', club_id)]",
        ondelete="set null",
        tracking=True,
    )
    nominated_by_id = fields.Many2one(
        "res.users",
        string="Nominated By",
        readonly=True,
    )
    nominated_on = fields.Datetime(
        string="Nominated On",
        readonly=True,
    )
    nomination_deadline = fields.Datetime(
        compute="_compute_nomination_deadline",
        store=True,
        string="Nomination Deadline",
    )
    is_deadline_overdue = fields.Boolean(
        compute="_compute_is_deadline_overdue",
        store=True,
        string="Deadline Overdue",
    )
    assignment_id = fields.Many2one(
        "federation.match.referee",
        string="Referee Assignment",
        readonly=True,
        ondelete="set null",
    )
    notes = fields.Text(string="Notes")

    _club_duty_unique = models.Constraint(
        "unique (match_id, club_id, role)",
        "A club can owe at most one duty per role per match.",
    )

    # ------------------------------------------------------------------
    # Computed
    # ------------------------------------------------------------------

    @api.depends("match_id", "club_id", "role")
    def _compute_display_name(self):
        role_labels = dict(self._fields["role"].selection)
        for rec in self:
            match_name = rec.match_id.display_name or str(rec.match_id.id)
            club_name = rec.club_id.name or str(rec.club_id.id)
            role_label = role_labels.get(rec.role, rec.role)
            rec.display_name = f"{match_name} – {club_name} ({role_label})"

    @api.depends("match_id.date_scheduled")
    def _compute_nomination_deadline(self):
        for rec in self:
            if rec.match_id.date_scheduled:
                rec.nomination_deadline = fields.Datetime.to_datetime(
                    rec.match_id.date_scheduled
                ) - timedelta(hours=72)
            else:
                rec.nomination_deadline = False

    @api.depends("nomination_deadline", "state")
    def _compute_is_deadline_overdue(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_deadline_overdue = bool(
                rec.state in ("draft", "open", "nominated", "rejected")
                and rec.nomination_deadline
                and now > rec.nomination_deadline
            )

    # ------------------------------------------------------------------
    # State actions
    # ------------------------------------------------------------------

    def action_open(self):
        """Draft → Open: notify club rep."""
        for rec in self:
            if rec.state != "draft":
                raise ValidationError(
                    _("Only draft duties can be opened (record: %s).")
                    % rec.display_name
                )
            rec.write({"state": "open"})
            Dispatcher = self.env.get("federation.notification.dispatcher")
            if Dispatcher is not None and hasattr(Dispatcher, "send_club_duty_opened"):
                Dispatcher.send_club_duty_opened(rec)

    def action_nominate(self, player_id):
        """Open/Rejected → Nominated: club submits a player.

        :param player_id: int — ID of the ``federation.player`` record.
        """
        for rec in self:
            if rec.state not in ("open", "rejected"):
                raise ValidationError(
                    _("Only open or rejected duties can be nominated (record: %s).")
                    % rec.display_name
                )
            player = self.env["federation.player"].browse(player_id)
            if not player.exists():
                raise ValidationError(_("Player not found."))
            if player.club_id.id != rec.club_id.id:
                raise ValidationError(
                    _("Player '%(player)s' does not belong to club '%(club)s'.")
                    % {"player": player.display_name, "club": rec.club_id.display_name}
                )
            rec.write(
                {
                    "state": "nominated",
                    "nominated_player_id": player.id,
                    "nominated_by_id": self.env.user.id,
                    "nominated_on": fields.Datetime.now(),
                }
            )

    def action_confirm(self):
        """Nominated → Confirmed: create federation.match.referee assignment."""
        for rec in self:
            if rec.state != "nominated":
                raise ValidationError(
                    _("Only nominated duties can be confirmed (record: %s).")
                    % rec.display_name
                )
            if not rec.nominated_player_id:
                raise ValidationError(
                    _("No player has been nominated for duty %s.") % rec.display_name
                )
            referee = self._get_or_create_referee_for_player(rec.nominated_player_id)
            assignment = self.env["federation.match.referee"].create(
                {
                    "match_id": rec.match_id.id,
                    "referee_id": referee.id,
                    "role": rec.role,
                    "state": "confirmed",
                }
            )
            rec.write({"state": "confirmed", "assignment_id": assignment.id})

    def action_reject(self, reason=""):
        """Nominated → Rejected: return to club for re-nomination."""
        for rec in self:
            if rec.state != "nominated":
                raise ValidationError(
                    _("Only nominated duties can be rejected (record: %s).")
                    % rec.display_name
                )
            notes = (rec.notes or "").strip()
            if reason:
                notes = (notes + "\n" + reason).strip() if notes else reason
            rec.write({"state": "rejected", "notes": notes or False})

    def action_cancel(self):
        """Any non-confirmed → Draft (admin escape hatch)."""
        for rec in self:
            if rec.state == "confirmed":
                raise ValidationError(
                    _("Confirmed duties cannot be cancelled (record: %s).")
                    % rec.display_name
                )
            rec.write(
                {
                    "state": "draft",
                    "nominated_player_id": False,
                    "nominated_by_id": False,
                    "nominated_on": False,
                    "assignment_id": False,
                }
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_referee_for_player(self, player):
        """Return (or create) a ``federation.referee`` record for *player*.

        A club-supplied official may not have a formal referee record yet.  We
        match by exact name and create a minimal record if none is found so
        that the existing officiating-readiness logic keeps working without
        changes.
        """
        Referee = self.env["federation.referee"]
        referee = Referee.search([("name", "=", player.display_name)], limit=1)
        if not referee:
            referee = Referee.create({"name": player.display_name})
        return referee
