# Restore Verification Checklist

Last updated: 2026-04-18
Owner: Federation Platform Team
Last reviewed: 2026-04-18
Review cadence: Every release

Use this checklist for the periodic backup-restore drill that validates the
federation backup layout, PostgreSQL restore path, and filestore handling.

## Minimum Cadence

- Run at least once per active release train.
- Re-run after backup automation, compose topology, or filestore layout changes.

## Inputs

- A backup directory produced by `./scripts/upgrade_sports_federation.sh`
- A disposable target database name such as `odoo_restore_drill`
- Access to the project `docker-compose.yaml` and database service

## Drill Command

```bash
bash addons/ci/restore_backup_drill.sh --backup-dir 2026-04-15_191410 --target-db odoo_restore_drill
```

Use `--dry-run` first when validating a new backup directory or compose setup.

## Verification Steps

1. Confirm the restore script resolves the expected dump, `modules.txt`, and optional filestore archive.
2. Confirm the target database is recreated successfully and the restore finishes without `pg_restore` errors.
3. Confirm the script verifies every module listed in `modules.txt` against the restored database.
4. If a filestore archive was present, confirm the restored directory exists under `odoo-data/filestore/<target_db>`.
5. Record the drill date, backup directory, target database, and outcome in the release notes or operator log.
6. Drop the disposable restore-drill database when the verification window is complete.

## Failure Follow-Up

- Missing dump or `modules.txt`: treat the backup as incomplete and investigate the upgrade backup step.
- Missing restored modules: treat the drill as failed and inspect the backup snapshot before the next production upgrade.
- Filestore extraction failure: block releases that depend on file-backed workflows until a clean drill succeeds.