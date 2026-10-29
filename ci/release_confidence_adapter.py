#!/usr/bin/env python3
"""Turn real Odoo test execution into per-scenario evidence, never static claims.

The committed case map associates each required check with an actual test method.
All methods must be observed starting in a successful nonzero test run. This
adapter cannot judge whether a test's assertions adequately prove its label.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from release_confidence import inspect_log, read, write, SUMMARY, SPEC


def build_result(text, rc, mapping, expected, commit, run_id):
    errors = inspect_log(text, require_tests=True)
    if rc: errors.append('Test process failed: ' + str(rc))
    if set(mapping) != set(expected): errors.append('Case map must cover exactly the scenario requirements.')
    checks = {}
    for check in expected:
        test_id = mapping.get(check, '')
        if not isinstance(test_id, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.:]*', test_id):
            errors.append('Invalid test method mapping: ' + check); continue
        method = test_id.rsplit('.', 1)[-1].rsplit(':', 1)[-1]
        if not method.startswith('test_') or not re.search(r'Starting .*\b' + re.escape(method) + r'\b', text):
            errors.append('Mapped test did not run: ' + test_id); continue
        checks[check] = {'status': 'passed', 'test_id': test_id, 'evidence': ['test-execution.log']}
    count = sum(int(n) for _, _, n in SUMMARY.findall(text))
    return {'schema_version': 1, 'commit': commit, 'run_id': run_id,
            'status': 'passed' if not errors else 'failed', 'tests_executed': count,
            'checks': checks, 'errors': errors}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-map', type=Path, required=True)
    p.add_argument('command', nargs=argparse.REMAINDER)
    a = p.parse_args()
    required_env = ('SF_CONFIDENCE_RESULT', 'SF_CONFIDENCE_ARTIFACTS', 'SF_CONFIDENCE_SCENARIO',
                    'SF_CONFIDENCE_COMMIT', 'SF_CONFIDENCE_RUN_ID')
    if any(not os.environ.get(k) for k in required_env): p.error('Run through release_confidence.py scenario.')
    command = a.command[1:] if a.command and a.command[0] == '--' else a.command
    if not command: p.error('A real Odoo test command is required.')
    dest = Path(os.environ['SF_CONFIDENCE_ARTIFACTS'])
    log = dest / 'test-execution.log'
    with log.open('w') as stream:
        rc = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT).returncode
    result = build_result(log.read_text(errors='replace'), rc, read(a.case_map),
                          read(SPEC)[os.environ['SF_CONFIDENCE_SCENARIO']],
                          os.environ['SF_CONFIDENCE_COMMIT'], os.environ['SF_CONFIDENCE_RUN_ID'])
    write(os.environ['SF_CONFIDENCE_RESULT'], result)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
