"""Pure member presentation and reviewed matching policy."""
import hashlib
import json
import unicodedata


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def normal_name(value):
    return ' '.join(unicodedata.normalize('NFKC', value or '').casefold().split())


def match_candidate(first, last, birthdate, candidate):
    return bool(birthdate and candidate.get('birthdate') and str(birthdate) == str(candidate['birthdate'])
                and normal_name(first) == normal_name(candidate.get('first_name'))
                and normal_name(last) == normal_name(candidate.get('last_name')))


def membership_label(state):
    return {'draft': 'Requested: federation review required', 'active': 'Active membership',
            'cancelled': 'Cancelled membership'}.get(state, 'Action needed: membership state not recognised')


def licence_valid(licence, today, club_id, season_id):
    return bool(licence and licence['state'] == 'active' and licence['club_id'] == club_id
                and licence['season_id'] == season_id and licence['issue_date'] <= today <= licence['expiry_date'])
