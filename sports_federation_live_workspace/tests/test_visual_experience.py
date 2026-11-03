from odoo.tests.common import TransactionCase, HttpCase, tagged
from odoo.exceptions import AccessError, ValidationError
from .test_commands import LiveFixture


@tagged('post_install', '-at_install', 'sf_visual_scheduling')
class TestVisualExperience(LiveFixture, TransactionCase):
    def setUp(self):
        super().setUp()
        self.plan = self.env['federation.visual.planning']
        self.fixture = self.schedule.available_fixture_ids[0]

    def test_event_constraint_uses_shared_timezone(self):
        from odoo.addons.sports_federation_calendar.time_policy import local_to_utc
        timezone = self.schedule.matchday_id.event_timezone
        self.env.user.tz = 'Pacific/Honolulu'
        values = {'name': 'Event time test', 'kind': 'court_window',
                  'court_id': self.planning_slot.court_id.id,
                  'start': '2026-11-03T10:00', 'end': '2026-11-03T11:00'}
        data = self.plan.create_event_constraint(self.schedule.id, self.schedule.revision, values)
        constraint = self.env['federation.visual.constraint'].search([
            ('schedule_id', '=', self.schedule.id), ('name', '=', values['name'])])
        self.assertEqual(constraint.start, local_to_utc(values['start'], timezone))
        self.assertEqual(data['timezone'], timezone)

    def test_event_constraint_rejects_stale_revision_and_extra_fields(self):
        with self.assertRaises(ValidationError):
            self.plan.create_event_constraint(self.schedule.id, self.schedule.revision + 1, {})
        with self.assertRaises(ValidationError):
            self.plan.create_event_constraint(self.schedule.id, self.schedule.revision, {'active': False})

    def test_event_timezone_locked_after_scheduling(self):
        self.schedule.matchday_id.state = 'scheduled'
        timezone = 'Europe/Brussels' if self.schedule.matchday_id.event_timezone != 'Europe/Brussels' else 'UTC'
        with self.assertRaises(ValidationError):
            self.schedule.matchday_id.event_timezone = timezone

    def test_historical_timezone_review_preserves_slots(self):
        day = self.schedule.matchday_id
        slots = [(slot.id, slot.start_datetime, slot.end_datetime) for slot in day.slot_ids]
        self.env.cr.execute('UPDATE federation_matchday SET event_timezone_reviewed=false WHERE id=%s', [day.id])
        day.invalidate_recordset(['event_timezone_reviewed'])
        day._review_event_timezone('Europe/Brussels', 'Venue event record confirms Brussels time')
        self.assertTrue(day.event_timezone_reviewed)
        self.assertEqual(day.event_timezone, 'Europe/Brussels')
        self.assertEqual(slots, [(slot.id, slot.start_datetime, slot.end_datetime) for slot in day.slot_ids])

    def test_event_display_ignores_user_timezone(self):
        self.env.user.tz = 'Pacific/Honolulu'
        text = self.env['federation.event.time'].display('2026-11-03 09:00:00', self.schedule.matchday_id)
        self.assertIn(self.schedule.matchday_id.event_timezone, text)

    def test_timezone_review_requires_calendar_authority(self):
        public = self.env.ref('base.public_user')
        with self.assertRaises(AccessError):
            self.schedule.matchday_id.with_user(public)._review_event_timezone('Europe/Brussels', 'Forged review')

    def test_timezone_review_requires_evidence(self):
        with self.assertRaises(ValidationError):
            self.schedule.matchday_id._review_event_timezone('Europe/Brussels', '')

    def _destinations(self):
        return self.plan.destinations(self.schedule.id, self.fixture.id, self.plan.load(self.schedule.id)['signature'])

    def _move(self, slot):
        return self.plan.preview(self.schedule.id, 'move', self.fixture.id, slot.id)

    def _another_fixture(self):
        return self.env['federation.fixture'].create({
            'structure_id': self.fixture.structure_id.id, 'stage_id': self.fixture.stage_id.id,
            'round_number': self.fixture.round_number, 'sequence': self.fixture.sequence + 100,
            'home_team_id': self.fixture.home_team_id.id, 'away_team_id': self.fixture.away_team_id.id,
            'state': 'ready'})

    def test_destinations_are_read_only(self):
        before = self.schedule.revision
        self._destinations()
        self.assertEqual(self.schedule.revision, before)
        self.assertFalse(self.schedule.assignment_ids)

    def test_available_destination(self):
        rows = self._destinations()['slots']
        self.assertTrue(next(row for row in rows if row['slot_id'] == self.planning_slot.id)['valid'])

    def test_unavailable_destination(self):
        self.planning_slot.state = 'blocked'
        row = next(row for row in self._destinations()['slots'] if row['slot_id'] == self.planning_slot.id)
        self.assertFalse(row['valid'])
        self.assertTrue(all(issue['severity'] == 'mandatory' and issue['hint'] for issue in row['errors']))

    def test_court_window_blocks_destination_and_apply(self):
        self.env['federation.visual.constraint'].create({'schedule_id': self.schedule.id, 'name': 'Court unavailable',
            'kind': 'court_window', 'court_id': self.planning_slot.court_id.id,
            'start': self.planning_slot.start_datetime, 'end': self.planning_slot.end_datetime})
        row = next(row for row in self._destinations()['slots'] if row['slot_id'] == self.planning_slot.id)
        self.assertFalse(row['valid'])
        with self.assertRaises(ValidationError):
            self.plan.apply(self._move(self.planning_slot)['id'], 'Must not bypass court closure')

    def test_team_window_blocks_apply(self):
        self.env['federation.visual.constraint'].create({'schedule_id': self.schedule.id, 'name': 'Team unavailable',
            'kind': 'team_window', 'team_id': self.fixture.home_team_id.id,
            'start': self.planning_slot.start_datetime, 'end': self.planning_slot.end_datetime})
        with self.assertRaises(ValidationError):
            self.plan.apply(self._move(self.planning_slot)['id'], 'Must not bypass team window')

    def test_occupied_slot_never_silently_swaps(self):
        other = self._another_fixture()
        self.plan.apply(self.plan.preview(self.schedule.id, 'move', other.id, self.planning_slot.id)['id'], 'Pin first fixture')
        row = next(row for row in self._destinations()['slots'] if row['slot_id'] == self.planning_slot.id)
        self.assertFalse(row['valid'])
        self.assertIn('slot_occupied', [issue['code'] for issue in row['errors']])
        self.assertEqual(self.schedule.assignment_ids[0].fixture_id, other)

    def test_team_overlap_across_courts_is_blocked(self):
        other = self._another_fixture()
        court = self.env['federation.playing.area'].create({'name': 'Second planning court', 'venue_id': self.planning_matchday.venue_id.id})
        simultaneous = self.env['federation.schedule.slot'].create({'matchday_id': self.planning_matchday.id,
            'court_id': court.id, 'start_datetime': self.planning_slot.start_datetime, 'end_datetime': self.planning_slot.end_datetime})
        self.plan.apply(self.plan.preview(self.schedule.id, 'move', other.id, self.planning_slot.id)['id'], 'Pin first game')
        candidate = self._move(simultaneous)
        self.assertIn('team_overlap', [issue['code'] for issue in candidate['after']['validation']['errors']])
        with self.assertRaises(ValidationError): self.plan.apply(candidate['id'], 'No overlapping team games')

    def test_preferred_rest_warning_is_not_mandatory(self):
        other = self._another_fixture()
        self.schedule.preferred_rest_minutes = 120
        self.plan.apply(self.plan.preview(self.schedule.id, 'move', other.id, self.planning_slot.id)['id'], 'Pin first game')
        candidate = self._move(self.second_slot)
        self.assertFalse(candidate['after']['validation']['errors'])
        warnings = candidate['after']['validation']['warnings']
        self.assertTrue(warnings)
        self.assertTrue(all(issue['severity'] == 'preference' for issue in warnings))
        self.plan.apply(candidate['id'], 'Accept preference tradeoff, not a mandatory violation')

    def test_mandatory_rest_blocks_same_candidate(self):
        other = self._another_fixture()
        self.plan.apply(self.plan.preview(self.schedule.id, 'move', other.id, self.planning_slot.id)['id'], 'Pin first game')
        self.env['federation.visual.constraint'].create({'schedule_id': self.schedule.id, 'name': 'Mandatory rest', 'kind': 'minimum_rest', 'minutes': 120})
        candidate = self._move(self.second_slot)
        self.assertIn('minimum_rest', [issue['code'] for issue in candidate['after']['validation']['errors']])
        with self.assertRaises(ValidationError): self.plan.apply(candidate['id'], 'No rest bypass')

    def test_stale_destination_signature_rejected(self):
        signature = self.plan.load(self.schedule.id)['signature']
        self.plan.apply(self._move(self.planning_slot)['id'], 'Change schedule')
        with self.assertRaises(ValidationError): self.plan.destinations(self.schedule.id, self.fixture.id, signature)

    def test_stale_preview_request_rejected(self):
        signature = self.plan.load(self.schedule.id)['signature']
        self.plan.apply(self._move(self.planning_slot)['id'], 'Change schedule')
        with self.assertRaises(ValidationError): self.plan.preview(self.schedule.id, 'move', self.fixture.id, self.second_slot.id, signature)

    def test_compare_does_not_apply(self):
        first, second = self._move(self.planning_slot), self._move(self.second_slot)
        result = self.plan.compare(first['id'], second['id'])
        self.assertEqual(result['changes'][0]['fixture_id'], self.fixture.id)
        self.assertFalse(self.schedule.assignment_ids)

    def test_same_preview_comparison_rejected(self):
        first = self._move(self.planning_slot)
        with self.assertRaises(ValidationError): self.plan.compare(first['id'], first['id'])

    def test_stale_comparison_rejected(self):
        first, second = self._move(self.planning_slot), self._move(self.second_slot)
        self.plan.apply(first['id'], 'Apply candidate A')
        with self.assertRaises(ValidationError): self.plan.compare(first['id'], second['id'])

    def test_foreign_preview_comparison_rejected(self):
        first, second = self._move(self.planning_slot), self._move(self.second_slot)
        with self.assertRaises(AccessError): self.plan.with_user(self.operator).compare(first['id'], second['id'])

    def test_impact_separates_changed_and_shared_team(self):
        other = self._another_fixture()
        impact = self._move(self.planning_slot)['impact']
        groups = {group['kind']: [fixture['id'] for fixture in group['fixtures']] for group in impact['groups']}
        self.assertEqual(groups['changed'], [self.fixture.id])
        self.assertIn(other.id, groups['shared_teams'])
        self.assertFalse(self.schedule.assignment_ids)

    def test_impact_is_persisted_with_candidate(self):
        candidate = self._move(self.planning_slot)
        record = self.env['federation.visual.proposal'].sudo().browse(candidate['id'])
        self.assertEqual(record.comparison['impact'], candidate['impact'])
        self.assertEqual(record.comparison['operation'], 'move')

    def test_regeneration_retains_pin(self):
        self.plan.apply(self._move(self.planning_slot)['id'], 'Pin manually')
        candidate = self.plan.preview(self.schedule.id, 'regenerate')
        self.assertFalse(candidate['impact']['pin_changes'])
        self.plan.apply(candidate['id'], 'Regenerate without moving pins')
        self.assertEqual(self.schedule.assignment_ids.filtered(lambda a: a.fixture_id == self.fixture).slot_id, self.planning_slot)

    def test_published_destinations_denied(self):
        published = self.publication.schedule_id
        with self.assertRaises(ValidationError):
            self.plan.destinations(published.id, published.assignment_ids[0].fixture_id.id, self.plan.load(published.id)['signature'])

    def test_amendment_keeps_publication_snapshot(self):
        published = self.publication.schedule_id
        before = self.publication.assignment_snapshot
        self.matchday.write({'state': 'closed', 'active_session_id': False})
        action = self.plan.amend(published.id, 'Reasoned visual amendment')
        replacement = self.env['federation.schedule'].browse(action['params']['schedule_id'])
        self.assertEqual(replacement.supersedes_id, published)
        self.assertEqual(replacement.state, 'changes_requested')
        self.assertEqual(self.publication.assignment_snapshot, before)


@tagged('post_install', '-at_install', 'sf_visual_scheduling')
class TestVisualBrowser(LiveFixture, HttpCase):
    def _action(self):
        return self.env['ir.actions.client'].create({'name': 'Visual experience test', 'tag': 'federation_visual_plan',
                                                    'context': repr({'active_id': self.schedule.id})})

    def test_destination_preview_and_focus(self):
        action = self._action()
        self.browser_js('/odoo/action-%s' % action.id, '''
(async () => {
    const wait = async (fn) => { for(let i=0;i<300;i++){ if(fn())return; await new Promise(r=>setTimeout(r,100)); } throw Error('Timed out'); };
    await wait(()=>document.querySelector('#visual-fixture'));
    const select=document.querySelector('#visual-fixture'); select.value=select.options[1].value;
    select.dispatchEvent(new Event('change',{bubbles:true}));
    await wait(()=>document.querySelector('[data-destination-button][aria-disabled="false"]'));
    const buttons=[...document.querySelectorAll('[data-destination-button]')];
    buttons[0].focus(); buttons[0].dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}));
    if(document.activeElement!==buttons.at(-1))throw Error('Keyboard destination navigation failed');
    document.querySelector('[data-destination-button][aria-disabled="false"]').click();
    await wait(()=>document.querySelector('[data-preview-heading]'));
    await wait(()=>document.activeElement===document.querySelector('[data-preview-heading]'));
    if(!document.querySelector('[data-visual-impact]').textContent.includes('Slot changes'))throw Error('Impact missing');
    console.log('test successful');
})().catch(error=>console.error(error));
''', login=self.operator.login, timeout=90)

    def test_drag_is_preview_only(self):
        fixture = self.schedule.available_fixture_ids[0]
        plan = self.env['federation.visual.planning']
        plan.apply(plan.preview(self.schedule.id, 'move', fixture.id, self.planning_slot.id)['id'], 'Prepare draggable fixture')
        revision = self.schedule.revision
        action = self._action()
        self.browser_js('/odoo/action-%s' % action.id, '''
(async () => {
    const wait = async (fn) => { for(let i=0;i<300;i++){ if(fn())return; await new Promise(r=>setTimeout(r,100)); } throw Error('Timed out'); };
    await wait(()=>document.querySelector('[data-fixture]'));
    const fixture=document.querySelector('[data-fixture]'); fixture.click();
    await wait(()=>document.querySelector('[data-destination-button][aria-disabled="false"]'));
    const transfer=new DataTransfer(); fixture.dispatchEvent(new DragEvent('dragstart',{dataTransfer:transfer,bubbles:true}));
    const target=[...document.querySelectorAll('[data-destination-button][aria-disabled="false"]')].find(button=>!button.textContent.includes('Current slot'));
    if(!target)throw Error('No alternate destination');
    target.closest('td').dispatchEvent(new DragEvent('drop',{dataTransfer:transfer,bubbles:true,cancelable:true}));
    await wait(()=>document.querySelector('[data-preview-heading]'));
    if(!document.querySelector('[data-visual-impact]'))throw Error('Drop bypassed preview');
    console.log('test successful');
})().catch(error=>console.error(error));
''', login=self.operator.login, timeout=90)
        self.schedule.invalidate_recordset()
        self.assertEqual(self.schedule.revision, revision)
