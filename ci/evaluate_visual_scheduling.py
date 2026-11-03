#!/usr/bin/env python3
"""Evaluate actual novice observations and executed integrity tests; missing evidence fails."""
import argparse
import json
import math
from pathlib import Path
from statistics import median

REQUIRED = ('scope', 'unavailable_slot', 'venue_blackout', 'occupied_slot', 'team_overlap',
            'mandatory_rest', 'unresolved_participants', 'stale_preview', 'published_immutability', 'pinned_regeneration')


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def evaluate(data):
    users = data.get('novices', [])
    ids = [row.get('participant') for row in users]
    distinct = len(users) >= 10 and all(ids) and len(set(ids)) == len(ids)
    complete = sum(row.get('completed') is True and row.get('assisted') is False for row in users)
    rules = sum(row.get('hard_vs_preference_correct') is True for row in users)
    affected = sum(row.get('affected_fixtures_correct') is True for row in users)
    timings = data.get('paired_timings', [])
    timing_ids = [row.get('participant') for row in timings]
    timing_valid = (len(timings) >= 10 and all(timing_ids) and len(set(timing_ids)) == len(timing_ids)
                    and all(row.get('baseline_completed') is True and row.get('candidate_completed') is True
                            and positive(row.get('baseline_seconds')) and positive(row.get('candidate_seconds')) for row in timings))
    reduction = 1 - median(row['candidate_seconds'] for row in timings) / median(row['baseline_seconds'] for row in timings) if timing_valid else None
    suite = data.get('integrity', {})
    executed = all(suite.get(name, {}).get('executed', 0) > 0 for name in REQUIRED)
    violations = executed and all(suite[name].get('accepted_hard_violations') == 0 for name in REQUIRED)
    pins = executed and suite['pinned_regeneration'].get('unintended_pin_changes') == 0
    gates = {'novice_completion_80_percent': distinct and complete / len(users) >= .8,
             'hard_vs_preference_90_percent': distinct and rules / len(users) >= .9,
             'affected_fixtures_90_percent': distinct and affected / len(users) >= .9,
             'median_planning_time_improves_30_percent': timing_valid and reduction >= .3,
             'zero_accepted_hard_violations': bool(violations), 'zero_unintended_pin_changes': bool(pins)}
    return {'passed': all(gates.values()), 'gates': gates, 'median_time_reduction': reduction,
            'note': 'Only real observations and executed tests establish acceptance. Policy tests are not novice usability evidence.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.observations.read_text()))
    text = json.dumps(result, indent=2)
    if args.output: args.output.write_text(text + '\n')
    print(text)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
