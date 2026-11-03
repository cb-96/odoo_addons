"""Read-only presentation policy shared by existing role workspaces."""
from datetime import timedelta

ROLE_ORDER = ('club', 'official', 'planner', 'reviewer', 'manager')
BUCKETS = ('now', 'soon', 'waiting', 'recent')


def choose_role(allowed, requested=None, remembered=None):
    """Never let a remembered or supplied responsibility grant access."""
    for role in (requested, remembered, *ROLE_ORDER):
        if role in allowed:
            return role
    return None


def bucket_for(*, complete=False, waiting=False, unavailable=False,
               deadline=None, now=None, blocking=False):
    if complete:
        return 'recent'
    if waiting or unavailable:
        return 'waiting'
    if blocking or not deadline or not now or deadline <= now:
        return 'now'
    # All open work remains visible; only the next seven days are "due soon".
    return 'soon' if deadline <= now + timedelta(days=7) else 'now'


def group_cards(cards):
    groups = {key: [] for key in BUCKETS}
    seen = set()
    for card in cards:
        key = card['key']
        if key in seen:
            continue
        seen.add(key)
        groups[card['bucket']].append(card)
    return groups


def participation_status(checks):
    """Unknown or waiting checks never become a green readiness certificate."""
    states = [check['state'] for check in checks]
    if 'action' in states:
        return 'action'
    if 'waiting' in states:
        return 'waiting'
    if not states or 'unknown' in states:
        return 'unknown'
    return 'complete'
