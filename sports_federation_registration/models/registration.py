from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationRegistrationWindow(models.Model):
    _name = "federation.registration.window"
    _description = "Competition Registration Window"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    name = fields.Char(required=True)
    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, ondelete="cascade", index=True
    )
    division_id = fields.Many2one(
        "federation.tournament", required=True, ondelete="cascade", index=True
    )
    date_open = fields.Datetime()
    date_close = fields.Datetime()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Open"),
            ("closed", "Closed"),
            ("finalized", "Finalized"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    entry_ids = fields.One2many("federation.competition.entry", "window_id")
    participant_set_id = fields.Many2one(
        "federation.participant.set", readonly=True, copy=False
    )

    def action_open(self):
        self.write({"state": "open"})
        return True

    def action_close(self):
        self.write({"state": "closed"})
        return True

    def action_finalize(self):
        roles = self.env["federation.competition.role.assignment"]
        roles.assert_role(
            self.edition_id, "registration_manager", "competition_director"
        )
        for rec in self:
            if rec.state != "closed":
                raise ValidationError(
                    _("Close registration before finalizing participants.")
                )
            approved = rec.entry_ids.filtered(lambda x: x.state == "approved")
            if len(approved) < 2:
                raise ValidationError(_("At least two approved teams are required."))
            if len(approved.mapped("team_id")) != len(approved):
                raise ValidationError(_("The approved list contains duplicate teams."))
            pset = self.env["federation.participant.set"].create(
                {
                    "name": _("Participants - %s") % rec.division_id.display_name,
                    "edition_id": rec.edition_id.id,
                    "division_id": rec.division_id.id,
                    "state": "finalized",
                }
            )
            self.env["federation.participant.set.line"].create(
                [
                    {
                        "participant_set_id": pset.id,
                        "team_id": e.team_id.id,
                        "seed": e.seed,
                    }
                    for e in approved
                ]
            )
            rec.write({"state": "finalized", "participant_set_id": pset.id})
            self.env["federation.competition.event"].emit(
                pset, "participant_set_finalized", {"team_count": len(approved)}
            )
        return True


class FederationCompetitionEntry(models.Model):
    _name = "federation.competition.entry"
    _description = "Competition Entry"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    window_id = fields.Many2one(
        "federation.registration.window", required=True, ondelete="cascade", index=True
    )
    edition_id = fields.Many2one(related="window_id.edition_id", store=True, index=True)
    team_id = fields.Many2one(
        "federation.team", required=True, ondelete="restrict", index=True
    )
    seed = fields.Integer()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("withdrawn", "Withdrawn"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    review_note = fields.Text()
    _unique_team = models.Constraint(
        "unique(window_id,team_id)", "A team can enter a registration window only once."
    )

    def action_submit(self):
        self.write({"state": "submitted"})
        return True

    def action_approve(self):
        self.mapped("window_id.edition_id") and self.env[
            "federation.competition.role.assignment"
        ].assert_role(
            self[:1].edition_id, "registration_manager", "competition_director"
        )
        self.write({"state": "approved"})
        return True

    def action_reject(self):
        self.write({"state": "rejected"})
        return True


class FederationParticipantSet(models.Model):
    _name = "federation.participant.set"
    _description = "Finalized Participant Set"
    _order = "id desc"
    name = fields.Char(required=True)
    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, ondelete="cascade", index=True
    )
    division_id = fields.Many2one(
        "federation.tournament", required=True, ondelete="cascade", index=True
    )
    state = fields.Selection(
        [("draft", "Draft"), ("finalized", "Finalized"), ("superseded", "Superseded")],
        default="draft",
        required=True,
        index=True,
    )
    line_ids = fields.One2many(
        "federation.participant.set.line", "participant_set_id", readonly=True
    )


class FederationParticipantSetLine(models.Model):
    _name = "federation.participant.set.line"
    _description = "Participant Set Line"
    _order = "seed,id"
    participant_set_id = fields.Many2one(
        "federation.participant.set", required=True, ondelete="cascade", index=True
    )
    team_id = fields.Many2one(
        "federation.team", required=True, ondelete="restrict", index=True
    )
    seed = fields.Integer()
    _unique_team = models.Constraint(
        "unique(participant_set_id,team_id)",
        "A finalized participant set cannot contain duplicate teams.",
    )
