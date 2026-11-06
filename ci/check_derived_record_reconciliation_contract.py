#!/usr/bin/env python3
"""Static contract tying reconciliation reporting to release invariants."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
service=(ROOT/'sports_federation_app/models/derived_record_reconciliation.py').read_text()
contract=json.loads((ROOT/'ci/release_invariants.json').read_text())
required={
 'finalized_participant_teams_without_participants',
 'resolved_playable_fixtures_without_matches',
 'matches_without_expected_team_match_sheets',
 'published_matches_without_published_slot',
 'published_matches_without_venue_or_playing_area',
 'multiple_active_primary_rosters',
 'retired_competition_engine_not_upgradeable',
 'retired_engine_legacy_tables_remaining',
}
missing=required-set(contract['zero_checks'])
assert not missing, f'missing release invariants: {sorted(missing)}'
for token in ('HEALTHY = "healthy"','MISSING = "missing"','ORPHANED = "orphaned"','CONFLICTING = "conflicting"','def report(','def repair('):
    assert token in service, f'missing reconciliation contract token {token}'
print('Derived-record reconciliation contract passed.')
