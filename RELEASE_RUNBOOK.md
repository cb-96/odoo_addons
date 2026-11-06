# Release Runbook

Last updated: 2026-09-09
Owner: Federation Platform Team
Last reviewed: 2026-09-09
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

### Transactional command ownership review evidence

The current release diff changes model-owned match-day cleanup and command
boundaries in `sports_federation_matchday`, `sports_federation_result_control`,
and `sports_federation_schedule_approval`. The changes were reviewed as
application and ownership behavior changes; no standalone migration script is
required. The normal addon upgrade path remains the deployment mechanism, with
the backup restore procedure below as the rollback path.

Dry-run evidence captured on 2026-09-09:

```text
./scripts/upgrade_sports_federation.sh --db odoo --dry-run
Exit code: 0
Install: none
Upgrade: sports_federation_base,sports_federation_calendar,
sports_federation_competition_core,sports_federation_compliance,
sports_federation_demo,sports_federation_discipline,
sports_federation_finance_bridge,sports_federation_format,
sports_federation_governance,sports_federation_import_tools,
sports_federation_matchday,sports_federation_notifications,
sports_federation_officiating,sports_federation_people,
sports_federation_portal,sports_federation_public_site,
sports_federation_registration,sports_federation_reporting,
sports_federation_result_control,sports_federation_rosters,
sports_federation_rules,sports_federation_schedule_approval,
sports_federation_scheduling,sports_federation_standings,
sports_federation_tournament,sports_federation_venues
```

The dry run only resolved the installed addon plan and did not modify the
database. If the upgrade fails, preserve the logs and failed database state,
then restore the pre-upgrade database and filestore backup before restarting
the previous release.

### Format progression and fixture ownership review evidence

The current format release hardens structure-scoped progression validation,
rejects ambiguous tied bracket results, makes Swiss pairing deterministic when
the first candidate pairing dead-ends, and synchronizes approved fixture
results through the authorized result-command boundary. These are model and
workflow ownership changes without a standalone schema migration. The normal
addon upgrade path remains the deployment mechanism, with database restore as
the rollback path.

Dry-run evidence captured on 2026-09-13:

```text
./scripts/upgrade_sports_federation.sh --db odoo --dry-run
Exit code: 0
Install: none
Upgrade: sports_federation_app,sports_federation_base,
sports_federation_calendar,sports_federation_competition_core,
sports_federation_compliance,sports_federation_demo,
sports_federation_discipline,sports_federation_finance_bridge,
sports_federation_format,sports_federation_governance,
sports_federation_import_tools,sports_federation_matchday,
sports_federation_notifications,sports_federation_officiating,
sports_federation_people,sports_federation_portal,
sports_federation_public_site,sports_federation_registration,
sports_federation_reporting,sports_federation_result_control,
sports_federation_rosters,sports_federation_rules,
sports_federation_schedule_approval,sports_federation_scheduling,
sports_federation_standings,sports_federation_tournament,
sports_federation_venues
```

Focused verification passed with the format addon and competition-core suite:

```text
bash ci/run_tests.sh --module sports_federation_format
Exit code: 0; 20 tests run, 20 passed, 0 failed, 0 errors

bash ci/run_tests.sh --suite competition_core
Exit code: 0; 248 tests run, 248 passed, 0 failed, 0 errors
```

Rollback requires restoring the pre-upgrade database and filestore backup;
do not bypass progression validation or fixture ownership checks as a
rollback workaround.

### Parental approval and game-day lineup upgrade review

Affected upgrades:

- `sports_federation_people` `19.0.1.1.0` to `19.0.1.2.0`
- `sports_federation_rosters` `19.0.1.5.1` to `19.0.1.6.0`

The People upgrade is additive: Odoo creates the new
`federation.player.parental.approval` table and its attachment-backed signed
document field. No existing player requires a backfill; the adult-league rule
only blocks players who are under 16 on the relevant participation date. The
Rosters upgrade changes workflow behavior but adds no stored schema: a team's
declared lineup is synchronized and approved once per explicit match day, with
tournament plus scheduled date as the legacy fallback.

Required dry run before promotion:

```bash
./scripts/upgrade_sports_federation.sh --db odoo \
  --modules sports_federation_people,sports_federation_rosters --dry-run
bash ./ci/run_tests.sh --suite people_rosters_rules
```

Patch-environment status on 2026-10-10: Python compilation, XML parsing, addon
integrity, ACL integrity, dependency drift, workflow contracts, documentation,
and focused source checks passed. The database dry run and Odoo test suite were
not executed because this patch environment has no Docker/Podman or Odoo
runtime. They remain mandatory release gates.

Rollback trigger: module installation/upgrade failure, an unexpected eligibility
blocker for an adult player or youth league, or inconsistent approved lineups in
one game-day scope. Because signed approvals create database rows and filestore
attachments, take a paired database/filestore backup before upgrading and
restore both to roll back after operators have created approval records. Do not
delete verified approvals or bypass the game-day synchronization as a rollback
workaround.

### Archived competitions hidden from the portal

Affected upgrade: `sports_federation_portal` `19.0.7.10.0` to `19.0.7.11.0`.

No schema change. Portal reads, the task projection and the portal ownership
checks now exclude entries, matches, lineups, referee duties and assignments,
game days and tasks of archived competitions and archived divisions. The
`post-migrate.py` script closes open operation tasks of competitions that were
already archived, so they leave the portal and the federation action queue.

Required dry run before promotion:

```bash
./scripts/upgrade_sports_federation.sh --db odoo \
  --modules sports_federation_portal --dry-run
bash ./ci/run_tests.sh --module sports_federation_portal
```

The upgrade log reports how many tasks were closed. Rollback is the standard
backup restore procedure. Without a restore, restoring a competition and its
divisions makes everything visible again, and the next task sync reopens its
tasks. Do not reopen tasks manually while the competition stays archived.

### Retiring the legacy competition engine

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

The release-candidate Odoo lanes run in the repository's `odoo:19` Docker
Compose runtime; a host Odoo checkout and `odoo-bin` are not required. The
baseline retains one isolated Compose project across its fresh-install,
focused, and same-version upgrade lanes, then removes it after evidence is
captured. If an interrupted run leaves the project behind, clean it with:

```bash
RC_COMPOSE_PROJECT=sf_rc_<project> scripts/ci/run_rc_validation.sh cleanup
```

If the release changes addon responsibility boundaries or adds a new
`sports_federation_*` module, update `MODULE_OWNERS.yaml` in the same release
branch and rerun the registry check before cutting the release.

If the release changes log retention, staged-delivery cleanup, or generated
report artifact handling, update `DATA_RETENTION_POLICY.md` in the same branch
and confirm the affected cleanup crons still match the documented windows.

### Archived rosters, archived-competition list and permanent deletion

Affected upgrades:

- `sports_federation_portal` `19.0.7.11.0` to `19.0.7.12.0`
- `sports_federation_competition_core` `19.0.1.7.0` to `19.0.1.8.0`

No schema change except the transient deletion wizard. The portal also hides
rosters, roster lines, season registrations and their tasks when every
competition the team plays that season (or the roster's own competition) is
archived. The portal `post-migrate.py` closes those tasks for competitions that
are already archived. Competition Core adds an Archived filter, a Restore
button and the system-administrator-only Delete permanently wizard.

Required dry run before promotion:

```bash
./scripts/upgrade_sports_federation.sh --db odoo \
  --modules sports_federation_competition_core,sports_federation_portal --dry-run
bash ./ci/run_tests.sh --module sports_federation_app
```

Rollback is the standard paired database and filestore backup restore.
Permanent deletion is irreversible by design; only a backup restore brings
deleted competitions back. Each deletion is logged at WARNING level and in
Settings > Technical > Logging under `sports_federation.force_delete`.


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
   - `/competitions`
   - `/competitions/<edition-slug>/register?division_id=<division-id>`
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

### Registration, publication and club-duty automation

**DB migrations**: three data migrations, all idempotent and logged.

| Module | Version | What it does |
|---|---|---|
| `sports_federation_registration` | 19.0.1.4.0 | Creates the missing confirmed participants of finalised team lists (one savepoint per set; ineligible teams are logged and skipped). |
| `sports_federation_rosters` | 19.0.1.12.0 | Prepares the roster of every participant in a running season and links existing rosters to the team's confirmed registration (one savepoint per participant). |
| `sports_federation_schedule_approval` | 19.0.2.6.0 | Sets playing area and venue from the published slot and moves published `draft` matches to `scheduled` (set-based SQL; no constraints re-run, no finance events created). |

Run the registration migration before the rosters one; the module order of an
upgrade already does this, and the rosters migration also covers participants
created before it.

**Behaviour changes**:

- Finalising a team list creates participants; participants create rosters.
- Publishing schedules matches, copies the slot's venue and playing area and, for
  rule sets with **Referees required per match** above 0 and **Ask clubs for
  officials on publication** on (default), creates the open club duties.
  Existing published schedules are not given duties retroactively; run
  **Plan Match-Day Officials** for them if wanted.
- The automatic venue-booking charge needs a configured `venue_booking` fee type
  with an amount; otherwise no charge and no implicit fee type.
- Roster, missing-roster, parental-consent, line-up and entry tasks now carry
  deadlines, so they sort, show as overdue and are covered by the due-soon reminder.

**Dry-run evidence**: `python ci/check_migration_review.py --files
sports_federation_rosters/migrations/19.0.1.12.0/post-migrate.py
sports_federation_registration/migrations/19.0.1.4.0/post-migrate.py
sports_federation_schedule_approval/migrations/19.0.2.6.0/post-migrate.py
RELEASE_RUNBOOK.md` exits with code 0. The Odoo database upgrade, ORM and HTTP
tests were not executed in the authoring environment; run the tagged tests
(`sf_participant_rosters`, `sf_task_deadlines`, `sf_auto_club_duties`,
`sf_publication`) and the migration rehearsal before promotion.

**Rollback**: restore the paired database and filestore taken before the upgrade
and deploy the previous code. Participants, rosters, duties and match states
created by the migrations or by publication are ordinary records; if only the
data must be undone, withdraw or delete the participants created for the
affected division, close the draft rosters, and set `state = 'draft'` and clear
`playing_area_id` for matches whose publication is removed. No schema change is
made, so no index or column needs dropping.

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


## Operator documentation qualification

The RC static lane validates essential paths in [`docs/COMPETITION_UI_WORKFLOW.md`](docs/COMPETITION_UI_WORKFLOW.md) against menu XML.


## RC test scope

The release baseline tests federation addons during fresh installation and once
more on the same-version upgraded database. It does not include the broad Odoo
`standard` dependency suite. That suite runs separately through the scheduled or
manual **Upstream Odoo compatibility** workflow. Focused core, portal, and public
lanes are diagnostic commands and are not repeated in the baseline.

## RC lane failure visibility

Odoo lanes write to `odoo-rc.log`. On a non-zero exit the runner prints an error summary and the final 200 lines. gettext `Empty msgid` warnings alone do not explain exit code 1; use the first test failure or module-load traceback in the logfile.

### Simplified competition workflow upgrade review

Affected upgrades:

- `sports_federation_base` `19.0.1.3.0` → `19.0.1.4.0`
- `sports_federation_competition_core` `19.0.1.5.1` → `19.0.1.6.0`
- `sports_federation_registration` `19.0.1.2.2` → `19.0.1.3.0`
- `sports_federation_scheduling` `19.0.3.5.0` → `19.0.3.6.0`
- `sports_federation_setup_flow` `19.0.3.0.0` → `19.0.4.0.0`
- `sports_federation_rosters` `19.0.1.6.0` → `19.0.1.7.0`
- `sports_federation_portal` `19.0.7.2.0` → `19.0.7.3.0`
- `sports_federation_navigation` new at `19.0.1.0.0`
- `sports_federation_app` `19.0.1.0.0` → `19.0.2.0.0`
- `sports_federation_demo` `19.0.1.1.0` → `19.0.1.2.0`

The setup-flow upgrade adds remembered preset/default columns on season competitions. The `19.0.4.0.0` post-migration backfills league/cup preset and format defaults without changing existing workflow states. New team, format, and lineup wizard records are transient. New task types reuse the existing task table. The new navigation integration addon updates only `ir.ui.menu` visibility/parent data and does not remove actions or permissions; the app entry point remains dependency-only.

Upgrade order follows dependencies: base, competition core, registration, format/calendar/scheduling/approval/setup flow, matchday/rosters, portal, app, then demo. Use the aggregate app upgrade for the supported installation:

```bash
./scripts/upgrade_sports_federation.sh --db odoo \
  --modules sports_federation_base,sports_federation_competition_core,sports_federation_registration,sports_federation_scheduling,sports_federation_setup_flow,sports_federation_rosters,sports_federation_portal,sports_federation_navigation,sports_federation_app --dry-run
bash ./ci/run_tests.sh --suite competition_core
bash ./ci/run_tests.sh --suite people_rosters_rules
bash ./ci/run_tests.sh --suite portal_public_ops
scripts/ci/run_rc_validation.sh install
scripts/ci/run_rc_validation.sh upgrade
scripts/ci/run_rc_validation.sh acceptance
```

Before promotion, verify one ordinary manager sees only Competition Hub under Competitions, an advanced user retains all owner workspaces and Administration recovery, Streamlined schedule/lineup/result transitions retain audit evidence, Independent Review retains separation of duties, and a missing parental approval blocks both roster and lineup submission.

Rollback requires the paired pre-upgrade database/filestore backup. Navigation can be restored by rolling back the app data update, but do not delete participant sets, entries, approvals, reviews, publications, match sheets, or audit/task records created after upgrade. Restore the full backup if persisted operations occurred.

## Minimal workspace and portal revision: upgrade review

Candidate source base: a9fbdebd0cd80e7122ae0e0a61637d6c5b763ebf.
See docs/MINIMAL_UX_VALIDATION.md for the exact upgrade and role/browser checks.

Schema change: federation.matchday.event_timezone. Calendar pre-migration explicitly
backfills historical days to UTC without changing slot instants. New days capture the
creator's timezone. Existing draft days require timezone review before generating slots.
Scheduled days remain UTC unless a separately reviewed historical data migration is approved.
The visual planner and court queue use event-local display; generic Odoo datetime widgets
retain user-profile display. Constraints convert local input on the server under existing
schedule access, mutability and revision checks. No new public route or sudo mutation is added.

Dry-run evidence: source-policy tests and Python/XML/JavaScript syntax checks executed.
Database upgrade, ORM/HTTP tests, browser/mobile sessions and novice acceptance have NOT
been executed in this environment. This candidate is not production-qualified by these checks.

Rollback: restore the pre-upgrade database and filestore together with the previous code.
Do not roll back code alone after new event-local constraints or slot generation have occurred.
Retain backups until event timezone review and staging acceptance are complete.

## Complete minimal UX revision: upgrade and qualification review

Candidate base: a6411d877a37986920c4c8b0337e10c794dc646f.
See docs/COMPLETE_UX_VALIDATION.md for the seven-point scope, module upgrade list,
local checks, runtime groups, browser matrix, historical-timezone review and rollback.
The calendar migration marks historical event timezone evidence as unreviewed without
moving stored slot instants. Calendar planners confirm evidence through an audited,
write-authorised, row-locked command. Match timezone fields are nonstored projections
of nonpersonal event metadata, not a new source of truth or a new access grant.
Task/list context is a presentation filter intersected with existing ownership domains.
No task system, readiness model, approval state or publication bypass is introduced.
Local source/policy and mocked-service checks were executed. Odoo database upgrade,
ORM/HTTP/browser runtime and novice acceptance remain unexecuted in this environment.
Rollback requires the pre-upgrade database and filestore together with previous code.

## Gameday roster and per-match participation: upgrade review

Candidate base: 4626ba2401ec05ca67ebac0e9f09b4d53d75338a.
Behaviour: one roster per team gameday, shared by all its matches; no starters or
substitutes declared in advance; at each match the coach crosses out the gameday
players who do not play. Crossing out is match-specific and never edits the roster.

Schema: federation.rule.set.gameday_roster_max_size and match_player_max_size
(integers, default 0 = unchanged behaviour) and federation.match.sheet.line.crossed_out
(boolean, default false). Odoo adds the columns on upgrade; no data migration runs and
existing sheets keep every listed player as playing. Legacy starter/substitute values
stay stored and synchronized, but new gameday rosters do not set them.

Upgrade sports_federation_rules, sports_federation_rosters, sports_federation_portal and
sports_federation_live_workspace, then set both limits (for example 14 and 12) on the
competition rule sets that use them. With limits at 0 nothing new is enforced.

New portal route: POST /my/match-sheets/<id>/participation (CSRF, ownership domain via
the portal privilege boundary). No new sudo statement is introduced. Sheet locking now
requires the per-match limit to be respected.

Dry-run evidence: Python/XML syntax checks, template xpath simulation against the
source templates, and repository static checks executed. Odoo upgrade, ORM/HTTP and
browser tests (sf_gameday_participation and existing roster tests) were NOT executed in
this environment and must pass on staging before release.

Rollback: restore the pre-upgrade database and filestore with the previous code. A
code-only rollback leaves unused columns and loses the record of crossed-out players.

## Competition lifecycle completion: upgrade review

Scope: one definition of a finished match, one standings/progression engine,
knockout placeholders/ties/corrections, guided competition finish, forfeit/bye
points and dated suspensions, and the gameday-roster follow-ups.

Data changes:
- result_control 19.0.1.6.0 post-migrate: matches with an approved result that
  are not done or cancelled are set to done. Only the state column changes;
  scores, audit and publication data are untouched. Safe to repeat.
- format 19.0.6.1.0 post-migrate: every round-robin stage with participants gets
  its linked league table (one savepoint per stage; failures are logged, not
  fatal). Review the upgrade log for "No league table created for stage".
- discipline: daily cron "Discipline: Start and End Suspensions" activates
  suspensions on their start date and expires them after their end date.

Behaviour changes to verify on staging: approving a result completes the match;
contesting/correcting reopens it and withdraws an unplayed follow-up knockout
match (audited as follow_up_match_withdrawn); knockout fixtures with unknown
teams can be scheduled and are filled without republication; competitions move
through Open/In Progress/Closed via the guarded transition and close only
without blockers; forfeits and byes use rule-set points.

Dry-run evidence: Python/XML syntax checks and repository static checks
(privileged mutation, addon integrity, route ownership, ACL, workflow command,
sudo guard) executed on the patched tree. Odoo upgrade, ORM/HTTP/browser tests
and an end-to-end competition run were NOT executed in this environment and
must pass on staging before release.

Rollback: restore the pre-upgrade database and filestore with the previous
code. Code-only rollback leaves done matches, linked tables and suspension
states that the previous code does not expect.

## Stage builder, match board and format reuse: upgrade review

Scope: the stage builder for custom formats, the season match board as the
planner's Schedule step, saved format templates, and reusing formats and game
days when a competition is copied to a new season.

Data changes (no migration scripts; upgrading installs the new columns and access rules):
- format 19.0.6.5.0: `federation.tournament.format_source_structure_id`
  (nullable). Templates accept the `custom` format type. Competition designers
  get create/write on stage progressions and create/write on format templates.
- setup_flow 19.0.4.11.0 and live_workspace 19.0.1.6.0: no stored fields. New
  client actions `federation_stage_builder` and `federation_season_board`, plus
  a "Match board" button on the competition.

Behaviour changes to verify on staging:
- The planner's Schedule step opens the match board. *Plan Competition* stays
  available as *Auto-plan the rest*.
- On the board, moves between game days update allocations and working
  schedules. They are logged as `board_move` and refused when the validator
  reports a new error. Published days stay locked.
- Custom formats open in the stage builder, and *Generate all matches* freezes
  them.
- *Copy competition setup* moves game days by whole weeks and keeps their
  divisions. Before this change, a game day limited to divisions could not be
  copied.

Dry-run evidence: Python/XML syntax checks, JavaScript syntax checks, the
board helper smoke test and repository static checks (access CSV, always-invisible
fields, privileged mutation boundaries, dependency drift, competition
workflow and usability checks) were executed on the patched tree. Odoo upgrade, ORM tests
(`sf_competition_formats`, `sf_live_workspace`) and browser checks of both
client actions were NOT executed in this environment and must pass on staging
before release.

Rollback: restore the previous code and upgrade the three modules. The
nullable field and the template rows can stay. Templates saved with the
`custom` type must be archived before a code-only rollback.

## Custom format setup and team spread: upgrade review

Scope: custom formats in the guided setup, safe re-generation of prepared
stages, and spreading each team's matches over its game days within the rest
limit.

Data changes: none. Upgrade sports_federation_format,
sports_federation_scheduling and sports_federation_setup_flow for the new code
and assets.

Behaviour changes to verify on staging:
- *Teams & format* keeps a draft custom format and opens the stage builder.
  The planner's format action for custom drafts opens the stage builder for
  every user.
- Generating a format whose stages were already prepared keeps their matches.
  Before this change it failed with "Fixtures with operational matches cannot
  be deleted". Different teams give a clear "make a new version" message.
- Plan Competition reports unfinished custom stages as a blocking issue.
- Plan Competition keeps each team within the rest limit per game day when the
  game days allow it. Rest warnings state the team's match total and its
  capacity.

Dry-run evidence: Python/XML/JavaScript syntax checks, the dependency-free
distributor tests (including team-spread cases) and repository static checks
were executed on the patched tree. Odoo upgrade and ORM tests
(`sf_competition_formats`) were NOT executed in this environment and must pass
on staging before release.

Rollback: restore the previous code. No data needs to be reverted.

## End-to-end release check: lifecycle lane and walkthrough

The release baseline now requires a `lifecycle` lane. It runs the scenarios
contracted in `ci/release_confidence/competition_lifecycle.json` from
`sports_federation_app/tests/test_competition_lifecycle_e2e.py` and fails when the
file is missing, uses shortcuts (elevation, policy bypass, direct state writes,
skips), or any required scenario did not run. Until the scenarios are written the
baseline is red by design.

`scripts/ci/run_end_to_end_release.sh` runs the lanes (and the migration rehearsal
when an approved backup is supplied), starts a disposable walkthrough server on the
host loopback, and combines automated, walkthrough and novice-session evidence into
`end-to-end-summary.json`. See docs/END_TO_END_RELEASE.md and
docs/END_TO_END_RELEASE_AGENT.md.

View files in accounting, calendar, duty coverage, member services, rosters,
schedule approval and setup flow only gained XML rationale comments for
always-invisible fields; no view behaviour changed and no module upgrade is needed
for them.

Dry-run evidence: shell syntax, the new checker unit tests and the repository
static checks executed. The Odoo lanes, walkthrough server and seed script were NOT
executed in this environment.

Rollback: revert the commit. No data or schema change is involved.

#### Retired engine migration decision gate

The invariant contract now records two blocking facts from every restored database:
`retired_competition_engine_not_upgradeable` and
`retired_engine_legacy_tables_remaining`. Both must be zero before the normal
upgrade lane is considered clean. A non-zero value is not auto-repaired: stop,
retain the restored backup unchanged, inventory the legacy module-owned records,
and attach the reviewed preserve/map/drop decision to the release evidence before
running a data-specific migration. This deliberately prevents an uninstall or SQL
state change from masquerading as a data-preserving migration.
