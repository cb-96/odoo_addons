from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class CompetitionCreationDraft(models.Model):
    _name = "federation.competition.creation.draft"
    _description = "Saved competition creation draft"
    _order = "write_date desc, id desc"

    name = fields.Char(required=True)
    owner_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, readonly=True)
    payload = fields.Json(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([dict(vals, owner_id=self.env.user.id) for vals in vals_list])

    def write(self, vals):
        if "owner_id" in vals:
            raise AccessError(_("Draft ownership cannot be transferred."))
        return super().write(vals)

    def action_resume(self):
        self.ensure_one()
        self.check_access("read")
        wizard = self.env["federation.create.competition.wizard"].create(dict(self.payload, creation_draft_id=self.id))
        return {"type": "ir.actions.act_window", "name": _("Resume competition creation"), "res_model": wizard._name, "res_id": wizard.id, "view_mode": "form", "target": "new"}
