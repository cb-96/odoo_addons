#!/usr/bin/env python3
"""Evaluate real staging observations. Missing evidence is never a pass."""
import argparse
import json
from pathlib import Path


def evaluate(data):
    recipients = data.get('recipients', [])
    enough = len(recipients) >= 10
    understanding = sum(row.get('understands_action') is True for row in recipients)
    direct = sum(row.get('correct_task_without_search') is True for row in recipients)
    latencies = data.get('urgent_inbox_latency_seconds', [])
    permission = data.get('permission_tests', {})
    duplicate = data.get('duplicate_tests', {})
    baseline = data.get('manual_reminders_baseline')
    after = data.get('manual_reminders_after')
    valid_baseline = isinstance(baseline, (int, float)) and baseline > 0 and isinstance(after, (int, float)) and after >= 0
    reduction = 1 - after / baseline if valid_baseline else None
    gates = {
        'action_understanding': enough and understanding / len(recipients) >= .9,
        'correct_task_without_search': enough and direct / len(recipients) >= .9,
        'zero_unauthorised_recipients': permission.get('executed', 0) > 0 and permission.get('unauthorised_recipients') == 0,
        'zero_unintended_duplicates': duplicate.get('retry_executed', 0) > 0 and duplicate.get('multi_role_executed', 0) > 0 and duplicate.get('unintended_duplicates') == 0,
        'urgent_inbox_within_60_seconds': bool(latencies) and all(isinstance(value, (int, float)) and 0 <= value <= 60 for value in latencies),
        'manual_reminders_reduced_50_percent': valid_baseline and reduction >= .5,
    }
    return {'passed': all(gates.values()), 'gates': gates, 'recipient_count': len(recipients),
            'understanding_count': understanding, 'direct_task_count': direct,
            'manual_reminder_reduction': reduction,
            'note': 'Inbox latency is measured from committed business action to authenticated inbox availability, not email-provider delivery.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.observations.read_text()))
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    print(text)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
