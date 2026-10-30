from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class Finance(models.Model):
    _inherit = 'federation.finance.event'
    account_move_id = fields.Many2one('account.move', readonly=True, copy=False, ondelete='restrict', check_company=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    invoice_product_id = fields.Many2one('product.product', check_company=True)
    charge_owner = fields.Selection([('federation', 'Federation'), ('club', 'Club')], default='federation', required=True)
    invoice_currency_id = fields.Many2one(related='account_move_id.currency_id')
    invoice_balance = fields.Monetary(related='account_move_id.amount_residual', currency_field='invoice_currency_id')
    invoice_payment_state = fields.Selection(related='account_move_id.payment_state')

    def _finance_actor(self):
        if not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_('Invoice administration permission is required.'))
        self.check_access('write')

    def write(self, vals):
        if vals.get('state') == 'settled' and any(e.account_move_id and (e.account_move_id.state != 'posted' or e.account_move_id.payment_state != 'paid') for e in self):
            raise ValidationError(_('An unpaid invoice cannot be bypassed by a state write.'))
        if vals.get('state') == 'cancelled' and any(e.account_move_id and e.account_move_id.state != 'cancel' for e in self):
            raise ValidationError(_('Resolve the native invoice before cancelling its obligation.'))
        if 'account_move_id' in vals:
            raise AccessError(_('Create invoices through the finance command.'))
        if {'company_id', 'currency_id', 'partner_id', 'amount', 'event_type', 'invoice_product_id', 'charge_owner'} & set(vals) and any(self.mapped('account_move_id')):
            raise ValidationError(_('Use native invoice corrections after invoicing.'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if any(v.get('account_move_id') for v in vals_list):
            raise AccessError(_('Invoice links are command-owned.'))
        return super().create(vals_list)

    def action_create_invoice(self):
        self.ensure_one()
        self._finance_actor()
        self.env.cr.execute('SELECT id FROM federation_finance_event WHERE id=%s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if self.account_move_id:
            return self.action_open_invoice()
        if self.state != 'confirmed' or self.event_type != 'charge' or self.amount <= 0:
            raise ValidationError(_('Only confirmed positive charges can create customer invoices.'))
        if not self.partner_id or not self.invoice_product_id:
            raise ValidationError(_('Select the authorised payer and a configured accounting product.'))
        if self.charge_owner == 'club' and not self.club_id:
            raise ValidationError(_('A club charge needs a club.'))
        if self.company_id not in self.env.companies:
            raise AccessError(_('The invoice company is outside your scope.'))
        move = self.env['account.move'].with_company(self.company_id).create({
            'move_type': 'out_invoice', 'partner_id': self.partner_id.id,
            'company_id': self.company_id.id, 'currency_id': self.currency_id.id,
            'invoice_origin': self.name,
            'invoice_line_ids': [fields.Command.create({'product_id': self.invoice_product_id.id,
                'name': self.name, 'quantity': 1, 'price_unit': self.amount})]})
        super().write({'account_move_id': move.id})
        return self.action_open_invoice()

    def action_open_invoice(self):
        self.ensure_one()
        self.account_move_id.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move',
                'res_id': self.account_move_id.id, 'view_mode': 'form', 'target': 'current'}

    def action_settle(self):
        for event in self:
            if event.account_move_id and (event.account_move_id.state != 'posted' or event.account_move_id.payment_state != 'paid'):
                raise ValidationError(_('Settle only after the native invoice is posted and fully paid.'))
        return super().action_settle()

    def action_cancel(self):
        if any(e.account_move_id and e.account_move_id.state != 'cancel' for e in self):
            raise ValidationError(_('Resolve the invoice or credit-note workflow in Accounting first.'))
        return super().action_cancel()
