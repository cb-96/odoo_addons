from odoo import _, fields, http
from odoo.http import request
from .role_journeys import RoleJourneys, JourneyInbox, JourneyManagerQueue
from .preparation_journey import ClubPreparationJourney
from .officiating import FederationOfficiatingPortal
from odoo.addons.sports_federation_rosters.models.roster_line import _get_parental_approval_reasons
from ..journey_cards import choose_role, bucket_for, group_cards, participation_status


ROLE_LABELS = {
    'club': 'Club and team preparation', 'official': 'My official assignments',
    'planner': 'Competition planning', 'reviewer': 'Result review',
    'manager': 'Manager work queue',
}
ROLE_URLS = {
    'club': '/my/preparation', 'official': '/my/referee-assignments',
    'planner': '/odoo/action-sports_federation_setup_flow.action_competition_setup_home',
    'reviewer': '/my/work/reviews', 'manager': '/federation/operations/action-items',
}


def task_cards(tasks, representatives=None):
    now = fields.Datetime.now()
    cards = []
    for task in tasks.with_context(journey_viewer_id=request.env.user.id):
        complete = task.state == 'done'
        unavailable = task.journey_status == 'unavailable'
        waiting = task.journey_status == 'waiting' or bool(
            task.assigned_user_id and task.assigned_user_id != request.env.user)
        owner = (task.assigned_user_id.display_name if task.assigned_user_id else
                 dict(task._fields['journey_owner'].selection).get(task.journey_owner))
        cards.append({
            'key': 'task:%s' % task.id, 'title': task.name, 'task': task, 'representatives': representatives,
            'url': task.journey_url, 'owner': owner or _('Owner not yet assigned'),
            'deadline': task.deadline, 'blocker': task.blocking_reason or '',
            'next_action': (_('View completed work') if complete else
                            _('Inspect current status') if unavailable else
                            _('View submission status') if waiting else
                            task.next_step or _('Open the task to continue')),
            'handoff': (_('This task is complete; source approval and eligibility remain separate checks.') if complete else
                        _('The source cannot be checked with your current access. No readiness is implied.') if unavailable else
                        _('Your work is handed over. The owner shown is responsible for the next decision.') if waiting else
                        _('Complete the linked action. Existing approval rules still apply.')),
            'bucket': bucket_for(complete=complete, waiting=waiting, unavailable=unavailable,
                                 deadline=task.deadline, now=now, blocking=task.blocking),
        })
    return cards


def review_cards(matches, controller):
    cards = []
    for match in matches:
        complete = match.result_state == 'approved'
        actionable = not complete and controller._can_review_match(match, request.env.user)
        cards.append({
            'key': 'result:%s' % match.id, 'title': match.display_name,
            'url': '/odoo/federation.match/%s' % match.id,
            'owner': (_('No further result decision') if complete else
                      _('Result validator') if match.result_state == 'submitted' else _('Result approver')),
            'deadline': False, 'blocker': (_('Independent review requires another authorised reviewer.') if not actionable and not complete else _('No recorded blocker')),
            'next_action': (_('View approved result') if complete else _('Verify submitted result') if match.result_state == 'submitted' else _('Approve verified result')),
            'handoff': _('Submission, verification and approval are separate decisions.'),
            'bucket': bucket_for(complete=complete, waiting=not actionable),
        })
    return cards


class ConnectedRoleJourneys(RoleJourneys):
    @http.route()
    def home(self, **kw):
        user = request.env.user
        model = request.env['federation.operation.task']
        federation_access = bool(model._portal_club_ids(user)) or bool(
            request.env['federation.referee']._portal_get_for_user(user=user)) or any(
                user.has_group(group) for group in (
                    'sports_federation_competition_core.group_competition_administrator',
                    'sports_federation_result_control.group_result_validator',
                    'sports_federation_result_control.group_result_approver',
                    'sports_federation_base.group_federation_manager'))
        if federation_access and kw.get('generic') != '1':
            return request.redirect('/my/work')
        return super().home(**kw)

    @http.route()
    def role_home(self, role=None, club=None, **kw):
        response = super().role_home(**kw)
        context = response.qcontext
        allowed = [key for key in ROLE_LABELS if context.get(key + '_access')]
        session_key = 'federation_journey_role:%s' % request.env.user.id
        if role and role not in allowed:
            return self._render_access_denied()
        selected = choose_role(allowed, role, request.session.get(session_key))
        if selected:
            request.session[session_key] = selected
        clubs = request.env['federation.club'].browse([])
        selected_club = None
        if selected == 'club':
            club_ids = request.env['federation.operation.task']._portal_club_ids(request.env.user)
            clubs = request.env['federation.portal.privilege'].portal_search(
                request.env['federation.club'], [('id', 'in', club_ids)], user=request.env.user)
            club_key = 'federation_journey_club:%s' % request.env.user.id
            if club is not None:
                try:
                    selected_club = int(club) if club else None
                except (ValueError, TypeError):
                    return self._render_access_denied()
                if selected_club and selected_club not in clubs.ids:
                    return self._render_access_denied()
            else:
                remembered = request.session.get(club_key)
                selected_club = remembered if remembered in clubs.ids else None
            request.session[club_key] = selected_club
        context.update(journey_clubs=clubs, journey_club=selected_club)
        cards = []
        if selected == 'club':
            model = request.env['federation.operation.task'].with_context(journey_viewer_id=request.env.user.id)
            tasks = request.env['federation.portal.privilege'].portal_search(
                model, model._portal_get_domain(request.env.user) + (
                    [('responsible_club_id', '=', selected_club)] if selected_club else []),
                user=request.env.user, order='id desc', limit=200)
            cards = task_cards(tasks)
            existing = {task.source_record_id for task in tasks if task.source_model == 'federation.competition.entry' and task.state != 'done'}
            for entry in model._journey_waiting_entries(user=request.env.user):
                if selected_club and entry.team_id.club_id.id != selected_club:
                    continue
                if entry.id not in existing:
                    cards.append({'key': 'entry:%s' % entry.id, 'title': entry.team_id.display_name,
                                  'url': '/my/competition-entries/%s' % entry.id,
                                  'owner': _('Federation registration reviewer'), 'deadline': False,
                                  'blocker': _('Awaiting an independent registration decision'),
                                  'next_action': _('View submission status'),
                                  'handoff': _('Submitted successfully. No resubmission is needed while review is pending.'),
                                  'bucket': 'waiting'})
        elif selected == 'manager':
            model = request.env['federation.operation.task']
            model.sync_for_user(user=request.env.user)
            cards = task_cards(model.search([('audience', '=', 'manager')], order='id desc', limit=200))
        elif selected == 'reviewer':
            states = ['approved']
            if request.env.user.has_group('sports_federation_result_control.group_result_validator'):
                states.append('submitted')
            if request.env.user.has_group('sports_federation_result_control.group_result_approver'):
                states.append('verified')
            cards = review_cards(request.env['federation.match'].search(
                [('result_state', 'in', states)], order='id desc', limit=100), self)
        elif selected == 'official':
            model = request.env['federation.match.referee']
            assignments = request.env['federation.portal.privilege'].portal_search(
                model, model._portal_get_domain(user=request.env.user) + [('publication_id', 'in', request.env['federation.matchday'].sudo().search([('current_publication_id.state', '=', 'live')]).mapped('current_publication_id').ids)], user=request.env.user,
                order='id desc', limit=100)
            cards = assignment_cards(assignments)
        elif selected == 'planner':
            for edition in request.env['federation.competition.edition'].search([], order='id desc', limit=50):
                data = edition.get_competition_planner_data()
                issue = data.get('current_issue') or {}
                cards.append({'key': 'edition:%s' % edition.id, 'title': edition.display_name,
                              'url': '/odoo/federation.competition.edition/%s' % edition.id,
                              'owner': issue.get('owner') or _('Competition organiser'),
                              'deadline': fields.Datetime.to_datetime(edition.date_start) if edition.date_start else False,
                              'blocker': issue.get('message') or _('No setup blocker recorded'),
                              'next_action': _('Continue: %s') % data['current_label'],
                              'handoff': _('The existing planner resumes at the first incomplete step. Publication still requires independent review.'),
                              'bucket': bucket_for(complete=data['complete'], waiting=issue.get('step') == 'publication', deadline=fields.Datetime.to_datetime(edition.date_start) if edition.date_start else None, now=fields.Datetime.now(), blocking=bool(issue))})
        context.update(journey_role=selected, journey_roles=[{'key': key, 'label': _(ROLE_LABELS[key])} for key in allowed],
                       journey_role_label=_(ROLE_LABELS[selected]) if selected else _('No federation responsibility assigned'),
                       journey_role_url=ROLE_URLS.get(selected), journey_groups=group_cards(cards),
                       journey_limit=200 if selected in ('club', 'manager') else 50 if selected == 'planner' else 100)
        return response

    @http.route()
    def review_work(self, **kw):
        response = super().review_work(**kw)
        if response.status_code == 200 and response.qcontext.get('matches') is not None:
            response.qcontext.update(journey_groups=group_cards(review_cards(response.qcontext['matches'], self)),
                                     journey_user_id=request.env.user.id)
        return response


class ConnectedClubInbox(JourneyInbox):
    @http.route()
    def portal_my_action_items(self, **kw):
        response = super().portal_my_action_items(**kw)
        if response.status_code == 200 and response.qcontext.get('tasks') is not None:
            response.qcontext['journey_groups'] = group_cards(task_cards(response.qcontext['tasks'], response.qcontext.get('representatives')))
        return response


class ConnectedManagerQueue(JourneyManagerQueue):
    @http.route()
    def manager_action_items(self, **kw):
        response = super().manager_action_items(**kw)
        if response.status_code == 200 and response.qcontext.get('tasks') is not None:
            response.qcontext.update(journey_groups=group_cards(task_cards(response.qcontext['tasks'], response.qcontext.get('representatives'))),
                                     journey_user_id=request.env.user.id)
        return response


def assignment_cards(assignments):
    cards = []
    for assignment in assignments:
        complete = assignment.state in ('done', 'cancelled')
        waiting = assignment.state == 'confirmed'
        cards.append({'key': 'assignment:%s' % assignment.id, 'title': assignment.match_id.display_name,
                      'url': '/my/referee-assignments/%s' % assignment.id,
                      'owner': _('You') if assignment.state == 'draft' else _('Match-day organiser'),
                      'deadline': assignment.confirmation_deadline,
                      'blocker': _('No recorded blocker'),
                      'next_action': _('Accept or decline assignment') if assignment.state == 'draft' else _('View assignment status'),
                      'handoff': _('Acceptance is recorded separately from eligibility, attendance and completion.'),
                      'bucket': bucket_for(complete=complete, waiting=waiting, deadline=assignment.confirmation_deadline, now=fields.Datetime.now())})
    return cards


class ConnectedOfficialQueue(FederationOfficiatingPortal):
    @http.route()
    def portal_my_referee_assignments(self, **kw):
        response = super().portal_my_referee_assignments(**kw)
        if getattr(response, 'qcontext', None) and response.qcontext.get('assignments') is not None:
            response.qcontext.update(journey_groups=group_cards(assignment_cards(response.qcontext['assignments'])),
                                     journey_user_id=request.env.user.id)
        return response


class ConnectedPreparation(ClubPreparationJourney):
    @http.route()
    def club_preparation(self, **kw):
        response = super().club_preparation(**kw)
        context = response.qcontext
        for row in context['rows']:
            roster = row['roster']
            checks = [dict(label=_('Registration'), state='complete', detail=_('Confirmed registration'),
                           url='/my/work/registrations/%s' % row['registration'].id)]
            roster_issues = roster._get_readiness_issues() if roster else []
            checks.append(dict(label=_('Roster'), state='action' if not roster or roster_issues else 'complete',
                               detail='\n'.join(roster_issues) if roster_issues else _('Create the roster from the existing registration.') if not roster else _('Current roster checks passed; match-day approval remains separate.'),
                               url='/my/rosters/%s' % roster.id if roster else '/my/work/registrations/%s' % row['registration'].id))
            player_issues = [reason for line in roster.line_ids for reason in line._get_eligibility_reasons()] if roster else []
            checks.append(dict(label=_('Player eligibility and licences'), state='unknown' if not roster or not roster.line_ids else 'action' if player_issues else 'complete',
                               detail='\n'.join(player_issues) if player_issues else _('Current roster-date checks passed.') if roster and roster.line_ids else _('Add players before eligibility can be checked.'),
                               url='/my/rosters/%s' % roster.id if roster else '/my/players'))
            sheet_model = request.env['federation.match.sheet']
            related = request.env['federation.portal.privilege'].portal_search(
                sheet_model, sheet_model._portal_get_domain(user=request.env.user) +
                [('roster_id', '=', roster.id), ('match_id.state', '!=', 'cancelled')],
                user=request.env.user) if roster else sheet_model.browse()
            lineup_state = ('unknown' if not related else 'action' if any(sheet.state == 'draft' for sheet in related)
                            else 'waiting' if any(sheet.state == 'submitted' for sheet in related) else 'complete')
            checks.append(dict(label=_('Lineups'), state=lineup_state,
                               detail=_('Submitted lineups await review.') if lineup_state == 'waiting' else _('Inspect the match-day lineup requirements and approval status.'), url='/my/match-sheets'))
            consent_issues = [reason for player in roster.line_ids.mapped('player_id')
                              for reason in _get_parental_approval_reasons(player, roster.team_id, roster._get_reference_date())] if roster else []
            checks.append(dict(label=_('Parental consent'), state='unknown' if not roster or not roster.line_ids else 'action' if consent_issues else 'complete',
                               detail='\n'.join(consent_issues) if consent_issues else _('Current roster-date parental-consent checks passed or are not required.') if roster and roster.line_ids else _('Add players before consent requirements can be checked.'), url='/my/players'))
            row.update(participation_checks=checks, participation_status=participation_status(checks))
        context['journey_user_id'] = request.env.user.id
        return response
