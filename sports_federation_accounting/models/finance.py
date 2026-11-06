from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class Finance(models.Model):
    _inherit = 'federation.finance.event'
    account_move_id = fields.Many2one('account.move', readonly=True, copy=False, ondelete='restrict', check_company=True)
    invoice_product_id = fields.Many2one('product.product', check_company=True)
    charge_owner = fields.Selection([('federation', 'Federation'), ('club', 'Club')], default='federation', required=True)
    invoice_currency_id = fields.Many2one(related='account_move_id.currency_id')
    invoice_balance = fields.Monetary(related='account_move_id.amount_residual', currency_field='invoice_currency_id')
    invoice_payment_state = fields.Selection(related='account_move_id.payment_state')

    def _finance_actor(self):
        if not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_('Invoice administration permission is required.'))
        self.check_access('write')

    def _invoice_resolved(self):
        self.ensure_one()
        move = self.account_move_id
        if not move:
            return self.state != 'settled'
        move.check_access('read')
        if move.state == 'cancel':
            return True
        if move.state != 'posted' or move.payment_state != 'reversed':
            return False
        credits = self.env['account.move'].search([
            ('reversed_entry_id', '=', move.id), ('state', '=', 'posted'), ('move_type', '=', 'out_refund'),
            ('company_id', '=', move.company_id.id), ('currency_id', '=', move.currency_id.id), ('partner_id', '=', move.partner_id.id)])
        return bool(credits) and move.currency_id.is_zero(sum(credits.mapped('amount_total')) - move.amount_total)

    def write(self, vals):
        self._finance_lock()
        if vals.get('state') == 'settled':
            self._finance_actor()
            if any(e.event_type == 'charge' and (not e.account_move_id or e.account_move_id.state != 'posted' or e.account_move_id.payment_state != 'paid') for e in self):
                raise ValidationError(_('Settle customer charges only after a posted and fully paid native invoice.'))
        if vals.get('state') == 'cancelled' and any(not e._invoice_resolved() for e in self):
            raise ValidationError(_('Cancel the draft invoice or fully reverse the posted invoice first.'))
        if 'account_move_id' in vals:
            raise AccessError(_('Create invoices through the finance command.'))
        if {'company_id', 'currency_id', 'partner_id', 'amount', 'event_type', 'invoice_product_id', 'charge_owner', 'invoice_ref'} & set(vals) and any(self.mapped('account_move_id')):
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
        self._finance_actor()
        self._check_company()
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
        super().write({'account_move_id': move.id, 'invoice_ref': str(move.id)})
        return self.action_open_invoice()

    def action_open_invoice(self):
        self.ensure_one()
        self.account_move_id.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move',
                'res_id': self.account_move_id.id, 'view_mode': 'form', 'target': 'current'}

    def action_settle(self):
        self._finance_lock()
        self._finance_actor()
        if any(e.state != 'confirmed' for e in self):
            raise ValidationError(_('Only confirmed obligations can be settled.'))
        return self.write({'state': 'settled'})

    def action_cancel(self):
        self._finance_lock()
        self._finance_actor()
        return self._write_handoff({'state': 'cancelled', 'handoff_state': 'closed',
                                   'closed_on': fields.Datetime.now(), 'closed_by_id': self.env.uid})
