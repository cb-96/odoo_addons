import json
from odoo import _, fields, models
from odoo.exceptions import ValidationError
from .membership import manager
from ..cohorts import compare_cohorts


class GrowthReport(models.TransientModel):
    _name = 'federation.membership.cohort.report'
    _description = 'Membership and Club Retention Comparison'
    previous_season_id = fields.Many2one('federation.season', required=True)
    current_season_id = fields.Many2one('federation.season', required=True)
    club_id = fields.Many2one('federation.club')
    summary = fields.Text(readonly=True)

    def action_compare(self):
        self.ensure_one()
        manager(self.env)
        if self.current_season_id.date_start <= self.previous_season_id.date_start:
            raise ValidationError(_('Choose two seasons in chronological order.'))
        domain = [('state', '=', 'active')]
        if self.club_id:
            domain.append(('club_id', '=', self.club_id.id))
        memberships = self.env['federation.person.membership']
        previous = memberships.search(domain + [('season_id', '=', self.previous_season_id.id)])
        current = memberships.search(domain + [('season_id', '=', self.current_season_id.id)])
        self.summary = json.dumps({
            'definition': 'Distinct people and clubs with active membership records; not proof of match participation.',
            'members': compare_cohorts(previous.person_id.ids, current.person_id.ids),
            'clubs': compare_cohorts(previous.club_id.ids, current.club_id.ids),
            'scope': self.club_id.name or 'All accessible clubs',
        }, indent=2)
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'new'}
