from odoo import _, api, models
from odoo.exceptions import AccessError, ValidationError
from ..visual_policy import impact_sets, pin_changes

HINTS = {
    'scope': 'Choose a fixture and slot from this schedule.',
    'fixture_not_ready': 'Resolve or advance the fixture before assigning it.',
    'participants_unresolved': 'Resolve both participants through the existing progression workflow.',
    'court_scope': 'Choose a court belonging to this match day and venue.',
    'slot_occupied': 'Move the existing fixture first or choose an empty slot. Dropping never silently swaps fixtures.',
    'slot_unavailable': 'Choose an available slot or correct its calendar availability.',
    'invalid_window': 'Correct the slot start and end times in calendar capacity.',
    'venue_blackout': 'Choose a slot outside the venue or court blackout window.',
    'team_overlap': 'Move one of the affected fixtures to a non-overlapping time.',
    'rest_shortfall': 'Prefer a later slot to improve rest. This is a preference, not a mandatory minimum.',
    'team_window': 'Choose a time outside the recorded team-unavailable window.',
    'court_window': 'Choose another court or a time outside the court-unavailable window.',
    'minimum_rest': 'Leave the configured mandatory rest interval between games.',
    'fixture_outside_calendar_plan': 'Correct the match-day allocation before scheduling this fixture.',
}


class VisualExperience(models.AbstractModel):
    _inherit = 'federation.visual.planning'

    def _schedule(self, schedule_id, mutable=False):
        schedule = super()._schedule(schedule_id, mutable)
        if mutable:
            # Constraints, preview generation and application share the schedule lock.
            self.env.cr.execute('SELECT id FROM federation_schedule WHERE id=%s FOR UPDATE', [schedule.id])
            schedule.invalidate_recordset()
            schedule.assert_mutable()
        return schedule

    def _structures(self, schedule):
        return schedule.structure_id | schedule.matchday_id.allocation_ids.mapped('structure_id')

    def _signature(self, schedule):
        # Topology and downstream participant changes also invalidate impact previews.
        from ..policy import digest
        fixtures = self.env['federation.fixture'].search([('structure_id', 'in', self._structures(schedule).ids)])
        return digest({'base': super()._signature(schedule),
                       'progression': [(f.id, f.stage_id.id, f.state, f.home_team_id.id, f.away_team_id.id, f.home_source_fixture_id.id, f.away_source_fixture_id.id,
                                        f.home_source_outcome, f.away_source_outcome, str(f.write_date)) for f in fixtures],
                       'stages': [(stage.id, stage.graph_state, stage.format_type, stage.sequence, str(stage.write_date)) for stage in self._structures(schedule).stage_ids],
                       'stage_edges': [(p.id, p.active, p.source_stage_id.id, p.target_stage_id.id, p.rank_from, p.rank_to, str(p.write_date))
                                       for p in self._structures(schedule).stage_ids.mapped('outgoing_progression_ids')]})

    def _issue_details(self, issue, severity):
        return {**issue, 'severity': severity, 'hint': _(HINTS.get(issue.get('code'), 'Inspect the affected fixture and current schedule rules.'))}

    def _explain(self, schedule, candidate):
        explanation = super()._explain(schedule, candidate)
        validation = explanation['validation']
        validation['errors'] = [self._issue_details(issue, 'mandatory') for issue in validation['errors']]
        validation['warnings'] = [self._issue_details(issue, 'preference') for issue in validation['warnings']]
        for unallocated in explanation['unallocated']:
            for attempt in unallocated['attempts']:
                attempt['errors'] = [self._issue_details(issue, 'mandatory') for issue in attempt['errors']]
        return explanation

    def _topology(self, schedule):
        fixtures = self.env['federation.fixture'].search([('structure_id', 'in', self._structures(schedule).ids)])
        return ([{'id': f.id, 'name': f.display_name, 'stage_id': f.stage_id.id,
                  'teams': (f.home_team_id | f.away_team_id).ids,
                  'home_source': f.home_source_fixture_id.id, 'away_source': f.away_source_fixture_id.id} for f in fixtures],
                [{'id': stage.id, 'next': [{'id': p.target_stage_id.id} for p in stage.outgoing_progression_ids if p.active]}
                 for stage in self._structures(schedule).stage_ids])

    def _impact(self, schedule, before, after, methods):
        fixtures, stages = self._topology(schedule)
        changed = sorted(fid for fid in set(before) | set(after) if before.get(fid) != after.get(fid))
        sets = impact_sets(changed, fixtures, stages)
        names = {f['id']: f['name'] for f in fixtures}
        reasons = {'changed': _('Slot changes in this candidate'), 'shared_teams': _('Shared team: inspect rest and overlap'),
                   'fixture_dependants': _('Winner/loser input depends on a changed fixture'),
                   'stage_dependants': _('Potential qualification dependency through stage progression')}
        return {'groups': [{'kind': kind, 'label': reasons[kind],
                            'fixtures': [{'id': fid, 'name': names.get(fid, str(fid))} for fid in ids]} for kind, ids in sets.items()],
                'changed_count': len(changed), 'pin_changes': pin_changes(before, after, methods),
                'note': _('Only the listed slot changes are applied. Other fixtures are review impacts, not automatic moves or participant predictions.')}

    @api.model
    def load(self, schedule_id):
        data = super().load(schedule_id)
        schedule = self._schedule(schedule_id)
        available = set(schedule.available_fixture_ids.ids)
        topology, _stages = self._topology(schedule)
        fixture_ids = {fixture['id'] for fixture in topology}
        data['fixtures'] = [fixture for fixture in data['fixtures'] if fixture['id'] in fixture_ids]
        data['stages'] = [{'id': stage.id, 'name': stage.name, 'format': stage.format_type, 'state': stage.graph_state,
                           'next': [{'id': edge.target_stage_id.id, 'rank_from': edge.rank_from, 'rank_to': edge.rank_to}
                                    for edge in stage.outgoing_progression_ids if edge.active]}
                          for stage in self._structures(schedule).stage_ids.sorted(lambda stage: (stage.sequence, stage.id))]
        try:
            self._schedule(schedule_id, True)
            data['can_edit'] = True
        except (AccessError, ValidationError):
            data['can_edit'] = False
        for fixture in data['fixtures']:
            fixture['allocated'] = fixture['id'] in available
        data['timezone'] = self.env.user.tz or 'UTC'
        data['governance'] = _('Working changes need an exact preview and reason. Applying is not publication. Published schedules require a linked amendment and independent review.')
        data['hard_rules'] = [_('Slot and court availability'), _('No double-booked slots or overlapping teams'),
                              _('Resolved and ready participants'), _('Recorded team/court windows and mandatory minimum rest')]
        data['preference_rules'] = [_('Preferred rest interval'), _('Fairness penalties for club, consecutive games, time and court balance')]
        return data

    @api.model
    def destinations(self, schedule_id, fixture_id, signature):
        schedule = self._schedule(schedule_id, True)
        if signature != self._signature(schedule):
            raise ValidationError(_('The schedule changed. Refresh before selecting a destination.'))
        fid = int(fixture_id)
        if fid not in schedule.available_fixture_ids.ids:
            raise ValidationError(_('Select an allocated fixture from this match day.'))
        before = self._map(schedule)
        validator = self.env['federation.schedule.validator']
        rows = []
        for slot in schedule.matchday_id.slot_ids:
            candidate = dict(before)
            candidate[fid] = slot.id
            validation = validator.validate_map(schedule, candidate)
            errors = [self._issue_details(issue, 'mandatory') for issue in validation['errors']]
            warnings = [self._issue_details(issue, 'preference') for issue in validation['warnings']]
            rows.append({'slot_id': slot.id, 'valid': not errors, 'errors': errors, 'warnings': warnings,
                         'unchanged': before.get(fid) == slot.id})
        return {'signature': signature, 'fixture_id': fid, 'slots': rows}

    @api.model
    def preview(self, schedule_id, operation, fixture_id=False, slot_id=False, signature=None):
        schedule = self._schedule(schedule_id, True)
        if signature is not None and signature != self._signature(schedule):
            raise ValidationError(_("The schedule changed. Refresh before previewing this move."))
        result = super().preview(schedule_id, operation, fixture_id, slot_id)
        proposal = self.env['federation.visual.proposal'].sudo().browse(result['id'])
        before = self._map(proposal.schedule_id)
        after = {int(k): int(v) for k, v in proposal.candidate.items()}
        methods = {a.fixture_id.id: a.method for a in proposal.schedule_id.assignment_ids}
        impact = self._impact(proposal.schedule_id, before, after, methods)
        if operation == 'regenerate' and impact['pin_changes']:
            raise ValidationError(_('Regeneration attempted to change pinned assignments. Nothing was applied.'))
        result.update(operation=operation, signature=proposal.signature, revision=proposal.revision, impact=impact)
        return result

    @api.model
    def compare(self, first_id, second_id):
        if int(first_id) == int(second_id):
            raise ValidationError(_('Choose two distinct candidates.'))
        proposals = self.env['federation.visual.proposal'].sudo().browse([int(first_id), int(second_id)]).exists()
        if len(proposals) != 2 or any(p.actor_id != self.env.user for p in proposals):
            raise AccessError(_('Choose two of your own distinct previews.'))
        first, second = proposals
        if first.schedule_id != second.schedule_id or first.signature != second.signature or first.revision != second.revision:
            raise ValidationError(_('Compare candidates from the same unchanged schedule revision.'))
        schedule = self._schedule(first.schedule_id.id)
        if self._signature(schedule) != first.signature or first.applied or second.applied:
            raise ValidationError(_('The comparison is stale or already applied. Generate fresh candidates.'))
        maps = [{int(k): int(v) for k, v in p.candidate.items()} for p in (first, second)]
        return {'first': first.id, 'second': second.id,
                'changes': [{'fixture_id': fid, 'first_slot': maps[0].get(fid, False), 'second_slot': maps[1].get(fid, False)}
                            for fid in sorted(set(maps[0]) | set(maps[1])) if maps[0].get(fid) != maps[1].get(fid)],
                'first_quality': self._explain(schedule, maps[0]), 'second_quality': self._explain(schedule, maps[1])}
