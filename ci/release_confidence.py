#!/usr/bin/env python3
"""Fail-closed orchestration over the existing release qualification tooling.

No deployment. Missing evidence is blocked, not passed. Agent-written scenario
assertions are evidence claims, not independent certification of test quality.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'ci/release_confidence/scenarios.json'
BROWSER_TESTS = ('test_full_competition_lifecycle_browser_tour',
                 'test_keyboard_competition_setup_browser_tour',
                 'test_finance_bridge_browser_lifecycle')
SUMMARY = re.compile(r'(\d+) failed,\s*(\d+) error(?:s|\(s\))? of\s*(\d+) tests', re.I)
SKIP = re.compile(r'(?:skipped|skiptest|websocket-client module is not installed|chrome.*not found|chromium.*not found)', re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def read(path): return json.loads(Path(path).read_text())
def write(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n'); temp.replace(path)
def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()
def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
def clean():
    if git('status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Commit the candidate and automation first. Dirty worktrees are not release evidence.')
def external(path):
    path = Path(path).resolve()
    if path == ROOT or ROOT in path.parents: raise ValueError('Evidence must be outside the repository.')
    return path

def execute(argv, log, env, timeout):
    """Stream logs; timeout terminates the host process group. Docker cleanup is separate."""
    import signal
    log = Path(log); log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w') as f:
        proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        try: return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try: proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait()
            f.write('\nRELEASE_CONFIDENCE_TIMEOUT\n'); return 124
        except BaseException:
            os.killpg(proc.pid, signal.SIGTERM)
            raise

def inspect_log(text, require_tests=False):
    failures = []
    summaries = SUMMARY.findall(text)
    if require_tests and not any(int(n) > 0 for _, _, n in summaries):
        failures.append('No nonzero Odoo test summary: a successful command is not proof tests ran.')
    if any(int(f) or int(e) for f, e, _ in summaries): failures.append('Odoo reported failed tests or errors.')
    if re.search(r'Some modules have inconsistent states|Some modules are not loaded|declared but cannot be loaded', text):
        failures.append('Registry integrity failure.')
    # Conservative policy: every skip in qualification logs needs resolution, not a waiver.
    if SKIP.search(text): failures.append('Skipped test or unavailable browser dependency.')
    if 'RELEASE_CONFIDENCE_TIMEOUT' in text: failures.append('Command timed out.')
    return failures

def safe_archive(path):
    import tarfile
    with tarfile.open(path, 'r:gz') as archive:
        names = []
        for member in archive:
            parts = Path(member.name).parts
            if Path(member.name).is_absolute() or '..' in parts or member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe filestore archive member: ' + member.name)
            if parts: names.append(parts[0])
        if len(set(names)) != 1: raise ValueError('Filestore must contain one top-level database directory.')

def isolated_compose(config, filestore):
    """Resolved Compose JSON is accepted by Compose. No ports, external networks or host sockets."""
    config.pop('name', None)
    if set(config.get('services', {})) != {'ci-db', 'ci-odoo'}:
        raise ValueError('Expected only the repository CI database and Odoo services.')
    config['networks'] = {'default': {'internal': True}}
    for service in config['services'].values():
        for key in ('ports', 'network_mode', 'container_name', 'extra_hosts'):
            service.pop(key, None)
        if service.get('privileged'): raise ValueError('Privileged CI containers are not allowed.')
        service['networks'] = ['default']
        for volume in service.get('volumes', []):
            if isinstance(volume, dict) and ('docker.sock' in str(volume.get('source', '')) or volume.get('source') == '/'):
                raise ValueError('Unsafe host mount.')
    config['services']['ci-odoo'].setdefault('environment', {})['SF_CONFIDENCE_ISOLATED_FILESTORE'] = '1'
    config['services']['ci-odoo'].setdefault('volumes', []).append({
        'type': 'bind', 'source': str(filestore), 'target': '/var/lib/odoo/filestore'})
    return config

def runtime_env(run):
    env = {key: value for key, value in os.environ.items() if key in ('PATH', 'HOME', 'USER', 'TMPDIR', 'LANG', 'LC_ALL', 'PYTHONDONTWRITEBYTECODE')}
    # Do not accept inherited production database/project/config selections.
    for key in list(env):
        if key.startswith(('RC_', 'CI_', 'MIGRATION_', 'RELEASE_', 'PG', 'DB_', 'UPGRADE_', 'COMPOSE_', 'ODOO_')):
            env.pop(key, None)
    token = run['run_id']
    env.update({
        'RC_COMPOSE_PROJECT': token, 'RC_COMPOSE_RETAIN': '1',
        'DB_NAME': token + '_install', 'UPGRADE_DB_NAME': token + '_upgrade',
        'MIGRATION_TARGET_DB': token + '_migration', 'MIGRATION_ROLLBACK_DB': token + '_rollback',
        'RC_COMPOSE_FILE': str(Path(run['directory']) / 'runtime/compose.json'),
        'RC_ODOO_CONFIG_PATH': str(Path(run['directory']) / 'runtime/odoo.conf'),
        'CI_ODOO_CONFIG_PATH': str(Path(run['directory']) / 'runtime/odoo.conf'),
        'CI_POSTGRES_USER': 'odoo', 'CI_POSTGRES_PASSWORD': run['runtime_password'],
        'CI_POSTGRES_DB': 'postgres', 'CI_ODOO_DB_HOST': 'ci-db', 'CI_ODOO_DB_PORT': '5432',
        'FILESTORE_ROOT': str(Path(run['directory']) / 'runtime/filestore'),
        'RELEASE_BASELINE_EVIDENCE_DIR': str(Path(run['directory']) / 'baseline'),
        'MIGRATION_EVIDENCE_DIR': str(Path(run['directory']) / 'migration'),
        'ODOO_LOGFILE': str(Path(run['directory']) / 'runtime/odoo.log'),
        'RELEASE_BACKUP_DIR': run['backup_dir'], 'ROLLBACK_OWNER': run['rollback_owner'],
        'ROLLBACK_TRIGGER': run['rollback_trigger'],
    })
    return env

def validate_attachment_scenario_command(command):
    script = (ROOT / 'ci/attachment_restore_scenario.py').resolve()
    if len(command) < 2:
        return False
    argument = Path(command[1])
    if not argument.is_absolute(): argument = ROOT / argument
    return (argument.resolve() == script
            and bool(re.fullmatch(r'python(?:3(?:\.\d+)?)?', Path(command[0]).name)))

def initialise(args):
    clean()
    backup = Path(args.backup_dir).resolve()
    dumps = list(backup.glob('*.dump')); stores = list(backup.glob('filestore_*.tar.gz'))
    modules_file = backup / 'modules.txt'
    if len(dumps) != 1 or len(stores) != 1 or not modules_file.is_file():
        raise ValueError('Require exactly one database dump, one filestore archive, and modules.txt. No --skip-filestore.')
    safe_archive(stores[0])
    directory = external(args.evidence_dir)
    if directory.exists(): raise ValueError('Use a fresh evidence directory for every run.')
    directory.mkdir(parents=True, mode=0o700)
    (directory / 'runtime/filestore').mkdir(parents=True)
    (directory / 'runtime/odoo.conf').touch()
    os.chmod(directory / 'runtime/filestore', 0o1777)
    run = {'schema_version': 1, 'run_id': 'sf_conf_' + secrets.token_hex(6), 'commit': git('rev-parse', 'HEAD'),
           'started_at': now(), 'directory': str(directory), 'backup_dir': str(backup),
            'approved_sanitized_backup': bool(args.approved_sanitized_backup),
           'rollback_owner': args.rollback_owner, 'rollback_trigger': args.rollback_trigger,
           'backup': [{'path': str(p), 'sha256': digest(p)} for p in (dumps[0], stores[0], modules_file)],
           'runtime_password': secrets.token_hex(16), 'status': 'running',
           'scenarios_spec_sha256': digest(SPEC)}
    write(directory / 'run.json', run)
    os.chmod(directory / 'run.json', 0o600)
    env = runtime_env(run)
    (directory / 'runtime/odoo.conf').write_text(
        '[options]\ndb_host = ci-db\ndb_port = 5432\ndb_user = odoo\ndb_password = ' + run['runtime_password'] +
        '\naddons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons\ndata_dir = /var/lib/odoo\nlist_db = False\nhttp_interface = 127.0.0.1\nwithout_demo = True\n')
    try:
        original = ROOT / 'ci/docker-compose.ci.yaml'
        resolved = subprocess.run(['docker', 'compose', '-f', str(original), 'config', '--format', 'json'],
                                  cwd=ROOT, env=env, check=True, capture_output=True, text=True)
        write(directory / 'runtime/compose.json', isolated_compose(json.loads(resolved.stdout), directory / 'runtime/filestore'))
        os.chmod(directory / 'runtime/compose.json', 0o600)
        rc = execute(['bash', 'scripts/ci/run_release_qualification.sh'], directory / 'qualification.log', env, args.timeout)
        run.update(status='passed' if rc == 0 else 'failed', exit_code=rc, finished_at=now())
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        run.update(status='blocked', error=str(exc), finished_at=now())
    finally:
        # Only the fresh generated CI project can be removed. Never remove source backups.
        if (directory / 'runtime/compose.json').exists():
            execute(['bash', 'scripts/ci/run_rc_validation.sh', 'cleanup'], directory / 'cleanup.log', env, 120)
        run['sealed_artifacts'] = [
            {'path': str(p.relative_to(directory)), 'sha256': digest(p)}
            for folder in ('baseline', 'migration') for p in (directory / folder).rglob('*') if p.is_file()]
        write(directory / 'run.json', run)
    return verify(directory)

def scenario(args):
    clean()
    directory = external(args.evidence_dir); run = read(directory / 'run.json')
    if run['commit'] != git('rev-parse', 'HEAD'): raise ValueError('Candidate changed; start a new full run.')
    spec = read(SPEC)
    if args.name not in spec: raise ValueError('Unknown scenario.')
    command = args.command
    if command and command[0] == '--': command = command[1:]
    if not command: raise ValueError('Supply a real test command after --. No manual passing flag.')
    dest = directory / 'scenarios' / args.name
    if dest.exists(): raise ValueError('Scenario already recorded. Use a new full run after fixing failures.')
    if args.name == 'attachment_restore':
        if not validate_attachment_scenario_command(command):
            raise ValueError(
                'attachment_restore must use ci/attachment_restore_scenario.py through '
                'release_confidence.py scenario, with --attachment-record, --source-checkout, '
                'and --source-ref inputs.')
    dest.mkdir(parents=True, mode=0o700)
    os.chmod(dest, 0o700)
    env = runtime_env(run)
    env.update(SF_CONFIDENCE_RUN_ID=run['run_id'], SF_CONFIDENCE_COMMIT=run['commit'],
               SF_CONFIDENCE_SCENARIO=args.name, SF_CONFIDENCE_RESULT=str(dest / 'result.json'),
               SF_CONFIDENCE_ARTIFACTS=str(dest),
               SF_CONFIDENCE_INVOCATION='release-confidence-scenario-v1')
    rc = execute(command, dest / 'command.log', env, args.timeout)
    record = {'commit': run['commit'], 'run_id': run['run_id'], 'command': command,
              'exit_code': rc, 'finished_at': now(), 'files': [
                  {'path': str(p.relative_to(dest)), 'sha256': digest(p)} for p in dest.rglob('*')
                  if p.is_file() and not p.is_symlink()]}
    write(dest / 'execution.json', record)
    return verify(directory)

def validate_scenario(dest, run, expected, scenario_name=None):
    errors = []
    try:
        execution = read(dest / 'execution.json'); result = read(dest / 'result.json')
        for data in (execution, result):
            if data.get('commit') != run['commit'] or data.get('run_id') != run['run_id']:
                errors.append('Evidence belongs to another candidate/run.')
        if not any(f.get('path') == 'result.json' and f.get('sha256') == digest(dest / 'result.json') for f in execution.get('files', [])):
            errors.append('Scenario result is not sealed.')
        if execution.get('exit_code') != 0: errors.append('Test command failed.')
        if scenario_name == 'attachment_restore':
            from attachment_restore_scenario import validate_attachment_evidence
            errors.extend(validate_attachment_evidence(dest, run, expected, execution, result))
        else:
            if result.get('status') != 'passed' or not isinstance(result.get('tests_executed'), int) or result['tests_executed'] < 1:
                errors.append('No passing executed tests.')
            checks = result.get('checks', {})
            for check in expected:
                item = checks.get(check, {})
                if item.get('status') != 'passed' or not item.get('test_id') or not item.get('evidence'):
                    errors.append('Missing passing assertion: ' + check); continue
                for rel in item['evidence']:
                    p = (dest / rel).resolve()
                    if dest.resolve() not in p.parents or not p.is_file() or p.is_symlink() or p.stat().st_size == 0:
                        errors.append('Invalid assertion evidence: ' + str(rel))
                    elif not any(f['path'] == rel and f['sha256'] == digest(p) for f in execution.get('files', [])):
                        errors.append('Unsealed assertion evidence: ' + str(rel))
        for f in execution.get('files', []):
            p = (dest / f['path']).resolve()
            if dest.resolve() not in p.parents or not p.is_file() or digest(p) != f['sha256']:
                errors.append('Changed scenario artifact: ' + f['path'])
    except (OSError, ValueError, TypeError, KeyError) as exc: errors.append('Incomplete scenario evidence: ' + str(exc))
    return errors

def verify(directory):
    directory = external(directory); run = read(directory / 'run.json'); blockers = []
    if git('rev-parse', 'HEAD') != run['commit'] or git('status', '--porcelain', '--untracked-files=all'):
        blockers.append('Current source differs from the tested clean candidate.')
    if digest(SPEC) != run['scenarios_spec_sha256']: blockers.append('Scenario requirements changed.')
    if run.get('status') != 'passed': blockers.append('Existing release qualification did not pass.')
    for f in run.get('backup', []):
        if not Path(f['path']).is_file() or digest(f['path']) != f['sha256']: blockers.append('Backup changed or unavailable.')
    for f in run.get('sealed_artifacts', []):
        p = (directory / f['path']).resolve()
        if directory not in p.parents or not p.is_file() or digest(p) != f['sha256']: blockers.append('Changed qualification artifact: ' + f['path'])
    if not (directory / 'baseline/summary.json').is_file(): blockers.append('Missing baseline summary.')
    if not run.get('sealed_artifacts'): blockers.append('No sealed qualification artifacts.')
    required = ('preflight', 'static', 'install', 'upgrade', 'full', 'performance', 'acceptance', 'focus')
    for lane in required:
        log = directory / 'baseline/logs' / (lane + '.log')
        if not log.is_file(): blockers.append('Missing lane log: ' + lane); continue
        blockers.extend(lane + ': ' + e for e in inspect_log(log.read_text(errors='replace'), lane not in ('preflight', 'static', 'upgrade')))
    browser = '\n'.join(p.read_text(errors='replace') for p in (directory / 'baseline/logs').glob('*.log'))
    for test in BROWSER_TESTS:
        if not re.search(r'Starting .*' + re.escape(test), browser): blockers.append('Critical browser test not observed: ' + test)
    for name in ('before-upgrade.json', 'after-upgrade.json', 'rollback.json', 'invariant-comparison.json', 'manifest.json', 'restore-before-upgrade.txt', 'restore-rollback.txt'):
        if not (directory / 'migration' / name).is_file(): blockers.append('Missing migration artifact: ' + name)
    for name in ('restore-before-upgrade.txt', 'restore-rollback.txt'):
        p = directory / 'migration' / name
        if p.is_file() and 'filestore_restored=yes' not in p.read_text(): blockers.append('Filestore restoration not demonstrated: ' + name)
    if (directory / 'baseline/summary.json').is_file() and (directory / 'migration/manifest.json').is_file():
        for argv in (
            ['python3', 'ci/check_release_evidence.py', '--evidence-dir', str(directory / 'baseline'), '--commit', run['commit'], '--require-passing'],
            ['python3', 'ci/check_release_signoff.py', '--baseline', str(directory / 'baseline/summary.json'), '--migration', str(directory / 'migration/manifest.json'), '--commit', run['commit']],
        ):
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
            if result.returncode: blockers.append('Existing evidence validator failed: ' + result.stdout.strip() + result.stderr.strip())
    for name, checks in read(SPEC).items():
        blockers.extend(name + ': ' + e for e in validate_scenario(
            directory / 'scenarios' / name, run, checks, scenario_name=name))
    report = {'schema_version': 1, 'commit': run['commit'], 'run_id': run['run_id'], 'verified_at': now(),
              'status': 'passed' if not blockers else 'blocked', 'blockers': blockers,
              'scope': 'Release-confidence evidence gate, not deployment approval or independent test-quality certification.'}
    write(directory / 'release-confidence.json', report)
    text = '# Release confidence\n\nStatus: **' + report['status'].upper() + '**\n\nCandidate: `' + run['commit'] + '`\n\n'
    text += '\n'.join('- ' + b for b in blockers) if blockers else 'All configured evidence gates passed. Human release authorisation remains separate.'
    (directory / 'release-confidence.md').write_text(text + '\n')
    print(text)
    return 0 if not blockers else 1

def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('plan')
    run = sub.add_parser('run')
    run.add_argument('--backup-dir', required=True); run.add_argument('--evidence-dir', required=True)
    run.add_argument('--rollback-owner', required=True); run.add_argument('--rollback-trigger', required=True)
    run.add_argument('--approved-sanitized-backup', action='store_true', required=True)
    run.add_argument('--timeout', type=int, default=21600)
    s = sub.add_parser('scenario'); s.add_argument('--evidence-dir', required=True); s.add_argument('--name', required=True)
    s.add_argument('--timeout', type=int, default=3600); s.add_argument('command', nargs=argparse.REMAINDER)
    v = sub.add_parser('verify'); v.add_argument('--evidence-dir', required=True)
    a = p.parse_args()
    try:
        if a.action == 'plan':
            print(json.dumps({'qualification': 'scripts/ci/run_release_qualification.sh', 'additional_scenarios': read(SPEC),
                              'safety': 'Fresh isolated CI project, internal network, full filestore restore, no deployment.'}, indent=2)); return 0
        if a.action == 'run': return initialise(a)
        if a.action == 'scenario': return scenario(a)
        return verify(a.evidence_dir)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('BLOCKED: ' + str(exc), file=sys.stderr); return 2

if __name__ == '__main__': raise SystemExit(main())
