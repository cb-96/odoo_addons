# Release runbook

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release
Release train: 2026.08

The canonical operator procedure for qualifying, upgrading and rolling back the
federation platform. Change-specific upgrade information (data migrations,
behaviour to verify, rollback per change) is recorded in the
[upgrade notes](upgrade-notes.md). Release qualification policy and acceptance
suites are in [release qualification](../release/README.md). First-time
installation is covered by the [deployment guide](deployment.md).

## Release at a glance

1. [Preconditions](#preconditions) are met.
2. The [documentation and migration review](#documentation-and-migration-review) passes.
3. [Release candidate qualification](#release-candidate-qualification) passes on the exact commit.
4. The [migration rehearsal](#migration-rehearsal-evidence) passes on an approved backup.
5. Read the [upgrade notes](upgrade-notes.md) for every change since the previous release.
6. Run the [upgrade dry run](#upgrade-dry-run), then the [production upgrade](#production-upgrade).
7. Complete the [post-upgrade verification](#post-upgrade-verification).
8. If needed, [roll back](#rollback).

## Preconditions

1. Confirm the target branch is merged and the working tree is clean enough to
   identify the intended release diff.
2. Confirm Docker services are healthy with the production compose file.
3. Confirm enough disk space exists for both a PostgreSQL dump and a filestore
   archive under `./backups/`.

## Documentation and migration review

Verify that documentation and contracts match the release:

```bash
python3 ci/check_doc_freshness.py
python3 ci/check_markdown_links.py
python3 ci/check_module_owners.py
python3 ci/check_openapi_contracts.py
python3 ci/check_release_train.py
```

If the release changed portal privilege boundaries, reporting SQL-view policy
or public route ownership, update the affected
[decision record](../architecture/decisions/README.md) in the same branch.

If the release contains model, view or controller changes, the migration-review
gate must pass and every affected module needs an entry in the
[upgrade notes](upgrade-notes.md) or an explicit migration script:

```bash
python3 ci/check_migration_review.py --base-ref origin/main
```

If the release adds a `sports_federation_*` addon or changes ownership, update
`MODULE_OWNERS.yaml` and the [module catalogue](../overview/modules.md). If it
changes retention or cleanup jobs, update [data retention](../reference/data-retention.md)
and confirm the cleanup crons match the documented windows.

## Release candidate qualification

The release-candidate readiness contracts cover role-separated access,
workflow recovery actions, portal usability surfaces, performance profile
metadata, and the required release evidence files. Run the static lane before
starting database qualification:

```bash
scripts/ci/run_rc_validation.sh static
```

The complete candidate sequence is:

```bash
scripts/ci/run_release_candidate.sh --backup-dir /path/to/approved-backup
```

The script performs the product-readiness and usability contract checks,
release-baseline lanes, and (when an approved backup is supplied) the migration
rehearsal. Record the candidate SHA, lane results, database names, and any
rollback observations with the release ticket. Browser lanes require a Chrome
executable; a candidate is not accepted when those lanes are silently skipped.

The release-candidate Odoo lanes run in the repository's `odoo:19` Docker
Compose runtime; a host Odoo checkout and `odoo-bin` are not required. The
baseline retains one isolated Compose project across its fresh-install,
focused, and same-version upgrade lanes, then removes it after evidence is
captured. If an interrupted run leaves the project behind, clean it with:

```bash
RC_COMPOSE_PROJECT=sf_rc_<project> scripts/ci/run_rc_validation.sh cleanup
```

### RC test scope

The release baseline tests federation addons during fresh installation and once
more on the same-version upgraded database. It does not include the broad Odoo
`standard` dependency suite. That suite runs separately through the scheduled or
manual **Upstream Odoo compatibility** workflow. Focused core, portal, and public
lanes are diagnostic commands and are not repeated in the baseline.

### RC lane failure visibility

Odoo lanes write to `odoo-rc.log`. On a non-zero exit the runner prints an error summary and the final 200 lines. gettext `Empty msgid` warnings alone do not explain exit code 1; use the first test failure or module-load traceback in the logfile. See also
[troubleshooting](troubleshooting.md#rc-install-exits-with-only-gettext-warnings).

### Operator documentation qualification

The RC static lane validates essential paths in [`docs/user-guide/competition-workflow.md`](../user-guide/competition-workflow.md) against menu XML.

### Machine-readable qualification evidence

Record every release-candidate lane against the immutable candidate commit. Evidence files are operational artifacts and must not be committed:

```bash
python3 ci/capture_release_evidence.py --lane install --status passed \
  --database sf_rc_validation --output artifacts/release/install.json
python3 ci/capture_release_evidence.py --lane restore --status passed \
  --database odoo_restore_drill --backup backups/release.dump \
  --output artifacts/release/restore.json
```

Archive the evidence directory with CI logs, database and filestore backup checksums, the migration invariant report, and the named rollback owner.

## Pre-release verification

Run the focused suites that cover the highest-risk federation workflows:

```bash
bash ci/run_tests.sh --suite portal_public_ops
bash ci/run_tests.sh --suite finance_reporting
bash ci/run_tests.sh --suite release_surfaces
```

If the release changed retention jobs or cleanup scope, also re-run the
affected module suites directly:

```bash
bash ci/run_tests.sh --module sports_federation_notifications
bash ci/run_tests.sh --module sports_federation_import_tools
bash ci/run_tests.sh --module sports_federation_reporting
```

These suites now include query-budget regression checks for the public-site,
portal, and reporting hotspots documented in `docs/development/testing.md`.

If the release changes the largest reporting SQL views, refresh the committed
`EXPLAIN` snapshots from a restored or staging database and review the diff in
`ci/explain_snapshots/` before promoting the release:

```bash
python3 ci/capture_explain_snapshots.py --db odoo_restore_drill
```

If the release changes only one module, also run that module directly before the
broader suites:

```bash
bash ci/run_tests.sh --module sports_federation_reporting
```

## Migration rehearsal evidence

Run the complete rehearsal against an approved database and filestore backup:

```bash
scripts/ci/run_migration_rehearsal.sh \
  --backup-dir /path/to/approved-backup \
  --rollback-owner "Release owner" \
  --rollback-trigger "Invariant comparison or acceptance validation fails" \
  --yes
```

The rehearsal creates pre-upgrade, post-upgrade, and rollback invariant snapshots;
validates exact counts for principal federation records; rejects ownership,
publication, fixture-link, and attachment metadata violations; runs the
role-separated operator acceptance lane; and writes a manifest containing the
backup checksum, rollback owner, rollback trigger, and evidence inventory.

Archive the generated `artifacts/release/migration/` directory with the candidate
logs. A release cannot proceed when the invariant comparison or operator
acceptance evidence is not `passed`.

### Odoo registry integrity

An Odoo process exit code of zero is not sufficient evidence of a clean upgrade.
The RC upgrade lane rejects a non-uninstalled
`sports_federation_competition_engine` module state before running Odoo, then
scans successful Odoo logs for inconsistent module states, missing dependencies,
and models declared but not loadable. Treat any such finding as a failed upgrade
and preserve the log; do not publish migration evidence as passed.

The October 13, 2026 rehearsal against backup `2026-10-11_114539` is blocked:
the restored database reports the retired engine as `to upgrade`. Its legacy
metadata includes persistent stage progression, match-slot, schedule-revision,
and workspace-presence rows. The rehearsal's zero exit and passing invariant
comparison do not clear this blocker; a reviewed, data-preserving migration and
rollback decision are required before a production-like upgrade can be called
clean.

If the restore drill or production upgrade fails, stop Odoo, preserve the
failed logs, restore the database and filestore backup, and restart the prior
release. Do not reinstall the removed engine as an ad-hoc rollback; use the
reviewed database migration or rollback procedure for the target release.

## Retiring the legacy competition engine

The legacy `sports_federation_competition_engine` addon is no longer present in
the source tree and must be removed through Odoo's normal uninstall lifecycle;
never force its `ir_module_module.state` with SQL. Before removal, upgrade
`sports_federation_tournament` to `19.0.1.6.0`. Its pre-migration archives any
non-null legacy planner fields on `federation.tournament` in the
administrator-only `retired_planner_settings` JSON field. The archive is for
audit/rollback only and is not read by current scheduling code.

On a disposable clone, run the normal module upgrade helper with
`--retire-legacy-engine --offline`. The helper first backs up the clone, then
uses Odoo shell to call `button_uninstall()` and commit the request; Odoo's
loader performs the actual metadata/field cleanup. Check that the legacy module
finishes as `uninstalled`, archived settings match the retired values, and
tournament, edition, event, entry, match, and format records/counts are
unchanged before repeating against production.

Production procedure: run the helper with `--retire-legacy-engine` and the full
installed addon set. It takes paired database/filestore backups, stops the live
Odoo service, queues the uninstall, and upgrades modules while the service is
offline. If any step fails,
preserve the failed database and logs for diagnosis; restore the paired backup
before restarting on the prior code. Do not manually drop legacy columns or
delete shared records as a workaround.

### Before upgrading a database that installed the legacy engine

The legacy monolithic competition engine is removed from the addon tree. The
replacement ownership chain is `sports_federation_competition_core`,
`sports_federation_registration`, `sports_federation_format`,
`sports_federation_calendar`, `sports_federation_scheduling`,
`sports_federation_schedule_approval`, and `sports_federation_matchday`.

Before upgrading a database that previously installed the legacy engine:

1. Take the database and filestore backups described above.
2. Run the upgrade script with `--dry-run` and confirm that the resolved module
   list contains the chain and does not contain the removed addon.
3. Inspect the target database's state for
   `sports_federation_competition_engine`; absence from the dry-run module list
   does not uninstall a module that remains registered in the database. The
   upgrade helper reports this state during dry runs and refuses a real upgrade
   unless it is `uninstalled`. If it is not, stop for the reviewed legacy-data
   migration. Do not force its state with SQL or uninstall it without reviewing
   the module-owned operational records.
4. Run the upgrade in a disposable restore of the backup first, then verify
   registration, format freeze, calendar capacity, scheduling, approval
   publication, and match-day operations. Review Odoo's upgrade output for
   registry errors as well as the process exit code; an exit code of zero does
   not make an inconsistent module registry a clean upgrade.
5. Record the dry-run output and restore-drill result with the release ticket;
   do not silently reinterpret legacy planner or published-schedule records.

### Migration decision gate

The invariant contract now records two blocking facts from every restored database:
`retired_competition_engine_not_upgradeable` and
`retired_engine_legacy_tables_remaining`. Both must be zero before the normal
upgrade lane is considered clean. A non-zero value is not auto-repaired: stop,
retain the restored backup unchanged, inventory the legacy module-owned records,
and attach the reviewed preserve/map/drop decision to the release evidence before
running a data-specific migration. This deliberately prevents an uninstall or SQL
state change from masquerading as a data-preserving migration.

### Legacy ownership-removal review record

The following checks are the minimum repository-side evidence to attach to
the release ticket:

```bash
bash -n ci/run_tests.sh
bash -n scripts/ci/run_rc_validation.sh
python3 ci/check_legacy_engine_removed.py
```

The shell checks and the loadability guard must pass. The database restore drill remains mandatory before production upgrade;
its output must be attached to the release ticket rather than inferred from
repository checks. No historical migration directory is reused for this
ownership removal, and no production record is silently rewritten.

Rollback is backup-based: stop the target release, preserve logs and the failed
database state for review, restore the pre-upgrade database and filestore, and
restart the previous release. If a data transformation is later required, it
must be introduced in a new reviewed migration with an explicit backfill and
rollback plan; reinstalling the removed addon is not an approved rollback.

## Upgrade dry run

Print the resolved module list and backup target before touching the database:

```bash
./scripts/upgrade_sports_federation.sh --db odoo --dry-run
```

If you need to restrict the release to a subset of modules:

```bash
./scripts/upgrade_sports_federation.sh --db odoo --modules sports_federation_reporting,sports_federation_portal --dry-run
```

## Backups

The upgrade script performs backups by default. It stores:

- `modules.txt` with the exact install/upgrade module list
- `<db>_<timestamp>.dump` as a PostgreSQL custom-format dump
- `filestore_<db>_<timestamp>.tar.gz` when a filestore exists under
  `./odoo-data/filestore/<db>`

Do not use `--skip-backup` for production releases.

Run the periodic restore drill against one of these backup directories before
or during each release train using the [backup and restore drill](#backup-and-restore-drill):

```bash
bash ci/restore_backup_drill.sh --backup-dir 2026-04-15_191410 --target-db odoo_restore_drill --dry-run
```

## Production upgrade

Run the upgrade during a maintenance window. The script backs up the database
and filestore, stops the live Odoo service so requests cannot hold locks needed
by schema updates, runs the upgrade in a one-off container, then starts the
service with the updated code. If the upgrade fails, it attempts to restore the
service automatically:

```bash
./scripts/upgrade_sports_federation.sh --db odoo
```

For a non-interactive upgrade that excludes demo data, use `--yes`. To include
the demo addon non-interactively, add `--install-demo`.

The script installs modules that are missing or uninstalled and upgrades
modules that are already installed. The upgrade command runs as a one-off
container while the live Odoo service is stopped, then Compose starts the live
service again:

- `docker compose run --rm --no-deps odoo odoo -c /etc/odoo/odoo.conf -d <db> -i <install_module_csv> -u <upgrade_module_csv> --stop-after-init`
- `docker compose up -d odoo`

`--skip-restart` leaves the service stopped after a successful upgrade; on a
failed upgrade the script still attempts to restore service availability.

The demo addon is excluded by default. Interactive runs ask whether
`sports_federation_demo` should be installed. Use `--install-demo` when that
choice is intentional and the upgrade is non-interactive.

## Post-upgrade verification

Verify these operator checkpoints immediately after the upgrade:

1. Open Federation > Reporting > Operator Checklist and confirm there are no
   unexpected blocked queues.
2. Open Federation > Administration > Configuration > Report Schedules and confirm there are no new
   `Last Run Failed` schedules.
3. Open Federation > Administration > Data Exchange > Inbound Deliveries and confirm there are no
   unexpected `failed` or `processed_with_errors` deliveries.
4. Validate the public and portal release surfaces manually if the release
   touched them:
   - `/web/login`
   - `/competitions`
   - `/competitions/<edition-slug>/register?division_id=<division-id>`
   - `/my/teams/new`
   - `/my/season-registration/new`
   - `/my/compliance`
5. Trigger one scheduled report manually from **Federation > Administration > Configuration >
   Report Schedules** if the release touched reporting code.

## Integration partner token rotation

After any release that modifies integration partner credentials, or on a
scheduled rotation cycle, rotate partner tokens using the following procedure:

**When to rotate:**
- After upgrading `sports_federation_import_tools` (any release that changed
  token storage, authentication, or the integration controller surface).
- When the `token_rotation_required` flag is set to `True` on a partner record
  (visible in Federation > Administration > Data Exchange > Integration Partners).
- On a periodic schedule — at minimum once per year or whenever a partner
  personnel change occurs.

**How to rotate (back-office procedure):**

1. Open **Federation > Administration > Data Exchange > Integration Partners**.
2. Filter for partners where **Token Rotation Required** is checked, or where
   **Last Rotated On** is older than the rotation policy window.
3. For each partner, open the form and click **Rotate Token** (requires
   Federation Manager group). Confirm the dialog.
4. The wizard reveals the new raw token **once** (it cannot be retrieved again).
   Copy it immediately and deliver it to the partner over a secure channel
   (not email in plain text).
5. The `token_rotation_required` flag clears automatically after a successful
   rotation.

**After a migration from plaintext storage:**

If `sports_federation_import_tools` was upgraded from a version prior to
`19.0.1.2.0`, existing plaintext tokens were hashed in place and flagged for
rotation by the post-migration script. Partners with `Token Rotation Required`
set to `True` are still functional (their hashed token verifies correctly)
but should be rotated and re-issued at the next opportunity.

**Verification:**

After rotation, ask the partner to make one authenticated test call and confirm
a `200 OK` response to `/integration/v1/contracts`. A `401` response with
`access_denied` indicates the token was not delivered correctly.

## Rollback

If the upgrade must be rolled back:

1. Stop or scale down the Odoo service to prevent new writes.
2. Restore the PostgreSQL dump from the relevant backup directory.
3. Restore the matching filestore archive.
4. Restart the Odoo service.
5. Re-run the post-upgrade verification checklist against the restored system.

Example restore outline:

```bash
docker compose stop odoo
dropdb -U odoo odoo
createdb -U odoo odoo
pg_restore -U odoo -d odoo backups/<timestamp>/odoo_<timestamp>.dump
tar -xzf backups/<timestamp>/filestore_odoo_<timestamp>.tar.gz -C odoo-data/filestore
docker compose up -d odoo
```

Adjust database names and paths to match the selected backup directory.

## Backup and restore drill

Run at least once per release train and after backup, compose, or filestore
layout changes:

```bash
bash ci/restore_backup_drill.sh \
   --backup-dir <backup-directory> \
   --target-db odoo_restore_drill --dry-run
```

Then run without `--dry-run`. Confirm the dump, `modules.txt`, and optional
filestore are restored, every listed module is present, secrets are replaced in
the acceptance environment, health/integrity checks pass, and scheduled jobs
remain disabled until verification completes. Record the date, backup, target
database, and outcome in the release log, then drop the disposable DB.

## Release acceptance checklist

- [ ] Domain-integrity gate is green for every active division.
- [ ] Workflow, portal ownership, and security certification is green.
- [ ] Performance, concurrency, and migration checks are green.
- [ ] Restore and operations verification is green.
- [ ] Static CI, fresh install, restored-database upgrade, full Odoo tests,
         frontend tests, and production-like smoke tests are green.
- [ ] Backup/restore rehearsal, artifact checksum, rollback owner, and rollback
         trigger are recorded.

## Production gates

- **Domain integrity:** played or published history must not be removed by
   cascades; stage, gameday, match, participant, and progression records must
   remain inside their division.
- **Security:** all cross-club substitution tests must deny access; modifying
   routes must be authenticated, state-checked, ownership-scoped, and CSRF
   protected.
- **Performance and concurrency:** validate migration indexes with
   `EXPLAIN (ANALYZE, BUFFERS)` on anonymized production-like data; preserve
   revision and domain invariants for slot assignment, publication, deletion,
   registration, roster editing, and result approval.
- **Operational health:** run the sanitized operational health snapshot after
   restore and upgrade, then execute the canonical smoke journeys.

## Release train convention

This runbook and the [roadmap](../roadmap.md) are the two authoritative release-train
surfaces. Use `YYYY.MM` for the active train identifier and update both files
when the operating window changes. Before cutting a new train:

1. Archive or replace superseded roadmap commitments.
2. Align the `Release train:` metadata in this file and `docs/roadmap.md`.
3. Confirm the [upgrade notes](upgrade-notes.md) cover every change in the train.
4. Run documentation, migration, workflow, and release checks before promotion.
