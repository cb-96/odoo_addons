#!/usr/bin/env python3
"""Restore one operator-selected attachment into isolated generated databases.

This program is an implementation detail of ``release_confidence.py scenario``.
It never chooses an attachment, database, backup, filestore, or source ref itself.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any

from release_confidence import ROOT, digest, read, write

SCENARIO = 'attachment_restore'
CHECKS = (
    'known_file_readable_after_upgrade',
    'known_file_readable_after_rollback',
    'database_attachment_reference_matches_file_checksum',
    'restored_files_visible_inside_odoo_container',
)
STAGES = {
    'before_upgrade': ('before-upgrade.json', 'MIGRATION_TARGET_DB'),
    'after_upgrade': ('after-upgrade.json', 'MIGRATION_TARGET_DB'),
    'after_rollback': ('after-rollback.json', 'MIGRATION_ROLLBACK_DB'),
}
STAGE_CHECK_FILES = {
    'known_file_readable_after_upgrade': ['after-upgrade.json'],
    'known_file_readable_after_rollback': ['after-rollback.json'],
    'database_attachment_reference_matches_file_checksum': [
        'before-upgrade.json', 'after-upgrade.json', 'after-rollback.json'],
    'restored_files_visible_inside_odoo_container': [
        'before-upgrade.json', 'after-upgrade.json', 'after-rollback.json'],
}
MARKER = 'SF_ATTACHMENT_PROBE_JSON='
SHA1_RE = re.compile(r'^[0-9a-f]{40}$', re.I)
SHA256_RE = re.compile(r'^[0-9a-f]{64}$', re.I)
GIT_COMMIT_RE = re.compile(r'^[0-9a-f]{40}(?:[0-9a-f]{24})?$', re.I)
MODULE_RE = re.compile(r'^[a-z][a-z0-9_]*$')


class ScenarioError(ValueError):
    """An invalid input or failed attachment restore assertion."""


def _private(path: Path, label: str, *, directory: bool) -> Path:
    path = Path(path).expanduser()
    if path.is_symlink():
        raise ScenarioError(f'{label} must not be a symlink.')
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ScenarioError(f'{label} is unavailable: {path}') from exc
    st = resolved.stat()
    if directory and not stat.S_ISDIR(st.st_mode):
        raise ScenarioError(f'{label} must be a directory.')
    if not directory and not stat.S_ISREG(st.st_mode):
        raise ScenarioError(f'{label} must be a regular file.')
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
        raise ScenarioError(f'{label} must be owned by the current user and mode 0700/0600 or stricter.')
    return resolved


def _outside_workspace(path: Path, label: str) -> Path:
    path = Path(path).resolve(strict=True)
    workspace = ROOT.parent.resolve()
    if path == workspace or workspace in path.parents:
        raise ScenarioError(f'{label} must be outside the repository workspace: {workspace}')
    return path


def validate_attachment_record(data: Any, backup_dump_sha256: str) -> dict[str, Any]:
    """Validate the independently captured operator record; never discover a file."""
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ScenarioError('Attachment record must be a schema_version 1 JSON object.')
    required = {'schema_version', 'recorded_by', 'recorded_at', 'backup_dump_sha256', 'attachment'}
    if not required.issubset(data):
        raise ScenarioError('Attachment record is missing required independent inventory fields.')
    if not isinstance(data['recorded_by'], str) or not data['recorded_by'].strip():
        raise ScenarioError('Attachment record requires a non-empty recorded_by value.')
    if not isinstance(data['recorded_at'], str) or not data['recorded_at'].strip():
        raise ScenarioError('Attachment record requires a recorded_at timestamp.')
    try:
        from datetime import datetime
        recorded_at = datetime.fromisoformat(data['recorded_at'].replace('Z', '+00:00'))
    except ValueError as exc:
        raise ScenarioError('Attachment record recorded_at must be an ISO-8601 timestamp.') from exc
    if recorded_at.tzinfo is None:
        raise ScenarioError('Attachment record recorded_at must include a timezone.')
    backup_hash = data['backup_dump_sha256']
    if not isinstance(backup_hash, str) or not SHA256_RE.fullmatch(backup_hash):
        raise ScenarioError('Attachment record backup_dump_sha256 must be a SHA-256 hex digest.')
    if backup_hash.lower() != backup_dump_sha256.lower():
        raise ScenarioError('Attachment record is not bound to this run’s approved backup dump.')
    attachment = data['attachment']
    if not isinstance(attachment, dict):
        raise ScenarioError('Attachment record requires an attachment object.')
    fields = {'id', 'name', 'checksum', 'size', 'sha256'}
    if not fields.issubset(attachment):
        raise ScenarioError('Attachment record requires id, name, checksum, size, and sha256.')
    attachment_id = attachment['id']
    if type(attachment_id) is not int or attachment_id <= 0:
        raise ScenarioError('Attachment id must be a positive database integer.')
    name = attachment['name']
    if not isinstance(name, str) or not name.strip() or '\x00' in name:
        raise ScenarioError('Attachment name must be a non-empty string without NUL bytes.')
    checksum = attachment['checksum']
    if not isinstance(checksum, str) or not SHA1_RE.fullmatch(checksum):
        raise ScenarioError('Odoo attachment checksum must be a SHA-1 hex digest.')
    size = attachment['size']
    if type(size) is not int or size < 0:
        raise ScenarioError('Attachment size must be a non-negative integer.')
    sha256 = attachment['sha256']
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        raise ScenarioError('Attachment sha256 must be a SHA-256 hex digest of the independently captured bytes.')
    return {
        'schema_version': 1,
        'recorded_by': data['recorded_by'].strip(),
        'recorded_at': data['recorded_at'],
        'backup_dump_sha256': backup_hash.lower(),
        'attachment': {
            'id': attachment_id,
            'name': name,
            'checksum': checksum.lower(),
            'size': size,
            'sha256': sha256.lower(),
        },
    }


def _git(path: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ['git', '-C', str(path), *args], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ScenarioError(f'Cannot verify git source checkout {path}: {exc}') from exc
    return result.stdout.strip()


def backup_modules(backup_dir: Path) -> list[str]:
    modules_file = backup_dir / 'modules.txt'
    if modules_file.is_symlink() or not modules_file.is_file():
        raise ScenarioError('Approved backup is missing a regular modules.txt file.')
    modules = [line.strip() for line in modules_file.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not modules or len(modules) != len(set(modules)) or any(not MODULE_RE.fullmatch(name) for name in modules):
        raise ScenarioError('Backup modules.txt must contain unique, valid module names.')
    return modules


def _validate_base_compose(env: dict[str, str], run_dir: Path) -> dict[str, Any]:
    config = read(env['RC_COMPOSE_FILE'])
    services = config.get('services', {})
    if set(services) != {'ci-db', 'ci-odoo'}:
        raise ScenarioError('Generated Compose config must contain only ci-db and ci-odoo.')
    if (set(config.get('networks', {})) != {'default'}
            or config['networks']['default'].get('internal') is not True):
        raise ScenarioError('Generated Compose network is not internal.')
    for service_name, service in services.items():
        if (service.get('privileged') or service.get('ports') or service.get('network_mode')
                or service.get('container_name') or service.get('extra_hosts')
                or service.get('networks') != ['default']):
            raise ScenarioError(f'Generated Compose service {service_name} has an unsafe host/network setting.')
    volumes = services['ci-odoo'].get('volumes')
    if not isinstance(volumes, list) or not all(isinstance(item, dict) for item in volumes):
        raise ScenarioError('Resolved Compose volume format is unsupported; refusing the attachment scenario.')
    targets = {item.get('target'): item for item in volumes}
    expected_mounts = {
        '/mnt/extra-addons': ROOT.resolve(),
        '/etc/odoo/odoo.conf': run_dir / 'runtime/odoo.conf',
        '/var/lib/odoo/filestore': run_dir / 'runtime/filestore',
    }
    for target, expected_source in expected_mounts.items():
        if sum(item.get('target') == target for item in volumes) != 1:
            raise ScenarioError(f'Generated Compose config must mount {target} exactly once.')
        item = targets.get(target)
        if not item or item.get('type') != 'bind' or Path(item.get('source', '')).resolve() != expected_source:
            raise ScenarioError(f'Generated Compose mount for {target} differs from the private candidate runtime.')
    if not targets['/mnt/extra-addons'].get('read_only'):
        raise ScenarioError('Candidate addon source mount must be read-only.')
    if not targets['/etc/odoo/odoo.conf'].get('read_only'):
        raise ScenarioError('Generated Odoo config mount must be read-only.')
    for item in volumes:
        if item.get('type') == 'bind':
            source = str(item.get('source', ''))
            if 'docker.sock' in source or source == '/':
                raise ScenarioError('Generated Compose config contains an unsafe host bind mount.')
            allowed = {str(ROOT.resolve()), str((run_dir / 'runtime/odoo.conf').resolve()),
                       str((run_dir / 'runtime/filestore').resolve())}
            if source not in allowed:
                raise ScenarioError('Generated Compose config contains a host bind mount outside the candidate/private runtime.')
    return config


def verify_source_checkout(path: Path, stated_ref: str, modules: list[str]) -> dict[str, Any]:
    """Require a separate clean checkout exactly at the operator-stated source commit."""
    checkout = Path(path).expanduser().resolve(strict=True)
    if not checkout.is_dir() or checkout == ROOT.resolve() or ROOT.resolve() in checkout.parents:
        raise ScenarioError('Rollback source must be a separate addon checkout, not the current candidate checkout.')
    if not GIT_COMMIT_RE.fullmatch(stated_ref):
        raise ScenarioError('--source-ref must be the full source-version git commit SHA.')
    top = Path(_git(checkout, 'rev-parse', '--show-toplevel')).resolve()
    if top != checkout:
        raise ScenarioError('--source-checkout must name the git checkout root containing the addons.')
    head = _git(checkout, 'rev-parse', 'HEAD')
    stated = _git(checkout, 'rev-parse', '--verify', f'{stated_ref}^{{commit}}')
    if head.lower() != stated.lower() or head.lower() != stated_ref.lower():
        raise ScenarioError('Source checkout HEAD must equal the stated source-version commit.')
    if _git(checkout, 'status', '--porcelain', '--untracked-files=all'):
        raise ScenarioError('Source-version addon checkout must be clean, including untracked files.')

    custom_modules = [name for name in modules if name.startswith('sports_federation_')]
    if not custom_modules:
        raise ScenarioError('Backup module inventory contains no sports-federation addons to verify.')
    manifest_info: dict[str, dict[str, str]] = {}
    for module in custom_modules:
        module_dir = checkout / module
        manifest_path = module_dir / '__manifest__.py'
        if module_dir.is_symlink() or manifest_path.is_symlink() or not manifest_path.is_file():
            raise ScenarioError(f'Source checkout is missing the installed addon manifest for {module}.')
        try:
            manifest = ast.literal_eval(manifest_path.read_text(encoding='utf-8'))
        except (OSError, SyntaxError, ValueError) as exc:
            raise ScenarioError(f'Cannot safely parse source manifest for {module}.') from exc
        version = manifest.get('version') if isinstance(manifest, dict) else None
        if not isinstance(version, str) or not version.strip():
            raise ScenarioError(f'Source manifest for {module} must declare a literal version.')
        manifest_info[module] = {'version': version, 'sha256': digest(manifest_path)}
    return {
        'checkout': str(checkout),
        'ref': stated_ref.lower(),
        'commit': head.lower(),
        'manifest_info': manifest_info,
    }


def _validate_runtime(env: dict[str, str]) -> dict[str, Any]:
    required = (
        'SF_CONFIDENCE_RUN_ID', 'SF_CONFIDENCE_COMMIT', 'SF_CONFIDENCE_SCENARIO',
        'SF_CONFIDENCE_RESULT', 'SF_CONFIDENCE_ARTIFACTS', 'SF_CONFIDENCE_INVOCATION',
        'RC_COMPOSE_PROJECT', 'RC_COMPOSE_RETAIN', 'RC_COMPOSE_FILE', 'RC_ODOO_CONFIG_PATH',
        'DB_NAME', 'UPGRADE_DB_NAME', 'MIGRATION_TARGET_DB', 'MIGRATION_ROLLBACK_DB',
        'FILESTORE_ROOT', 'RELEASE_BACKUP_DIR', 'MIGRATION_EVIDENCE_DIR',
        'CI_POSTGRES_USER', 'CI_POSTGRES_PASSWORD', 'CI_POSTGRES_DB',
        'CI_ODOO_DB_HOST', 'CI_ODOO_DB_PORT', 'ODOO_LOGFILE', 'ROLLBACK_OWNER', 'ROLLBACK_TRIGGER',
    )
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise ScenarioError('Missing generated release-confidence runtime variables: ' + ', '.join(missing))
    run_id = env['SF_CONFIDENCE_RUN_ID']
    if not re.fullmatch(r'sf_conf_[0-9a-f]{12}', run_id):
        raise ScenarioError('SF_CONFIDENCE_RUN_ID is not a generated run identifier.')
    if env['SF_CONFIDENCE_SCENARIO'] != SCENARIO or env['SF_CONFIDENCE_INVOCATION'] != 'release-confidence-scenario-v1':
        raise ScenarioError('This driver is available only through release_confidence.py scenario attachment_restore.')
    if not GIT_COMMIT_RE.fullmatch(env['SF_CONFIDENCE_COMMIT']):
        raise ScenarioError('SF_CONFIDENCE_COMMIT is not a full candidate commit SHA.')

    artifacts = _private(Path(env['SF_CONFIDENCE_ARTIFACTS']), 'Scenario artifacts directory', directory=True)
    run_path = artifacts.parent.parent / 'run.json'
    run = read(run_path)
    run_dir = Path(run['directory']).resolve(strict=True)
    expected_artifacts = run_dir / 'scenarios' / SCENARIO
    if artifacts != expected_artifacts or Path(env['SF_CONFIDENCE_RESULT']).resolve() != artifacts / 'result.json':
        raise ScenarioError('Scenario artifact/result paths do not match the generated private run directory.')
    if run.get('run_id') != run_id or run.get('commit') != env['SF_CONFIDENCE_COMMIT']:
        raise ScenarioError('Generated scenario variables do not match run.json.')
    if run.get('status') != 'passed' or run.get('approved_sanitized_backup') is not True:
        raise ScenarioError('A passed qualification using an approved sanitized backup is required.')
    if run_dir.stat().st_uid != os.getuid() or stat.S_IMODE(run_dir.stat().st_mode) & 0o077:
        raise ScenarioError('Release-confidence run directory must remain private to the current user.')
    if artifacts.exists() and (artifacts.stat().st_uid != os.getuid() or stat.S_IMODE(artifacts.stat().st_mode) & 0o077):
        raise ScenarioError('Scenario artifacts directory must remain private to the current user.')

    expected_names = {
        'RC_COMPOSE_PROJECT': run_id,
        'DB_NAME': run_id + '_install',
        'UPGRADE_DB_NAME': run_id + '_upgrade',
        'MIGRATION_TARGET_DB': run_id + '_migration',
        'MIGRATION_ROLLBACK_DB': run_id + '_rollback',
    }
    for key, value in expected_names.items():
        if env[key] != value:
            raise ScenarioError(f'{key} is not the generated value for this run.')
    if env['RC_COMPOSE_RETAIN'] != '1':
        raise ScenarioError('The isolated generated Compose project must be retained during the scenario.')
    for key in ('MIGRATION_TARGET_DB', 'MIGRATION_ROLLBACK_DB'):
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', env[key]):
            raise ScenarioError(f'{key} is not a safe generated database name.')
    if env['MIGRATION_TARGET_DB'] == env['MIGRATION_ROLLBACK_DB']:
        raise ScenarioError('Upgrade and rollback targets must be separate generated databases.')

    for key, relative in (
        ('RC_COMPOSE_FILE', 'runtime/compose.json'),
        ('RC_ODOO_CONFIG_PATH', 'runtime/odoo.conf'),
        ('FILESTORE_ROOT', 'runtime/filestore'),
        ('MIGRATION_EVIDENCE_DIR', 'migration'),
        ('ODOO_LOGFILE', 'runtime/odoo.log'),
    ):
        if Path(env[key]).resolve() != run_dir / relative:
            raise ScenarioError(f'{key} must point only into this generated private run.')
    compose_path = run_dir / 'runtime/compose.json'
    if not compose_path.is_file() or compose_path.is_symlink():
        raise ScenarioError('Generated isolated Compose configuration is missing or unsafe.')
    file_store = run_dir / 'runtime/filestore'
    if not file_store.is_dir() or file_store.is_symlink():
        raise ScenarioError('Generated private FILESTORE_ROOT is missing or unsafe.')

    backup = _outside_workspace(
        _private(Path(run['backup_dir']), 'Approved backup directory', directory=True), 'Approved backup')
    if Path(env['RELEASE_BACKUP_DIR']).resolve(strict=True) != backup:
        raise ScenarioError('RELEASE_BACKUP_DIR does not match the run backup.')
    if (env['CI_ODOO_DB_HOST'] != 'ci-db' or env['CI_ODOO_DB_PORT'] != '5432'
            or env['CI_POSTGRES_DB'] != 'postgres' or env['CI_POSTGRES_USER'] != 'odoo'
            or env['CI_POSTGRES_PASSWORD'] != run.get('runtime_password')):
        raise ScenarioError('Generated isolated PostgreSQL connection settings were changed.')

    _validate_base_compose(env, run_dir)

    current_commit = _git(ROOT, 'rev-parse', 'HEAD')
    if current_commit.lower() != env['SF_CONFIDENCE_COMMIT'].lower() or _git(
            ROOT, 'status', '--porcelain', '--untracked-files=all'):
        raise ScenarioError('Current candidate checkout is not the clean generated release-confidence commit.')
    return {'env': env, 'artifacts': artifacts, 'run_dir': run_dir, 'run': run, 'backup': backup}


def _inspect_backup(context: dict[str, Any]) -> dict[str, Any]:
    backup = context['backup']
    dump_files = sorted(p for p in backup.glob('*.dump') if p.is_file() and not p.is_symlink())
    store_files = sorted(p for p in backup.glob('filestore_*.tar.gz') if p.is_file() and not p.is_symlink())
    if len(dump_files) != 1 or len(store_files) != 1:
        raise ScenarioError('Require exactly one regular database dump and one filestore archive.')
    expected = {Path(item['path']).resolve(): item['sha256'] for item in context['run'].get('backup', [])}
    modules_path = (backup / 'modules.txt').resolve()
    if set(expected) != {dump_files[0].resolve(), store_files[0].resolve(), modules_path}:
        raise ScenarioError('Backup files differ from those approved and hashed in run.json.')
    if (backup / 'modules.txt').is_symlink() or not (backup / 'modules.txt').is_file():
        raise ScenarioError('Approved backup modules.txt is missing or unsafe.')
    for path in (dump_files[0], store_files[0], backup / 'modules.txt'):
        if digest(path) != expected[path.resolve()]:
            raise ScenarioError(f'Approved backup changed after qualification: {path.name}')
    return {
        'dump': dump_files[0].resolve(),
        'filestore_archive': store_files[0].resolve(),
        'dump_sha256': digest(dump_files[0]),
        'modules': backup_modules(backup),
    }


def _ensure_odoo_config(context: dict[str, Any]) -> None:
    """The existing RC cleanup removes this generated file after full qualification."""
    env = context['env']
    config_path = context['run_dir'] / 'runtime/odoo.conf'
    expected = (
        '[options]\n'
        'db_host = ci-db\n'
        'db_port = 5432\n'
        'db_user = odoo\n'
        f"db_password = {env['CI_POSTGRES_PASSWORD']}\n"
        'addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons\n'
        'data_dir = /var/lib/odoo\n'
        'list_db = False\n'
        'http_interface = 127.0.0.1\n'
        'without_demo = True\n'
        'log_level = info\n'
    )
    if config_path.is_symlink():
        raise ScenarioError('Generated Odoo config path must not be a symlink.')
    initializer_form = expected.removesuffix('log_level = info\n')
    if config_path.exists() and config_path.read_text(encoding='utf-8') not in (expected, initializer_form):
        raise ScenarioError('Existing generated Odoo config does not match the private RC database settings.')
    if not config_path.exists():
        config_path.write_text(expected, encoding='utf-8')
    # Odoo runs as uid odoo in the container; its parent run directory is mode 0700 on the host.
    os.chmod(config_path, 0o644)


def _start_generated_database(context: dict[str, Any], timeout: int) -> None:
    """Start only the run-specific CI database; reject pre-existing project containers."""
    env = context['env']
    compose = [
        'docker', 'compose', '-p', env['RC_COMPOSE_PROJECT'],
        '-f', env['RC_COMPOSE_FILE'],
    ]
    existing = _run_logged(
        compose + ['ps', '-a', '-q'],
        context['artifacts'] / 'database-preflight.log', env, 120,
    )
    if existing.returncode != 0:
        raise ScenarioError('Cannot inspect the generated CI project before starting it.')
    if existing.stdout.strip():
        raise ScenarioError('Generated CI project already contains containers; refusing to reuse it.')

    # From this point the randomly named project was observed empty, so this run owns
    # any containers created by its start attempt (including a partial failed start).
    context['owns_generated_project'] = True
    started = _run_logged(
        compose + ['up', '-d', '--wait', 'ci-db'],
        context['artifacts'] / 'database-start.log', env, timeout,
    )
    if started.returncode != 0:
        raise ScenarioError('Could not start the generated private CI PostgreSQL service.')
    ready = _run_logged(
        compose + [
            'exec', '-T', 'ci-db', 'pg_isready',
            '-U', env['CI_POSTGRES_USER'], '-d', env['CI_POSTGRES_DB'],
        ],
        context['artifacts'] / 'database-readiness.log', env, 120,
    )
    if ready.returncode != 0:
        raise ScenarioError('Generated private CI PostgreSQL service failed its readiness check.')


def _compose_for_probe(base_path: Path, output_path: Path, probe_path: Path,
                       source_checkout: Path | None) -> Path:
    config = json.loads(base_path.read_text(encoding='utf-8'))
    services = config.get('services', {})
    if set(services) != {'ci-db', 'ci-odoo'}:
        raise ScenarioError('Generated Compose config must contain only ci-db and ci-odoo.')
    odoo = services['ci-odoo']
    if odoo.get('privileged') or 'ports' in odoo or odoo.get('network_mode'):
        raise ScenarioError('Generated Odoo service has unsafe Compose privileges or networking.')
    volumes = odoo.get('volumes')
    if not isinstance(volumes, list) or not all(isinstance(item, dict) for item in volumes):
        raise ScenarioError('Resolved Compose volume format is unsupported; refusing a rollback probe.')
    addon_mounts = [item for item in volumes if item.get('target') == '/mnt/extra-addons']
    if len(addon_mounts) != 1:
        raise ScenarioError('Expected exactly one addon checkout mount in the isolated Compose config.')
    if source_checkout is None:
        if Path(addon_mounts[0].get('source', '')).resolve() != ROOT.resolve():
            raise ScenarioError('Pre/post-upgrade probe is not mounted against the candidate addon checkout.')
    else:
        addon_mounts[0]['source'] = str(source_checkout)
        addon_mounts[0]['read_only'] = True
    if any(item.get('target') == '/tmp/sf-attachment-probe.py' for item in volumes):
        raise ScenarioError('Probe mount already exists in generated Compose config.')
    volumes.append({
        'type': 'bind', 'source': str(probe_path.resolve()),
        'target': '/tmp/sf-attachment-probe.py', 'read_only': True,
    })
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    write(output_path, config)
    os.chmod(output_path, 0o600)
    return output_path


def _probe_source(record: dict[str, Any], stage: str, database: str, code_commit: str,
                  manifest_info: dict[str, dict[str, str]] | None) -> str:
    payload = {
        'stage': stage,
        'database': database,
        'code_commit': code_commit,
        'attachment': record['attachment'],
        'manifest_info': manifest_info or {},
    }
    encoded = base64.b64encode(json.dumps(payload, sort_keys=True).encode()).decode('ascii')
    return _PROBE_TEMPLATE.replace('__PAYLOAD_B64__', encoded)


_PROBE_TEMPLATE = r'''import base64
import hashlib
import json
import os
from pathlib import Path

from odoo.modules.module import get_module_path

EXPECTED = json.loads(base64.b64decode('__PAYLOAD_B64__'))
result = {
    'schema_version': 1,
    'stage': EXPECTED['stage'],
    'database': EXPECTED['database'],
    'addon_commit': EXPECTED['code_commit'],
    'container_probe': Path('/.dockerenv').exists(),
    'checks': {},
}
try:
    attachment = env['ir.attachment'].sudo().browse(EXPECTED['attachment']['id']).exists()
    if not attachment:
        raise RuntimeError('operator-selected attachment id is absent')
    raw = attachment.raw
    if isinstance(raw, (bytearray, memoryview)):
        raw = bytes(raw)
    if not isinstance(raw, bytes):
        raise TypeError('ir.attachment.raw did not return bytes')
    expected = EXPECTED['attachment']
    actual = {
        'id': attachment.id,
        'name': attachment.name,
        'checksum': attachment.checksum,
        'size': attachment.file_size,
    }
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    raw_sha1 = hashlib.sha1(raw).hexdigest()
    full_path = attachment._full_path(attachment.store_fname) if attachment.store_fname else ''
    file = Path(full_path) if full_path else None
    file_present = bool(file and file.is_file() and not file.is_symlink())
    file_readable = False
    file_size = None
    file_sha256 = None
    path_within_filestore = False
    if file_present:
        resolved_file = file.resolve(strict=True)
        store_root = (Path('/var/lib/odoo/filestore') / EXPECTED['database']).resolve(strict=True)
        path_within_filestore = resolved_file.is_relative_to(store_root)
        with resolved_file.open('rb') as stream:
            file_bytes = stream.read()
        file_readable = True
        file_size = len(file_bytes)
        file_sha256 = hashlib.sha256(file_bytes).hexdigest()

    expected_manifests = EXPECTED['manifest_info']
    manifests_match = True
    module_versions_match = True
    if expected_manifests:
        for module, info in expected_manifests.items():
            module_path = get_module_path(module)
            if not module_path or not Path(module_path).resolve().is_relative_to(Path('/mnt/extra-addons').resolve()):
                manifests_match = False
                continue
            manifest_path = Path(module_path) / '__manifest__.py'
            if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != info['sha256']:
                manifests_match = False
        installed = env['ir.module.module'].sudo().search_read(
            [('name', 'in', list(expected_manifests)), ('state', '=', 'installed')],
            ['name', 'latest_version'])
        found = {item['name']: item['latest_version'] for item in installed}
        module_versions_match = all(
            found.get(module) == info['version'] for module, info in expected_manifests.items())

    result.update({
        'database_attachment': actual,
        'raw': {'size': len(raw), 'sha256': raw_sha256},
        'odoo_checksum_sha1': raw_sha1,
        'full_path': str(file) if file else '',
        'file': {
            'present': file_present,
            'readable': file_readable,
            'size': file_size,
            'sha256': file_sha256,
            'path_within_filestore': path_within_filestore,
        },
        'source_manifests_match_mounted_checkout': manifests_match,
        'source_module_versions_match_restored_database': module_versions_match,
        'checks': {
            'container_probe': result['container_probe'],
            'database_fields_match': (
                actual['id'] == expected['id']
                and actual['name'] == expected['name']
                and (actual['checksum'] or '').lower() == expected['checksum']
                and actual['size'] == expected['size']),
            'raw_size_matches': len(raw) == expected['size'],
            'raw_sha256_matches': raw_sha256 == expected['sha256'],
            'odoo_checksum_matches_sha1': (
                (actual['checksum'] or '').lower() == expected['checksum'] == raw_sha1),
            'file_present': file_present,
            'file_readable': file_readable,
            'file_size_matches': file_size == expected['size'],
            'file_sha256_matches_raw': file_sha256 == raw_sha256 == expected['sha256'],
            'path_within_filestore': path_within_filestore,
            'source_manifests_match_mounted_checkout': manifests_match,
            'source_module_versions_match_restored_database': module_versions_match,
        },
    })
except Exception as exc:
    result['error'] = type(exc).__name__ + ': ' + str(exc)
    result['checks']['probe_completed'] = False

print('SF_ATTACHMENT_PROBE_JSON=' + json.dumps(result, sort_keys=True))
if result.get('error') or not all(result['checks'].values()):
    raise RuntimeError('attachment restore probe assertions failed')
'''


def _write_private_json(path: Path, value: Any) -> None:
    write(path, value)
    os.chmod(path, 0o600)


def _run_logged(argv: list[str], log_path: Path, env: dict[str, str], timeout: int,
                *, stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        proc = subprocess.run(
            argv, cwd=ROOT, env=env, input=stdin_text, capture_output=True, text=True,
            timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _write_private_json(log_path.with_suffix(log_path.suffix + '.error.json'), {'error': str(exc)})
        raise ScenarioError(f'Command failed or timed out: {Path(argv[0]).name}') from exc
    log_path.write_text(proc.stdout + proc.stderr, encoding='utf-8')
    os.chmod(log_path, 0o600)
    return proc


def _restore(context: dict[str, Any], backup: dict[str, Any], database: str,
             report: Path, log: Path, timeout: int) -> None:
    env = dict(context['env'])
    env['FILESTORE_ROOT'] = str(context['run_dir'] / 'runtime/filestore')
    argv = [
        'bash', 'ci/restore_backup_drill.sh',
        '--backup-dir', str(context['backup']),
        '--target-db', database,
        '--compose-file', env['RC_COMPOSE_FILE'],
        '--project-name', env['RC_COMPOSE_PROJECT'],
        '--db-service', 'ci-db',
        '--db-user', env['CI_POSTGRES_USER'],
        '--backup-root', str(context['backup'].parent),
        '--filestore-root', env['FILESTORE_ROOT'],
        '--report-file', str(report),
        '--yes',
    ]
    proc = _run_logged(argv, log, env, timeout)
    if proc.returncode != 0:
        raise ScenarioError(f'Backup restore failed for generated target {database}.')
    if not report.is_file() or report.stat().st_size == 0:
        raise ScenarioError(f'Restore script did not emit evidence for {database}.')
    report_text = report.read_text(encoding='utf-8', errors='replace')
    if f'target_db={database}' not in report_text or 'filestore_restored=yes' not in report_text:
        raise ScenarioError(f'Restore report does not prove a full filestore restore for {database}.')
    if backup['dump_sha256'] != digest(backup['dump']):
        raise ScenarioError('Approved database dump changed while the restore scenario was running.')


def _run_probe(context: dict[str, Any], record: dict[str, Any], stage: str, database: str,
               code_commit: str, source_checkout: Path | None,
               manifest_info: dict[str, dict[str, str]] | None, timeout: int) -> dict[str, Any]:
    artifacts = context['artifacts']
    stage_filename = STAGES[stage][0]
    probe_file = artifacts / (stage + '-probe.py')
    probe_file.write_text(_probe_source(record, stage, database, code_commit, manifest_info), encoding='utf-8')
    os.chmod(probe_file, 0o444)
    compose_path = _compose_for_probe(
        Path(context['env']['RC_COMPOSE_FILE']),
        artifacts / (stage + '-compose.json'), probe_file, source_checkout)
    container_command = r'''set -eu
if [ ! -e /usr/lib/python3/dist-packages/odoo-bin ]; then
  ln -s /usr/bin/odoo /usr/lib/python3/dist-packages/odoo-bin
fi
if command -v gosu >/dev/null 2>&1; then
  exec gosu odoo odoo shell -c /etc/odoo/odoo.conf -d "$1" --no-http --stop-after-init
elif command -v runuser >/dev/null 2>&1; then
  exec runuser -u odoo -- odoo shell -c /etc/odoo/odoo.conf -d "$1" --no-http --stop-after-init
else
  echo 'No supported privilege-drop command; refusing ORM probe as root.' >&2
  exit 2
fi
'''
    env = dict(context['env'])
    argv = [
        'docker', 'compose', '-p', env['RC_COMPOSE_PROJECT'], '-f', str(compose_path),
        'run', '--rm', '--no-deps', '--no-build', '-T', 'ci-odoo',
        'sh', '-lc', container_command, '--', database,
    ]
    log = artifacts / (stage + '-probe.log')
    try:
        proc = _run_logged(argv, log, env, timeout, stdin_text=probe_file.read_text(encoding='utf-8'))
    except ScenarioError as exc:
        _write_private_json(artifacts / stage_filename, {
            'schema_version': 1, 'stage': stage, 'database': database,
            'addon_commit': code_commit, 'status': 'failed', 'error': str(exc), 'checks': {},
        })
        raise
    output = proc.stdout + proc.stderr
    encoded_result = next((line.split(MARKER, 1)[1] for line in output.splitlines() if MARKER in line), None)
    if encoded_result is None:
        _write_private_json(artifacts / stage_filename, {
            'schema_version': 1, 'stage': stage, 'database': database,
            'addon_commit': code_commit, 'status': 'failed',
            'error': 'Odoo container emitted no structured ORM result.', 'checks': {},
        })
        raise ScenarioError(f'Odoo container emitted no structured ORM result for {stage}.')
    try:
        stage_result = json.loads(encoded_result)
    except json.JSONDecodeError as exc:
        _write_private_json(artifacts / stage_filename, {
            'schema_version': 1, 'stage': stage, 'database': database,
            'addon_commit': code_commit, 'status': 'failed',
            'error': 'Odoo container emitted invalid JSON.', 'checks': {},
        })
        raise ScenarioError(f'Odoo container emitted invalid JSON for {stage}.') from exc
    if not isinstance(stage_result, dict):
        _write_private_json(artifacts / stage_filename, {
            'schema_version': 1, 'stage': stage, 'database': database,
            'addon_commit': code_commit, 'status': 'failed',
            'error': 'Odoo container result was not a JSON object.', 'checks': {},
        })
        raise ScenarioError(f'Odoo container emitted a non-object result for {stage}.')
    _write_private_json(artifacts / stage_filename, stage_result)
    failed_checks = [name for name, value in stage_result.get('checks', {}).items() if value is not True]
    if stage == 'after_rollback' and stage_result.get('source_manifests_match_mounted_checkout') is not True:
        raise ScenarioError(
            'Rollback source addon manifests could not be verified inside Odoo. Supply a checkout '
            'with the supported module layout or make a reviewed runner adjustment; do not claim rollback readability.')
    if stage == 'after_rollback' and stage_result.get('source_module_versions_match_restored_database') is not True:
        raise ScenarioError(
            'Rollback source manifest versions do not match the restored database. Supply the '
            'correct source-version commit or stop; do not upgrade the rollback database.')
    if proc.returncode != 0 or stage_result.get('error') or failed_checks:
        detail = stage_result.get('error') or ', '.join(failed_checks) or 'Odoo shell exited nonzero'
        raise ScenarioError(f'Odoo ORM attachment checks failed during {stage}: {detail}.')
    return stage_result


def build_attachment_result(commit: str, run_id: str, record: dict[str, Any],
                            source: dict[str, Any] | None, stages: dict[str, dict[str, Any]],
                            restore_targets: list[str], errors: list[str],
                            upgrade_exit_code: int | None = 0) -> dict[str, Any]:
    """Create truthful per-check claims from explicit stage probe outcomes."""
    stage_by_file = {STAGES[key][0]: value for key, value in stages.items()}
    checks: dict[str, Any] = {}
    for check in CHECKS:
        evidence = STAGE_CHECK_FILES[check]
        relevant = [stage_by_file[name] for name in evidence if name in stage_by_file]
        stage_checks = [item.get('checks', {}) for item in relevant]
        if check == 'known_file_readable_after_upgrade':
            passed = len(stage_checks) == 1 and all(stage_checks[0].get(key) is True for key in (
                'container_probe', 'raw_sha256_matches', 'file_present', 'file_readable',
                'file_size_matches', 'file_sha256_matches_raw', 'path_within_filestore'))
        elif check == 'known_file_readable_after_rollback':
            passed = len(stage_checks) == 1 and all(stage_checks[0].get(key) is True for key in (
                'container_probe', 'raw_sha256_matches', 'file_present', 'file_readable',
                'file_size_matches', 'file_sha256_matches_raw', 'path_within_filestore',
                'source_manifests_match_mounted_checkout', 'source_module_versions_match_restored_database'))
        elif check == 'database_attachment_reference_matches_file_checksum':
            passed = len(stage_checks) == 3 and all(all(values.get(key) is True for key in (
                'database_fields_match', 'raw_size_matches', 'raw_sha256_matches',
                'odoo_checksum_matches_sha1', 'file_size_matches', 'file_sha256_matches_raw'))
                for values in stage_checks)
        else:
            passed = len(stage_checks) == 3 and all(all(values.get(key) is True for key in (
                'container_probe', 'file_present', 'file_readable', 'path_within_filestore'))
                for values in stage_checks)
        checks[check] = {
            'status': 'passed' if passed else 'failed',
            'probe_id': check,
            'evidence': [name for name in evidence if name in stage_by_file],
        }
        if not passed and not errors:
            errors.append('Required attachment assertion was not demonstrated: ' + check)
    passed = not errors and all(item['status'] == 'passed' for item in checks.values())
    return {
        'schema_version': 1,
        'adapter': 'attachment-restore-v1',
        'scenario': SCENARIO,
        'commit': commit,
        'run_id': run_id,
        'status': 'passed' if passed else 'failed',
        'probes_executed': len(stages),
        'restore_targets': restore_targets,
        'upgrade_exit_code': upgrade_exit_code,
        'upgrade_command': ['bash', 'scripts/ci/run_rc_validation.sh', 'upgrade'],
        'upgrade_database': (stages.get('after_upgrade', {}).get('database')
                     or stages.get('before_upgrade', {}).get('database')),
        'attachment_record': record,
        'source_version': ({key: source[key] for key in ('checkout', 'ref', 'commit')}
                           if source else None),
        'checks': checks,
        'errors': errors,
    }


def _check_stage(stage: dict[str, Any], stage_name: str, database: str,
                 code_commit: str, record: dict[str, Any], source_required: bool) -> list[str]:
    errors = []
    label = stage_name
    expected_attachment = record['attachment']
    if stage.get('schema_version') != 1 or stage.get('stage') != stage_name:
        errors.append(f'{label}: wrong stage evidence schema or stage name.')
    if stage.get('database') != database or stage.get('addon_commit') != code_commit:
        errors.append(f'{label}: unexpected generated database or addon source commit.')
    actual = stage.get('database_attachment', {})
    for key in ('id', 'name', 'checksum', 'size'):
        actual_value = actual.get(key)
        expected_value = expected_attachment[key]
        if key == 'checksum' and isinstance(actual_value, str):
            actual_value = actual_value.lower()
        if actual_value != expected_value:
            errors.append(f'{label}: database attachment {key} differs from the independent record.')
    raw = stage.get('raw', {})
    file = stage.get('file', {})
    if raw.get('size') != expected_attachment['size'] or raw.get('sha256') != expected_attachment['sha256']:
        errors.append(f'{label}: Odoo ir.attachment.raw bytes differ from recorded size/SHA-256.')
    if stage.get('odoo_checksum_sha1') != expected_attachment['checksum']:
        errors.append(f'{label}: Odoo checksum does not match the independently recorded checksum.')
    if (file.get('present') is not True or file.get('readable') is not True
            or file.get('size') != expected_attachment['size']
            or file.get('sha256') != expected_attachment['sha256']
            or file.get('path_within_filestore') is not True
            or not stage.get('full_path')):
        errors.append(f'{label}: _full_path file is absent, unreadable, outside its filestore, or has different bytes.')
    else:
        expected_prefix = f'/var/lib/odoo/filestore/{database}/'
        full_path = Path(stage['full_path'])
        if (not full_path.is_absolute() or '..' in full_path.parts
                or not stage['full_path'].startswith(expected_prefix)):
            errors.append(f'{label}: _full_path is not inside the generated target database filestore.')
    if stage.get('container_probe') is not True:
        errors.append(f'{label}: result did not come from an Odoo container probe.')
    checks = stage.get('checks', {})
    if not isinstance(checks, dict) or not checks or not all(value is True for value in checks.values()):
        errors.append(f'{label}: one or more probe assertions failed.')
    if source_required and (stage.get('source_manifests_match_mounted_checkout') is not True
                            or stage.get('source_module_versions_match_restored_database') is not True):
        errors.append(f'{label}: rollback probe did not verify source-version manifests against the restored DB.')
    return errors


def validate_attachment_evidence(dest: Path, run: dict[str, Any], expected: list[str],
                                 execution: dict[str, Any], result: dict[str, Any]) -> list[str]:
    """Dedicated validator; the generic Odoo-test adapter remains unchanged."""
    errors: list[str] = []
    if not isinstance(execution, dict) or not isinstance(result, dict):
        return ['Attachment execution and result evidence must be JSON objects.']
    if set(expected) != set(CHECKS):
        errors.append('Configured attachment_restore requirements differ from the dedicated adapter contract.')
    if result.get('adapter') != 'attachment-restore-v1' or result.get('scenario') != SCENARIO:
        errors.append('Attachment scenario did not use the dedicated restore evidence adapter.')
    if result.get('status') != 'passed' or result.get('probes_executed') != 3:
        errors.append('Attachment restore did not complete all three Odoo ORM probes.')
    if result.get('restore_targets') != [run['run_id'] + '_migration', run['run_id'] + '_rollback']:
        errors.append('Attachment evidence does not show two restores into the generated distinct targets.')
    if result.get('upgrade_exit_code') != 0:
        errors.append('Generated pre-upgrade target was not successfully upgraded.')
    if result.get('upgrade_command') != ['bash', 'scripts/ci/run_rc_validation.sh', 'upgrade']:
        errors.append('Attachment upgrade did not use the existing RC upgrade lane.')
    if result.get('upgrade_database') != run['run_id'] + '_migration':
        errors.append('Upgrade evidence does not target only the generated pre-upgrade database.')
    if result.get('commit') != run.get('commit') or result.get('run_id') != run.get('run_id'):
        errors.append('Attachment result belongs to a different candidate or run.')

    backup_entries = [item for item in run.get('backup', []) if Path(item.get('path', '')).suffix == '.dump']
    store_entries = [item for item in run.get('backup', []) if Path(item.get('path', '')).name.startswith('filestore_')]
    try:
        if len(backup_entries) != 1 or len(store_entries) != 1:
            raise ScenarioError('run.json does not identify exactly one approved dump and filestore archive.')
        record_data = read(dest / 'attachment-record.json')
        record = validate_attachment_record(record_data, backup_entries[0]['sha256'])
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append('Invalid copied independent attachment record: ' + str(exc))
        record = None

    source = result.get('source_version')
    source_info = None
    if not isinstance(source, dict):
        errors.append('Source-version checkout/ref evidence is missing.')
    else:
        try:
            modules = backup_modules(Path(run['backup_dir']).resolve(strict=True))
            source_info = verify_source_checkout(Path(source['checkout']), source['ref'], modules)
            if source_info['commit'] != source.get('commit'):
                errors.append('Rollback source checkout changed after the probe.')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append('Rollback source checkout is no longer verifiable: ' + str(exc))

    if record:
        try:
            preflight = read(dest / 'preflight.json')
            if (preflight.get('status') != 'passed'
                    or preflight.get('backup_dump_sha256') != backup_entries[0]['sha256']
                    or preflight.get('backup_filestore_sha256') != store_entries[0]['sha256']
                    or preflight.get('attachment_id') != record['attachment']['id']):
                errors.append('Preflight evidence does not match the approved backup and independent record.')
        except (OSError, ValueError, TypeError) as exc:
            errors.append('Missing or invalid preflight evidence: ' + str(exc))
        checks = result.get('checks', {})
        if set(checks) != set(expected):
            errors.append('Attachment result does not contain exactly the four configured checks.')
        for check in expected:
            item = checks.get(check, {})
            if item.get('status') != 'passed' or item.get('probe_id') != check:
                errors.append('Missing passing attachment assertion: ' + check)
            required_files = STAGE_CHECK_FILES.get(check, [])
            if item.get('evidence') != required_files:
                errors.append('Attachment assertion evidence references unexpected stage files: ' + check)

        stage_values: dict[str, dict[str, Any]] = {}
        database_names = {
            'before_upgrade': run['run_id'] + '_migration',
            'after_upgrade': run['run_id'] + '_migration',
            'after_rollback': run['run_id'] + '_rollback',
        }
        current_commit = run['commit']
        source_commit = source_info['commit'] if source_info else ''
        for stage_name, (filename, _) in STAGES.items():
            path = dest / filename
            try:
                stage = read(path)
                if not isinstance(stage, dict):
                    raise ScenarioError('stage JSON must contain an object')
                if path.stat().st_size == 0:
                    raise ScenarioError('stage JSON is empty')
                stage_values[stage_name] = stage
                errors.extend(_check_stage(
                    stage, stage_name, database_names[stage_name],
                    source_commit if stage_name == 'after_rollback' else current_commit,
                    record, stage_name == 'after_rollback'))
            except (OSError, ValueError, TypeError) as exc:
                errors.append(f'Missing or invalid nonempty {filename}: {exc}')

        for filename, database in (
            ('restore-before-upgrade.txt', run['run_id'] + '_migration'),
            ('restore-rollback.txt', run['run_id'] + '_rollback'),
        ):
            try:
                text = (dest / filename).read_text(encoding='utf-8')
                expected_dump = str(Path(backup_entries[0]['path']).resolve()) if backup_entries else ''
                expected_archive = str(Path(store_entries[0]['path']).resolve()) if store_entries else ''
                if (not text.strip() or f'target_db={database}' not in text
                        or f'backup_dir={Path(run["backup_dir"]).resolve()}' not in text
                        or f'dump_file={expected_dump}' not in text
                        or f'filestore_archive={expected_archive}' not in text
                        or 'filestore_restored=yes' not in text):
                    errors.append(f'{filename} does not prove a full restore to its generated target.')
            except OSError:
                errors.append(f'Missing restore report: {filename}')
        if not (dest / 'upgrade.log').is_file() or (dest / 'upgrade.log').stat().st_size == 0:
            errors.append('Missing nonempty target upgrade log.')

    sealed = {item.get('path'): item.get('sha256') for item in execution.get('files', [])}
    required_evidence = {'attachment-record.json', 'preflight.json', *(value[0] for value in STAGES.values()),
                         'restore-before-upgrade.txt', 'restore-rollback.txt', 'upgrade.log'}
    for relative in required_evidence:
        path = (dest / relative).resolve()
        if dest.resolve() not in path.parents or not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            errors.append('Missing, empty, or unsafe attachment evidence: ' + relative)
        elif sealed.get(relative) != digest(path):
            errors.append('Unsealed attachment evidence: ' + relative)
    for check in expected:
        for relative in STAGE_CHECK_FILES.get(check, []):
            evidence_path = dest / relative
            if not evidence_path.is_file() or sealed.get(relative) != digest(evidence_path):
                errors.append('Attachment check references unsealed stage evidence: ' + check)
                break
    return errors


def _write_failure_result(env: dict[str, str], error: str, record: dict[str, Any] | None,
                          source: dict[str, Any] | None, stages: dict[str, dict[str, Any]],
                          restore_targets: list[str]) -> None:
    result = build_attachment_result(
        env.get('SF_CONFIDENCE_COMMIT', ''), env.get('SF_CONFIDENCE_RUN_ID', ''),
        record or {}, source, stages, restore_targets, [error], upgrade_exit_code=None)
    output = Path(env['SF_CONFIDENCE_RESULT'])
    _write_private_json(output, result)
    preflight_path = Path(env['SF_CONFIDENCE_ARTIFACTS']) / 'preflight.json'
    _write_private_json(preflight_path, {'schema_version': 1, 'status': 'blocked', 'error': error})


def run_scenario(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    record: dict[str, Any] | None = None
    source: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    stages: dict[str, dict[str, Any]] = {}
    restore_targets: list[str] = []
    upgrade_exit_code: int | None = None
    try:
        context = _validate_runtime(env)
        artifacts = context['artifacts']
        if (artifacts / 'result.json').exists():
            raise ScenarioError('Scenario evidence already exists; use a fresh release-confidence run.')
        backup = _inspect_backup(context)
        record_path = _private(args.attachment_record, 'Independent attachment record', directory=False)
        if record_path == artifacts or artifacts in record_path.parents or record_path == ROOT or ROOT in record_path.parents:
            raise ScenarioError('Independent attachment record must be outside both the repository and scenario evidence.')
        record = validate_attachment_record(read(record_path), backup['dump_sha256'])
        modules = backup['modules']
        source_path = _outside_workspace(Path(args.source_checkout), 'Source-version addon checkout')
        source = verify_source_checkout(source_path, args.source_ref, modules)

        _ensure_odoo_config(context)
        # Verify candidate and rollback source mount rewrites before the first destructive restore.
        preflight_probe = artifacts / 'preflight-probe.py'
        preflight_probe.write_text(
            _probe_source(record, 'before_upgrade', env['MIGRATION_TARGET_DB'],
                          env['SF_CONFIDENCE_COMMIT'], None), encoding='utf-8')
        os.chmod(preflight_probe, 0o444)
        _compose_for_probe(Path(env['RC_COMPOSE_FILE']), artifacts / 'preflight-candidate-compose.json',
                           preflight_probe, None)
        _compose_for_probe(Path(env['RC_COMPOSE_FILE']), artifacts / 'preflight-source-compose.json',
                           preflight_probe, Path(source['checkout']))
        _start_generated_database(context, args.restore_timeout)

        copied_record = artifacts / 'attachment-record.json'
        shutil.copyfile(record_path, copied_record)
        os.chmod(copied_record, 0o600)
        _write_private_json(artifacts / 'preflight.json', {
            'schema_version': 1,
            'status': 'passed',
            'backup_dump_sha256': backup['dump_sha256'],
            'backup_filestore_sha256': digest(backup['filestore_archive']),
            'attachment_id': record['attachment']['id'],
            'source_ref': source['ref'],
            'source_commit': source['commit'],
            'source_addon_manifests': source['manifest_info'],
        })

        upgrade_db = env['MIGRATION_TARGET_DB']
        rollback_db = env['MIGRATION_ROLLBACK_DB']
        _restore(context, backup, upgrade_db, artifacts / 'restore-before-upgrade.txt',
                 artifacts / 'restore-before-upgrade.log', args.restore_timeout)
        restore_targets.append(upgrade_db)
        stages['before_upgrade'] = _run_probe(
            context, record, 'before_upgrade', upgrade_db, env['SF_CONFIDENCE_COMMIT'], None, None,
            args.probe_timeout)

        upgrade_env = dict(env)
        upgrade_env['UPGRADE_DB_NAME'] = upgrade_db
        upgrade_proc = _run_logged(
            ['bash', 'scripts/ci/run_rc_validation.sh', 'upgrade'], artifacts / 'upgrade.log',
            upgrade_env, args.upgrade_timeout)
        upgrade_exit_code = upgrade_proc.returncode
        scenario_errors = []
        if upgrade_exit_code != 0:
            scenario_errors.append('Existing RC upgrade lane failed on the generated pre-upgrade target.')
            _write_private_json(artifacts / STAGES['after_upgrade'][0], {
                'schema_version': 1, 'stage': 'after_upgrade', 'database': upgrade_db,
                'addon_commit': env['SF_CONFIDENCE_COMMIT'], 'status': 'failed',
                'error': 'The existing RC upgrade lane returned a nonzero exit code.', 'checks': {},
            })
        else:
            try:
                stages['after_upgrade'] = _run_probe(
                    context, record, 'after_upgrade', upgrade_db, env['SF_CONFIDENCE_COMMIT'], None, None,
                    args.probe_timeout)
            except ScenarioError as exc:
                scenario_errors.append(str(exc))

        _restore(context, backup, rollback_db, artifacts / 'restore-rollback.txt',
                 artifacts / 'restore-rollback.log', args.restore_timeout)
        restore_targets.append(rollback_db)
        # Deliberately do not invoke the upgrade lane for rollback_db.
        stages['after_rollback'] = _run_probe(
            context, record, 'after_rollback', rollback_db, source['commit'],
            Path(source['checkout']), source['manifest_info'], args.probe_timeout)
        result = build_attachment_result(
            env['SF_CONFIDENCE_COMMIT'], env['SF_CONFIDENCE_RUN_ID'], record, source,
            stages, restore_targets, scenario_errors, upgrade_exit_code)
        _write_private_json(artifacts / 'result.json', result)
        if result['status'] != 'passed':
            return 1
        return 0
    except Exception as exc:
        message = str(exc)
        print('BLOCKED: ' + message, file=sys.stderr)
        if context is not None and env.get('SF_CONFIDENCE_RESULT') and env.get('SF_CONFIDENCE_ARTIFACTS'):
            try:
                _write_failure_result(env, message, record, source, stages, restore_targets)
            except (OSError, ValueError, TypeError, KeyError):
                pass
        return 1
    finally:
        # Cleanup targets only the generated Compose project. The private evidence/filestore stay intact.
        if context is not None and context.get('owns_generated_project'):
            cleanup_env = dict(context['env'])
            try:
                _run_logged(
                    ['bash', 'scripts/ci/run_rc_validation.sh', 'cleanup'],
                    context['artifacts'] / 'cleanup.log', cleanup_env, 120)
            except (OSError, ScenarioError):
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attachment-record', type=Path, required=True,
                        help='Private operator-recorded JSON inventory for one known attachment.')
    parser.add_argument('--source-checkout', type=Path, required=True,
                        help='Separate clean source-version addon checkout root.')
    parser.add_argument('--source-ref', required=True,
                        help='Full git commit SHA identifying the rollback source checkout.')
    parser.add_argument('--restore-timeout', type=int, default=3600)
    parser.add_argument('--upgrade-timeout', type=int, default=7200)
    parser.add_argument('--probe-timeout', type=int, default=900)
    args = parser.parse_args()
    if min(args.restore_timeout, args.upgrade_timeout, args.probe_timeout) <= 0:
        parser.error('All command timeouts must be positive.')
    return run_scenario(args)


if __name__ == '__main__':
    raise SystemExit(main())