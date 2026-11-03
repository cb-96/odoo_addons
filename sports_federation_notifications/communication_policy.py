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
