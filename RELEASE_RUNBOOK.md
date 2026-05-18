# Release Runbook

Last updated: 2026-04-30
Owner: Federation Platform Team
Last reviewed: 2026-04-30
Review cadence: Every release
Release train: 2026.05

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
portal, and reporting hotspots documented in `PERFORMANCE_BASELINES.md`.

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

If you need to restrict the release to a subset of installed modules:

```bash
./scripts/upgrade_sports_federation.sh --db odoo --modules sports_federation_reporting,sports_federation_portal --dry-run
```

## Backups

The upgrade script performs backups by default. It stores:

- `modules.txt` with the exact upgraded module list
- `<db>_<timestamp>.dump` as a PostgreSQL custom-format dump
- `filestore_<db>_<timestamp>.tar.gz` when a filestore exists under
  `./odoo-data/filestore/<db>`

Do not use `--skip-backup` for production releases.

Run the periodic restore drill against one of these backup directories before
or during each release train using `RESTORE_VERIFICATION_CHECKLIST.md` as the
operator checklist:

```bash
bash addons/ci/restore_backup_drill.sh --backup-dir 2026-04-15_191410 --target-db odoo_restore_drill --dry-run
```

## Production Upgrade

Run the upgrade and let the script restart the live Odoo service afterward so
Python changes are loaded by the running web container:

```bash
./scripts/upgrade_sports_federation.sh --db odoo --yes
```

The script runs:

- `odoo -c /etc/odoo/odoo.conf -d <db> -u <module_csv> --stop-after-init`
- `docker compose restart odoo`

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
changes. Reference `COMPATIBILITY_INVENTORY.md` for route retirement dates.

### Release 2026.05

**DB migrations**: None.

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