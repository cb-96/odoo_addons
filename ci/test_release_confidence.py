"""Harness unit tests use synthetic log fixtures, not application test evidence."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from release_confidence import (
    inspect_log, isolated_compose, safe_archive, validate_scenario, digest,
    runtime_env, validate_attachment_scenario_command, verify, write,
)
from release_confidence_adapter import build_result
from attachment_restore_scenario import (
    CHECKS as ATTACHMENT_CHECKS,
    STAGES as ATTACHMENT_STAGES,
    build_attachment_result,
    run_scenario as run_attachment_scenario,
    _start_generated_database,
    validate_attachment_record,
    validate_attachment_evidence,
    verify_source_checkout,
)

class ConfidenceTests(unittest.TestCase):
    def test_real_odoo_summary_format(self):
        self.assertFalse(inspect_log("0 failed, 0 error(s) of 93 tests when loading database", True))
    def test_zero_tests_blocked(self):
        self.assertTrue(inspect_log('0 failed, 0 error of 0 tests', True))
    def test_missing_summary_blocked(self):
        self.assertTrue(inspect_log('Process exited successfully', True))
    def test_failure_and_skip_blocked(self):
        for text in ('1 failed, 0 error of 8 tests', '0 failed, 2 errors of 8 tests', 'skipped browser test', 'Some modules have inconsistent states'):
            self.assertTrue(inspect_log(text, True))
    def test_nonzero_clean_summary(self):
        self.assertFalse(inspect_log('0 failed, 0 error of 8 tests', True))
    def test_compose_isolation(self):
        c = {'name': 'prod', 'services': {'ci-db': {'ports': ['5432:5432']}, 'ci-odoo': {'network_mode': 'host', 'volumes': []}}, 'networks': {'prod': {'external': True}}}
        result = isolated_compose(c, Path('/tmp/private-filestore'))
        self.assertTrue(result['networks']['default']['internal'])
        self.assertNotIn('ports', result['services']['ci-db'])
        self.assertNotIn('network_mode', result['services']['ci-odoo'])
        self.assertEqual(result['services']['ci-odoo']['volumes'][-1]['target'], '/var/lib/odoo/filestore')
    def test_unsafe_compose_rejected(self):
        for c in ({'services': {'production': {}}}, {'services': {'ci-db': {}, 'ci-odoo': {'privileged': True}}}):
            with self.assertRaises(ValueError): isolated_compose(c, Path('/tmp/x'))
    def test_production_environment_overridden(self):
        with patch.dict('os.environ', {'DB_NAME': 'production', 'RC_COMPOSE_PROJECT': 'production', 'PGHOST': 'prod'}):
            env = runtime_env({'run_id': 'sf_conf_unit', 'directory': '/tmp/unit', 'runtime_password': 'unit', 'backup_dir': '/tmp/backup', 'rollback_owner': 'unit', 'rollback_trigger': 'unit'})
        self.assertEqual(env['DB_NAME'], 'sf_conf_unit_install')
        self.assertNotIn('PGHOST', env)
    def test_unsafe_archive_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'bad.tar.gz'
            with tarfile.open(p, 'w:gz') as t:
                member = tarfile.TarInfo('../escape'); member.size = 1; t.addfile(member, io.BytesIO(b'x'))
            with self.assertRaises(ValueError): safe_archive(p)
    def test_missing_scenario_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(validate_scenario(Path(d), {'commit': 'c', 'run_id': 'r'}, ['check']))
    def test_generic_scenario_still_requires_an_observed_test_id(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / 'test.log').write_text('test evidence')
            write(p / 'result.json', {
                'commit': 'c', 'run_id': 'r', 'status': 'passed', 'tests_executed': 1,
                'checks': {'check': {'status': 'passed', 'probe_id': 'fabricated', 'evidence': ['test.log']}},
            })
            write(p / 'execution.json', {
                'commit': 'c', 'run_id': 'r', 'exit_code': 0,
                'files': [{'path': path.name, 'sha256': digest(path)} for path in (p / 'test.log', p / 'result.json')],
            })
            errors = validate_scenario(p, {'commit': 'c', 'run_id': 'r'}, ['check'], 'notification_recovery')
            self.assertTrue(any('Missing passing assertion: check' in error for error in errors))
    def test_attachment_scenario_accepts_only_the_specialized_driver(self):
        self.assertTrue(validate_attachment_scenario_command([
            'python3', 'ci/attachment_restore_scenario.py', '--attachment-record', '/private/record.json',
        ]))
        self.assertFalse(validate_attachment_scenario_command([
            'python3', 'ci/release_confidence_adapter.py', '--case-map', 'missing.json',
        ]))

    def test_changed_artifact_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); (p / 'test.log').write_text('test evidence')
            write(p / 'result.json', {'commit': 'c', 'run_id': 'r', 'status': 'passed', 'tests_executed': 1, 'checks': {'check': {'status': 'passed', 'test_id': 'test_real', 'evidence': ['test.log']}}})
            write(p / 'execution.json', {'commit': 'c', 'run_id': 'r', 'exit_code': 0, 'files': [{'path': f.name, 'sha256': digest(f)} for f in (p / 'test.log', p / 'result.json')]})
            self.assertFalse(validate_scenario(p, {'commit': 'c', 'run_id': 'r'}, ['check']))
            (p / 'test.log').write_text('changed')
            self.assertTrue(validate_scenario(p, {'commit': 'c', 'run_id': 'r'}, ['check']))
    def test_adapter_requires_test_observed(self):
        r = build_result('0 failed, 0 error of 1 tests', 0, {'check': 'Case.test_actual'}, ['check'], 'c', 'r')
        self.assertEqual(r['status'], 'failed')
    def test_adapter_passes_observed_clean_execution(self):
        r = build_result('Starting Case.test_actual ...\n0 failed, 0 error of 1 tests', 0, {'check': 'Case.test_actual'}, ['check'], 'c', 'r')
        self.assertEqual(r['status'], 'passed')
    def test_adapter_rejects_exit_failure(self):
        r = build_result('Starting Case.test_actual ...\n0 failed, 0 error of 1 tests', 1, {'check': 'Case.test_actual'}, ['check'], 'c', 'r')
        self.assertEqual(r['status'], 'failed')
    def test_adapter_rejects_skip(self):
        r = build_result('Starting Case.test_actual ... skipped\n0 failed, 0 error of 1 tests', 0, {'check': 'Case.test_actual'}, ['check'], 'c', 'r')
        self.assertEqual(r['status'], 'failed')

    def test_adapter_rejects_incomplete_map(self):
        r = build_result('Starting Case.test_actual ...\n0 failed, 0 error of 1 tests', 0, {}, ['check'], 'c', 'r')
        self.assertEqual(r['status'], 'failed')
    def test_wrong_run_scenario_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            write(p / 'result.json', {'commit': 'old', 'run_id': 'old', 'status': 'passed', 'tests_executed': 1, 'checks': {}})
            write(p / 'execution.json', {'commit': 'old', 'run_id': 'old', 'exit_code': 0, 'files': []})
            self.assertTrue(validate_scenario(p, {'commit': 'new', 'run_id': 'new'}, ['check']))
    def test_empty_evidence_blocks_full_gate(self):
        import release_confidence as rc
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            write(p / 'run.json', {'commit': 'c', 'run_id': 'r', 'status': 'passed', 'backup': [], 'sealed_artifacts': [], 'scenarios_spec_sha256': digest(rc.SPEC)})
            with patch.object(rc, 'git', side_effect=lambda *args: 'c' if args == ('rev-parse', 'HEAD') else ''):
                self.assertEqual(verify(p), 1)
            report = json.loads((p / 'release-confidence.json').read_text())
            self.assertIn('Missing baseline summary.', report['blockers'])
            self.assertEqual(report['status'], 'blocked')
    def test_safe_archive_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'good.tar.gz'
            with tarfile.open(p, 'w:gz') as t:
                member = tarfile.TarInfo('test_database/file'); member.size = 1; t.addfile(member, io.BytesIO(b'x'))
            safe_archive(p)


class AttachmentRestoreTests(unittest.TestCase):
    def setUp(self):
        self.payload = b'operator-recorded attachment fixture'
        self.record = {
            'schema_version': 1,
            'recorded_by': 'release operator',
            'recorded_at': '2026-10-29T12:00:00+00:00',
            'backup_dump_sha256': hashlib.sha256(b'approved database dump').hexdigest(),
            'attachment': {
                'id': 42,
                'name': 'known-document.pdf',
                'checksum': hashlib.sha1(self.payload).hexdigest(),
                'size': len(self.payload),
                'sha256': hashlib.sha256(self.payload).hexdigest(),
            },
        }

    def test_invalid_operator_record_fails_before_any_restore(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run_dir = root / 'run'
            artifacts = run_dir / 'scenarios' / 'attachment_restore'
            artifacts.mkdir(parents=True, mode=0o700)
            record_path = root / 'invalid-record.json'
            invalid = copy.deepcopy(self.record)
            del invalid['attachment']['size']
            write(record_path, invalid)
            record_path.chmod(0o600)
            env = {
                'SF_CONFIDENCE_RESULT': str(artifacts / 'result.json'),
                'SF_CONFIDENCE_ARTIFACTS': str(artifacts),
                'SF_CONFIDENCE_COMMIT': 'a' * 40,
                'SF_CONFIDENCE_RUN_ID': 'sf_conf_abcdef012345',
            }
            context = {
                'env': env,
                'artifacts': artifacts,
                'run_dir': run_dir,
                'run': {'run_id': env['SF_CONFIDENCE_RUN_ID'], 'commit': env['SF_CONFIDENCE_COMMIT']},
                'backup': root / 'backup',
            }
            args = type('Args', (), {
                'attachment_record': record_path,
                'source_checkout': root / 'unused-source',
                'source_ref': 'b' * 40,
                'restore_timeout': 5,
                'upgrade_timeout': 5,
                'probe_timeout': 5,
            })()
            with patch.dict('os.environ', env), \
                    patch('attachment_restore_scenario._validate_runtime', return_value=context), \
                    patch('attachment_restore_scenario._inspect_backup', return_value={
                        'dump_sha256': self.record['backup_dump_sha256'], 'modules': ['sports_federation_demo'],
                    }), \
                    patch('attachment_restore_scenario._restore') as restore, \
                    patch('attachment_restore_scenario._run_logged') as run_logged:
                self.assertEqual(run_attachment_scenario(args), 1)
            restore.assert_not_called()
            run_logged.assert_not_called()
            result = json.loads((artifacts / 'result.json').read_text())
            self.assertEqual(result['status'], 'failed')

    def test_database_start_requires_an_empty_generated_project(self):
        context = {
            'env': {
                'RC_COMPOSE_PROJECT': 'sf_conf_abcdef012345',
                'RC_COMPOSE_FILE': '/private/runtime/compose.json',
                'CI_POSTGRES_USER': 'odoo',
                'CI_POSTGRES_DB': 'postgres',
            },
            'artifacts': Path('/private/scenario'),
        }
        completed = subprocess.CompletedProcess([], 0, '', '')
        with patch(
            'attachment_restore_scenario._run_logged',
            side_effect=(completed, completed, completed),
        ) as run_logged:
            _start_generated_database(context, 30)

        self.assertEqual(run_logged.call_count, 3)
        self.assertEqual(run_logged.call_args_list[1].args[0][-4:], [
            'up', '-d', '--wait', 'ci-db',
        ])

    def test_database_start_refuses_existing_generated_project_containers(self):
        context = {
            'env': {
                'RC_COMPOSE_PROJECT': 'sf_conf_abcdef012345',
                'RC_COMPOSE_FILE': '/private/runtime/compose.json',
                'CI_POSTGRES_USER': 'odoo',
                'CI_POSTGRES_DB': 'postgres',
            },
            'artifacts': Path('/private/scenario'),
        }
        existing = subprocess.CompletedProcess([], 0, 'container-id\n', '')
        with patch('attachment_restore_scenario._run_logged', return_value=existing) as run_logged:
            with self.assertRaisesRegex(ValueError, 'already contains containers'):
                _start_generated_database(context, 30)

        run_logged.assert_called_once()

    def _source_checkout(self, root):
        checkout = root / 'source-addons'
        (checkout / 'sports_federation_demo').mkdir(parents=True)
        (checkout / 'sports_federation_demo' / '__manifest__.py').write_text(
            "{'name': 'Demo', 'version': '19.0.1.0.0'}\n", encoding='utf-8')
        subprocess.run(['git', 'init', str(checkout)], check=True, capture_output=True, text=True)
        subprocess.run(['git', '-C', str(checkout), 'config', 'user.name', 'CI Test'], check=True)
        subprocess.run(['git', '-C', str(checkout), 'config', 'user.email', 'ci@example.invalid'], check=True)
        subprocess.run(['git', '-C', str(checkout), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(checkout), 'commit', '-m', 'source fixture'], check=True, capture_output=True, text=True)
        commit = subprocess.run(
            ['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True,
            capture_output=True, text=True).stdout.strip()
        return checkout, commit

    def _stage(self, stage_name, database, addon_commit, rollback=False):
        attachment = self.record['attachment']
        checks = {
            'container_probe': True,
            'database_fields_match': True,
            'raw_size_matches': True,
            'raw_sha256_matches': True,
            'odoo_checksum_matches_sha1': True,
            'file_present': True,
            'file_readable': True,
            'file_size_matches': True,
            'file_sha256_matches_raw': True,
            'path_within_filestore': True,
            'source_manifests_match_mounted_checkout': True,
            'source_module_versions_match_restored_database': True,
        }
        return {
            'schema_version': 1,
            'stage': stage_name,
            'database': database,
            'addon_commit': addon_commit,
            'container_probe': True,
            'database_attachment': {
                'id': attachment['id'], 'name': attachment['name'],
                'checksum': attachment['checksum'], 'size': attachment['size'],
            },
            'raw': {'size': attachment['size'], 'sha256': attachment['sha256']},
            'odoo_checksum_sha1': attachment['checksum'],
            'full_path': '/var/lib/odoo/filestore/' + database + '/aa/' + 'a' * 40,
            'file': {
                'present': True, 'readable': True, 'size': attachment['size'],
                'sha256': attachment['sha256'], 'path_within_filestore': True,
            },
            'source_manifests_match_mounted_checkout': True,
            'source_module_versions_match_restored_database': True,
            'checks': checks,
        }

    def test_attachment_record_requires_all_independent_hashes_and_database_fields(self):
        record = validate_attachment_record(self.record, self.record['backup_dump_sha256'])
        self.assertEqual(record['attachment']['id'], 42)
        invalid = copy.deepcopy(self.record)
        del invalid['attachment']['sha256']
        with self.assertRaises(ValueError):
            validate_attachment_record(invalid, self.record['backup_dump_sha256'])
        with self.assertRaises(ValueError):
            validate_attachment_record(self.record, '0' * 64)

    def test_source_checkout_must_be_clean_at_stated_commit(self):
        with tempfile.TemporaryDirectory() as d:
            checkout, commit = self._source_checkout(Path(d))
            result = verify_source_checkout(checkout, commit, ['sports_federation_demo'])
            self.assertEqual(result['commit'], commit)
            self.assertIn('sports_federation_demo', result['manifest_info'])
            (checkout / 'untracked.txt').write_text('dirty', encoding='utf-8')
            with self.assertRaises(ValueError):
                verify_source_checkout(checkout, commit, ['sports_federation_demo'])

    def test_attachment_result_reports_only_checks_demonstrated_by_all_stages(self):
        commit = 'a' * 40
        source = {'checkout': '/tmp/source', 'ref': 'b' * 40, 'commit': 'b' * 40}
        stages = {
            'before_upgrade': self._stage('before_upgrade', 'sf_conf_abcdef012345_migration', commit),
            'after_upgrade': self._stage('after_upgrade', 'sf_conf_abcdef012345_migration', commit),
            'after_rollback': self._stage('after_rollback', 'sf_conf_abcdef012345_rollback', source['commit'], True),
        }
        result = build_attachment_result(
            commit, 'sf_conf_abcdef012345', self.record, source, stages,
            ['sf_conf_abcdef012345_migration', 'sf_conf_abcdef012345_rollback'], [])
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(set(result['checks']), set(ATTACHMENT_CHECKS))
        stages['after_rollback']['checks']['file_readable'] = False
        result = build_attachment_result(
            commit, 'sf_conf_abcdef012345', self.record, source, stages,
            ['sf_conf_abcdef012345_migration', 'sf_conf_abcdef012345_rollback'], [])
        self.assertEqual(result['checks']['known_file_readable_after_rollback']['status'], 'failed')
        self.assertEqual(result['checks']['restored_files_visible_inside_odoo_container']['status'], 'failed')

    def test_dedicated_validator_requires_three_sealed_stage_probes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            backup = root / 'approved-backup'
            backup.mkdir(mode=0o700)
            dump = backup / 'approved.dump'
            dump.write_bytes(b'approved database dump')
            archive = backup / 'filestore_approved.tar.gz'
            archive.write_bytes(b'approved filestore archive')
            modules_file = backup / 'modules.txt'
            modules_file.write_text('sports_federation_demo\n', encoding='utf-8')
            self.record['backup_dump_sha256'] = digest(dump)
            checkout, source_commit = self._source_checkout(root)
            source = verify_source_checkout(checkout, source_commit, ['sports_federation_demo'])
            commit = 'a' * 40
            run_id = 'sf_conf_abcdef012345'
            run = {
                'run_id': run_id, 'commit': commit, 'backup_dir': str(backup),
                'backup': [
                    {'path': str(dump), 'sha256': digest(dump)},
                    {'path': str(archive), 'sha256': digest(archive)},
                    {'path': str(modules_file), 'sha256': digest(modules_file)},
                ],
            }
            result_dir = root / 'scenario'
            result_dir.mkdir(mode=0o700)
            write(result_dir / 'attachment-record.json', self.record)
            write(result_dir / 'preflight.json', {
                'status': 'passed', 'backup_dump_sha256': digest(dump),
                'backup_filestore_sha256': digest(archive), 'attachment_id': 42,
            })
            stages = {}
            for stage_name, (filename, _) in ATTACHMENT_STAGES.items():
                database = run_id + ('_rollback' if stage_name == 'after_rollback' else '_migration')
                addon_commit = source_commit if stage_name == 'after_rollback' else commit
                stages[stage_name] = self._stage(stage_name, database, addon_commit, stage_name == 'after_rollback')
                write(result_dir / filename, stages[stage_name])
            for filename, database in (
                ('restore-before-upgrade.txt', run_id + '_migration'),
                ('restore-rollback.txt', run_id + '_rollback'),
            ):
                (result_dir / filename).write_text(
                    f'backup_dir={backup}\ndump_file={dump}\ntarget_db={database}\n'
                    f'filestore_archive={archive}\nfilestore_restored=yes\n', encoding='utf-8')
            (result_dir / 'upgrade.log').write_text('upgrade completed\n', encoding='utf-8')
            result = build_attachment_result(
                commit, run_id, self.record, source, stages,
                [run_id + '_migration', run_id + '_rollback'], [])
            write(result_dir / 'result.json', result)
            files = [
                {'path': path.name, 'sha256': digest(path)}
                for path in result_dir.iterdir() if path.is_file()
            ]
            execution = {'files': files, 'exit_code': 0}
            errors = validate_attachment_evidence(
                result_dir, run, list(ATTACHMENT_CHECKS), execution, result)
            self.assertEqual(errors, [])

            broken = json.loads((result_dir / 'after-rollback.json').read_text())
            broken['file']['sha256'] = '0' * 64
            write(result_dir / 'after-rollback.json', broken)
            execution['files'] = [
                {'path': path.name, 'sha256': digest(path)}
                for path in result_dir.iterdir() if path.is_file()
            ]
            errors = validate_attachment_evidence(
                result_dir, run, list(ATTACHMENT_CHECKS), execution, result)
            self.assertTrue(any('after_rollback' in error for error in errors))

if __name__ == '__main__': unittest.main()
