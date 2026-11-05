"""Pure communication policy. Delivery never establishes task completion."""
import hashlib

KINDS = ('schedule_change', 'official_response', 'document_returned', 'due_soon', 'delivery_failure')
MODES = ('immediate', 'digest', 'inbox')


def identity(event_key, user_id):
    return hashlib.sha256(('%s:%s' % (event_key, user_id)).encode()).hexdigest()


def merge_roles(routes):
    result = {}
    for user_id, role in routes:
        result.setdefault(user_id, set()).add(role)
    return {user: sorted(roles) for user, roles in result.items()}


def retry_delay(attempt):
    return min(60, 2 ** max(0, attempt))


def delivery_label(state):
    return {'pending': 'Waiting to queue', 'queued': 'Queued for email',
            'sent': 'Accepted by outbound mail server', 'failed': 'Delivery failed',
            'cancelled': 'Delivery cancelled', 'suppressed': 'Inbox only'}.get(state, 'Not checked')


# ---------------------------------------------------------------------------
# Actionable-notification lifecycle
#
# created -> queued -> delivered | failed -> seen -> acted upon
#                                       \-> expired | superseded
#
# "Delivered" means the outbound mail server accepted the message, or that the
# item is available in the participant's inbox. It is not proof of reading, and
# neither delivery nor "seen" ever establishes that the requirement was resolved:
# only "acted upon" does, and only when the underlying requirement is complete.
# ---------------------------------------------------------------------------
LIFECYCLE = (
    ('created', 'Created'), ('queued', 'Queued'), ('delivered', 'Delivered'),
    ('failed', 'Failed'), ('seen', 'Seen'), ('acted', 'Acted upon'),
    ('expired', 'Expired'), ('superseded', 'Superseded'),
)
CLOSED_LIFECYCLE = ('acted', 'expired', 'superseded')
DEFAULT_EXPIRY_DAYS = 30


def lifecycle_state(superseded=False, acted=False, expired=False, seen=False, delivery_states=()):
    """Return the one lifecycle state of a notification from its recorded facts."""
    states = set(delivery_states)
    if superseded:
        return 'superseded'
    if acted:
        return 'acted'
    if expired:
        return 'expired'
    if seen:
        return 'seen'
    if states & {'sent', 'suppressed'}:
        return 'delivered'
    if 'failed' in states:
        return 'failed'
    if states & {'pending', 'queued'}:
        return 'queued'
    return 'created'


def summarize_lifecycle(rows):
    """Summarise ``(kind, state, count)`` rows into totals and a resolution rate.

    The resolution rate is acted upon / (acted upon + expired + seen but still
    open): the share of finished or stalled notifications whose requirement was
    actually resolved. Notifications still in flight are not counted against it.
    """
    totals, by_kind = {}, {}
    for kind, state, count in rows:
        totals[state] = totals.get(state, 0) + count
        by_kind.setdefault(kind, {})[state] = by_kind.get(kind, {}).get(state, 0) + count
    acted = totals.get('acted', 0)
    stalled = totals.get('expired', 0) + totals.get('seen', 0)
    denominator = acted + stalled
    return {
        'totals': totals,
        'by_kind': by_kind,
        'seen_unresolved': totals.get('seen', 0),
        'resolution_rate': (acted / denominator) if denominator else None,
    }
