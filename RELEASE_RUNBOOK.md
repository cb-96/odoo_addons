# Release Runbook

Last updated: 2026-09-03
Owner: Federation Platform Team
Last reviewed: 2026-09-03
Review cadence: Every release
Release train: 2026.08

This runbook is the canonical operator checklist for promoting the federation
stack with repeatable verification, upgrade, and rollback steps.

## Preconditions

1. Confirm the target branch is merged and the working tree is clean enough to
   identify the intended release diff.
2. Confirm Docker services are healthy with the production compose file.
3. Confirm enough disk space exists for both a PostgreSQL dump and a filestore
   archive under `./backups/`.

## Documentation Freshness

Before cutting a release, verify that the freshness-tracked docs still match the
change set whenever route ownership, architecture, CI policy, or operational
guidance changed:

```bash
python3 addons/ci/check_doc_freshness.py
python3 addons/ci/check_markdown_links.py
python3 addons/ci/check_module_owners.py
python3 addons/ci/check_openapi_contracts.py
```

If the release changed any tracked surface, update the affected document or
archive it in the same release branch before proceeding.

If the release changed portal privilege boundaries, reporting SQL view policy,
or canonical public route ownership, review the affected record under `adr/`
and update it in the same release branch when the decision changed.

If the release includes model, view, or controller ownership changes, confirm
the migration-review gate passes and that every affected module has either
release-note coverage or an explicit migration script:

```bash
python3 addons/ci/check_migration_review.py --base-ref origin/main
```

For the same release branch, record migration evidence and rollback notes in
this runbook:

```bash
# add the commands, outcomes, rollback triggers, and SQL/drop steps
${EDITOR:-vi} addons/RELEASE_RUNBOOK.md
```

### Portal controller-load repair evidence

The portal repair removes the stale re-export of the deleted V1 workspace
controller, restores the tournament-registration view in the manifest data
order, and keeps officiating assignment visibility limited to live current
publications. No database migration is required; the portal manifest is bumped
from `19.0.4.0.0` to `19.0.4.1.0`.

### Formatting-only model review evidence

The 2026-09-03 formatting change touched model files in
`sports_federation_base`, `sports_federation_competition_core`,
`sports_federation_format`, `sports_federation_import_tools`,
`sports_federation_notifications`, `sports_federation_reporting`,
`sports_federation_schedule_approval`, and
`sports_federation_scheduling`. It made no schema, data, or workflow changes,
so no database migration is required. The migration-review dry run must include
this record and pass before release promotion.

Dry-run evidence captured on 2026-08-23:

```text
./scripts/upgrade_sports_federation.sh --db odoo --dry-run
Exit code: 0
Upgrade: sports_federation_base,...,sports_federation_portal,...,sports_federation_venues
Install: none
```

Focused verification:

```text
bash ci/run_tests.sh --module sports_federation_portal
Exit code: 0; 116 tests run, 116 passed, 0 failed, 0 errors; 30 post-tests
```

Rollback is the standard backup restore procedure in this runbook. Do not
restore the deleted V1 controller or broaden portal publication access as a
rollback workaround.

### Release-candidate readiness review

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

If the release changes addon responsibility boundaries or adds a new
`sports_federation_*` module, update `MODULE_OWNERS.yaml` in the same release
branch and rerun the registry check before cutting the release.

If the release changes log retention, staged-delivery cleanup, or generated
report artifact handling, update `DATA_RETENTION_POLICY.md` in the same branch
and confirm the affected cleanup crons still match the documented windows.

## Pre-Release Verification

Run the focused suites that cover the highest-risk federation workflows:

```bash
bash addons/ci/run_tests.sh --suite portal_public_ops
bash addons/ci/run_tests.sh --suite finance_reporting
bash addons/ci/run_tests.sh --suite release_surfaces
```

If the release changed retention jobs or cleanup scope, also re-run the
affected module suites directly:

```bash
bash addons/ci/run_tests.sh --module sports_federation_notifications
bash addons/ci/run_tests.sh --module sports_federation_import_tools
bash addons/ci/run_tests.sh --module sports_federation_reporting
```

These suites now include query-budget regression checks for the public-site,
portal, and reporting hotspots documented in `TESTING_GUIDE.md`.

If the release changes the largest reporting SQL views, refresh the committed
`EXPLAIN` snapshots from a restored or staging database and review the diff in
`addons/ci/explain_snapshots/` before promoting the release:

```bash
python3 addons/ci/capture_explain_snapshots.py --db odoo_restore_drill
```

If the release changes only one module, also run that module directly before the
broader suites:

```bash
bash addons/ci/run_tests.sh --module sports_federation_reporting
```

## Upgrade Dry Run

Print the resolved module list and backup target before touching the database:

```bash
./scripts/upgrade_sports_federation.sh --db odoo --dry-run
```

If you need to restrict the release to a subset of modules:

```bash
./scripts/upgrade_sports_federation.sh --db odoo --modules sports_federation_reporting,sports_federation_portal --dry-run
```

### Competition ownership change evidence

The legacy monolithic competition engine is removed from the addon tree. The
replacement ownership chain is `sports_federation_competition_core`,
`sports_federation_registration`, `sports_federation_format`,
`sports_federation_calendar`, `sports_federation_scheduling`,
`sports_federation_schedule_approval`, and `sports_federation_matchday`.

Before upgrading a database that previously installed the legacy engine:

1. Take the database and filestore backups described above.
2. Run the upgrade script with `--dry-run` and confirm that the resolved module
   list contains the chain and does not contain the removed addon.
3. Run the upgrade in a disposable restore of the backup first, then verify
   registration, format freeze, calendar capacity, scheduling, approval
   publication, and match-day operations.
4. Record the dry-run output and restore-drill result with the release ticket;
   do not silently reinterpret legacy planner or published-schedule records.

If the restore drill or production upgrade fails, stop Odoo, preserve the
failed logs, restore the database and filestore backup, and restart the prior
release. Do not reinstall the removed engine as an ad-hoc rollback; use the
reviewed database migration or rollback procedure for the target release.

### Legacy ownership-removal review record

The repository-side review for this ownership change was completed against the
recorded base commit before preparing the release patch. The following checks
are the minimum evidence to attach to the release ticket:

```bash
bash -n addons/ci/run_tests.sh
bash -n addons/scripts/ci/run_rc_validation.sh
python3 addons/ci/check_legacy_engine_removed.py
git -C addons apply --check addons/legacy_removal.patch
```

The shell checks, loadability guard, and clean-worktree patch check must all
pass. The database restore drill remains mandatory before production upgrade;
its output must be attached to the release ticket rather than inferred from
repository checks. No historical migration directory is reused for this
ownership removal, and no production record is silently rewritten.

Rollback is backup-based: stop the target release, preserve logs and the failed
database state for review, restore the pre-upgrade database and filestore, and
restart the previous release. If a data transformation is later required, it
must be introduced in a new reviewed migration with an explicit backfill and
rollback plan; reinstalling the removed addon is not an approved rollback.

## Backups

The upgrade script performs backups by default. It stores:

- `modules.txt` with the exact install/upgrade module list
- `<db>_<timestamp>.dump` as a PostgreSQL custom-format dump
- `filestore_<db>_<timestamp>.tar.gz` when a filestore exists under
  `./odoo-data/filestore/<db>`

Do not use `--skip-backup` for production releases.

Run the periodic restore drill against one of these backup directories before
or during each release train using the restore checklist in this runbook:

```bash
bash addons/ci/restore_backup_drill.sh --backup-dir 2026-04-15_191410 --target-db odoo_restore_drill --dry-run
```

## Production Upgrade

Run the upgrade and let the script restart the live Odoo service afterward so
Python changes are loaded by the running web container:

```bash
./scripts/upgrade_sports_federation.sh --db odoo
```

For a non-interactive upgrade that excludes demo data, use `--yes`. To include
the demo addon non-interactively, add `--install-demo`.

The script installs modules that are missing or uninstalled, upgrades modules
that are already installed, and restarts the Odoo service. It runs:

- `odoo -c /etc/odoo/odoo.conf -d <db> -i <install_module_csv> -u <upgrade_module_csv> --stop-after-init`
- `docker compose restart odoo`

The demo addon is excluded by default. Interactive runs ask whether
`sports_federation_demo` should be installed. Use `--install-demo` when that
choice is intentional and the upgrade is non-interactive.

## Post-Upgrade Verification

Verify these operator checkpoints immediately after the upgrade:

1. Open Federation > Reporting > Operator Checklist and confirm there are no
   unexpected blocked queues.
2. Open Federation > Reporting > Report Schedules and confirm there are no new
   `Last Run Failed` schedules.
3. Open Federation > Import Tools > Inbound Deliveries and confirm there are no
   unexpected `failed` or `processed_with_errors` deliveries.
4. Validate the public and portal release surfaces manually if the release
   touched them:
   - `/web/login`
   - `/tournaments`
   - `/tournaments/<slug>/register`
   - `/my/teams/new`
   - `/my/season-registration/new`
   - `/my/compliance`
5. Trigger one scheduled report manually from Federation > Reporting > Report
   Schedules if the release touched reporting code.

## Integration Partner Token Rotation

After any release that modifies integration partner credentials, or on a
scheduled rotation cycle, rotate partner tokens using the following procedure:

**When to rotate:**
- After upgrading `sports_federation_import_tools` (any release that changed
  token storage, authentication, or the integration controller surface).
- When the `token_rotation_required` flag is set to `True` on a partner record
  (visible in Federation > Import Tools > Integration Partners).
- On a periodic schedule — at minimum once per year or whenever a partner
  personnel change occurs.

**How to rotate (back-office procedure):**

1. Open **Federation > Import Tools > Integration Partners**.
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

---

## Upgrade Path Notes (per release train)

This section records DB migrations, new `ir.config_parameter` keys, deprecated
field removals, and module install order changes introduced in each release.
Add a subsection here for every release train that makes schema or behavioural
changes. Reference the compatibility table in `INTEGRATION_CONTRACTS.md` for
route retirement dates.

### Release 2026.05

**DB migrations**: None.

### Release 2026.08

**DB migrations**: None. The roster match-sheet change only suppresses the
interactive match creation side effect while Odoo loads demo fixtures; normal
ORM-created matches still receive their draft home and away sheets. The demo
fixture was also aligned with current participant eligibility and compliance
expiry-date validation.

**Validation evidence**: A fresh isolated install with demo data enabled passed
the demo module tests (5 passed, 0 failed, 0 errors) and did not report the
`federation_match_sheet_unique_match_team_side` violation.

**Rollback**: Revert the additive code and fixture changes. No database
backfill, schema reversal, or migration artifact is required.

### Public-site route ownership review

**DB migrations**: None. The public-site controller route ownership change
does not alter persisted data or the public API contract.

**Dry-run evidence**: `python ci/check_migration_review.py --files
sports_federation_public_site/controllers/public_competitions.py
RELEASE_RUNBOOK.md` exited with code 0, confirming that the controller change
has release-review evidence.

**Rollback**: Revert the controller change and redeploy the prior application
revision. No database restore or data backfill is required.

## Release train convention

This runbook and `ROADMAP.md` are the two authoritative release-train
surfaces. Use `YYYY.MM` for the active train identifier and update both files
when the operating window changes. Before cutting a new train:

1. Archive or replace superseded roadmap commitments.
2. Align the `Release train:` metadata in this file and `ROADMAP.md`.
3. Confirm module release notes and migration evidence use the same train.
4. Run documentation, migration, workflow, and release checks before promotion.

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

## Backup and restore drill

Run at least once per release train and after backup, compose, or filestore
layout changes:

```bash
bash addons/ci/restore_backup_drill.sh \
   --backup-dir <backup-directory> \
   --target-db odoo_restore_drill --dry-run
```

Then run without `--dry-run`. Confirm the dump, `modules.txt`, and optional
filestore are restored, every listed module is present, secrets are replaced in
the acceptance environment, health/integrity checks pass, and scheduled jobs
remain disabled until verification completes. Record the date, backup, target
database, and outcome here or in the release log, then drop the disposable DB.

## Migration evidence and rollback record

For every migration-sensitive change, record the affected modules, migration
or ownership surfaces, command output summary, test result, and known warnings
in the release notes. Record rollback triggers, backup requirements, migration
artifacts, and any index or data reversal in the same release entry. The
validated 2026.06 tournament migration backfilled missing match schedule and
round fields and added five operational indexes; its rollback path is restoring
the paired database/filestore or dropping those indexes when only index
rollback is required. The 2026.08 workspace and portal ownership cleanup was
rollback-neutral.

**New `ir.config_parameter` keys**:

| Key | Purpose | Default |
|---|---|---|
| `sports_federation.rate_limit.<scope>.limit` | Per-scope rate-limit ceiling override | See `_POLICIES` in `request_rate_limit.py` |
| `sports_federation.rate_limit.<scope>.window_seconds` | Per-scope window override | See `_POLICIES` |

**Deprecated field removals**: None.

**Module install order changes**: None. Default install order (tier 1 → 2 → 3 → 4)
is unchanged; see `DEPLOYMENT_GUIDE.md`.

**Behaviour changes**:

- Rate-limit policies are now overridable at runtime via `ir.config_parameter`
  without a code deployment. See `openapi/ERROR_CODES.md` for per-scope limits.
- Integration partner tokens are now stored hashed. Existing plaintext tokens
  were migrated in place and flagged `token_rotation_required = True`. Rotate
  all partner tokens within one release cycle.

**Scheduled actions to verify**:

| Action | Expected state after upgrade |
|---|---|
| `Federation: GC Rate Limit Buckets` | Active, interval 1 hour |
| `Federation: GC Staged Deliveries` | Active, interval 1 day |
| `Federation: Expire Player Licenses` | Active, interval 1 day |

## Upgrade evidence: schedule publication and match-day operations 19.0.2

Affected upgrades:

- `sports_federation_schedule_approval` `19.0.2.1.0` to `19.0.2.2.0`
- `sports_federation_matchday` `19.0.2.0.0` to `19.0.2.1.0`

Dry-run procedure:

```bash
odoo-bin -d RC_DATABASE \
   -u sports_federation_schedule_approval,sports_federation_matchday \
   --stop-after-init
```

Verify that publication `matchday_id` values are populated, each match day has
at most one `live` publication, existing published matches have
`operational_slot_id = published_slot_id`, and the publication integrity contract
and module tests pass. The approval migration creates a partial unique index for
one live publication per match day. Existing data is safe because the preceding
implementation permitted at most one live publication for the broader edition.

Before upgrading, take a database backup. Rollback requires restoring that
backup because the new publication uniqueness semantics and operational audit
fields are persistent. Do not downgrade only the addon code after operators have
recorded live deviations.
## Portal cutover 19.0.4.0.0

Upgrade `sports_federation_portal` after the competition, registration,
schedule-approval and match-day modules. The migration closes open operation
tasks projected from V1 tournament registrations. It does not delete business
records.

```bash
odoo-bin -d RC_DATABASE -u sports_federation_portal --stop-after-init
python ci/check_portal_competition_ownership.py
python ci/check_portal_sudo_guard.py
bash ci/run_tests.sh --module sports_federation_portal
```

Verify /my/competitions, /my/competition-entries, /my/match-days and one match-day operations page. Confirm that draft schedules and superseded publications do not appear.

Rollback requires a database restore if entries or portal audit events were created after cutover.

## officials and standalone-match cleanup

Upgrade `sports_federation_tournament`, `sports_federation_officiating`, and
`sports_federation_portal` together after taking a verified database backup.
The tournament migration permanently removes test-only standalone matches and
their dependent records.

```bash
odoo-bin -d RC_DATABASE \
  -u sports_federation_tournament,sports_federation_officiating,sports_federation_portal \
  --stop-after-init
python ci/check_officiating_contract.py
```

Verify that the standalone-match count is zero, create officials through a
current live match-day publication, and confirm that the official self-service
portal shows current assignments plus retained history.

## competition-entry cutover 19.0.5.0.0

Upgrade registration, portal, public site and reporting together after a verified
backup. The portal migration permanently drops the test-only V1 tournament
registration table.

```bash
odoo-bin -d RC_DATABASE -u sports_federation_registration,sports_federation_portal,sports_federation_public_site,sports_federation_reporting --stop-after-init
python ci/check_registration_contract.py
python ci/check_access_csv_integrity.py
```

## Machine-readable qualification evidence

Record every release-candidate lane against the immutable candidate commit. Evidence files are operational artifacts and must not be committed:

```bash
python3 ci/capture_release_evidence.py --lane install --status passed \
  --database sf_rc_validation --output artifacts/release/install.json
python3 ci/capture_release_evidence.py --lane restore --status passed \
  --database odoo_restore_drill --backup backups/release.dump \
  --output artifacts/release/restore.json
```

Archive the evidence directory with CI logs, database and filestore backup checksums, the migration invariant report, and the named rollback owner.


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
