# Troubleshooting Guide

Last updated: 2026-05-18
Owner: Federation Platform Team
Review cadence: Every release train

This guide documents known issues, their root causes, and the recommended
recovery steps. Always check this file before escalating to a developer.

---

## Quick Diagnostic Checklist

Before diving into a specific symptom, run these checks first:

```bash
# 1. All containers running?
docker compose ps

# 2. Any Python errors in the Odoo log?
docker compose logs odoo 2>&1 | grep -i "error\|traceback\|exception" | tail -20

# 3. PostgreSQL accepting connections?
docker compose exec db pg_isready -U odoo

# 4. Scheduled actions healthy?
# Check in the back office: Settings → Technical → Automation → Scheduled Actions
# Look for any action where "Last Execution" shows a failure icon.
```

---

## Symptom Index

| Symptom | Section |
|---|---|
| Match form crashes with `UndefinedColumn` | [§1](#1-match-form-crashes-with-undefinedcolumn) |
| Standings not recomputing after result approval | [§2](#2-standings-not-recomputing-after-result-approval) |
| Notifications not sending | [§3](#3-notifications-not-sending) |
| Import wizard dry-run always fails | [§4](#4-import-wizard-dry-run-always-fails) |
| Rate limit buckets never cleared | [§5](#5-rate-limit-buckets-never-cleared) |
| CI container fails to start PostgreSQL | [§6](#6-ci-container-fails-to-start-postgresql) |
| Portal page shows 403 / `AccessError` | [§7](#7-portal-page-shows-403--accesserror) |
| Public JSON feed returns `500` | [§8](#8-public-json-feed-returns-500) |
| Player shows `is_eligible = False` after license activation | [§9](#9-player-shows-is_eligible--false-after-license-activation) |
| Finance events not exporting to partner | [§10](#10-finance-events-not-exporting-to-partner) |
| Reporting schedule stuck in `running` | [§11](#11-reporting-schedule-stuck-in-running) |
| Roster assignment_ready False with no clear reason | [§12](#12-roster-assignment_ready-false-with-no-clear-reason) |

---

## 1. Match Form Crashes with `UndefinedColumn`

**Symptom**: Opening or saving a match record raises a `ProgrammingError:
column "xyz" of relation "federation_match" does not exist`.

**Cause**: A `store=True` computed field was added to the match model in a
new release but the database column was never created because the module was
not upgraded after the code change.

**Fix**:

```bash
# Upgrade the affected module(s) to create the missing column
docker compose exec odoo odoo \
  -c /etc/odoo/odoo.conf \
  -d odoo \
  -u sports_federation_tournament,sports_federation_result_control \
  --stop-after-init
docker compose restart odoo
```

**Prevention**: always run `upgrade_sports_federation.sh` (or `-u <module>`)
after pulling code that adds or changes stored computed fields. A missing
column never appears in `--test-enable` output but will crash the live form.

---

## 2. Standings Not Recomputing After Result Approval

**Symptom**: A result is approved (`result_state = approved`,
`include_in_official_standings = True`) but the standings table is unchanged.

**Cause A**: The standings record for the affected tournament/stage/group is
in `frozen` state. Frozen standings are never recomputed automatically.

**Fix A**:

1. Open **Federation → Standings** and locate the relevant standings record.
2. Verify `state = frozen`.
3. Click **Unfreeze** (requires Federation Manager group).
4. Click **Recompute**.
5. Verify the standings are correct, then re-freeze.

**Cause B**: The `@api.depends` chain on the standings recompute trigger is
missing the field that changed.

**Fix B**:

1. Check which field on `federation.match` changed (e.g. `home_score`).
2. Verify it appears in the `@api.depends` decorator on
   `_trigger_recompute` or the equivalent compute method in
   `sports_federation_standings/models/federation_standings.py`.
3. If missing, add the field to the depends list and upgrade the module.

**Cause C**: The automatic trigger code path was skipped because the result
was approved via a raw ORM write (`record.write({"result_state": "approved"})`)
instead of the `action_approve_result()` method. This can happen during
bulk imports.

**Fix C**: Trigger a manual recompute from the standings form.

---

## 3. Notifications Not Sending

**Symptom**: Expected emails (result approval, roster confirmation, referee
assignment) are not delivered.

**Cause A**: SMTP server is not configured or is misconfigured.

**Fix A**:
1. Open **Settings → Technical → Email → Outgoing Mail Servers**.
2. Verify the server entry exists and is active.
3. Click **Test Connection**. If it fails, correct the host, port, and
   credentials.
4. Check `docker compose logs odoo | grep -i smtp` for connection errors.

**Cause B**: `sports_federation_notifications` module is not installed.

**Fix B**:
```bash
docker compose exec odoo odoo -c /etc/odoo/odoo.conf -d odoo \
  -i sports_federation_notifications --stop-after-init
```

**Cause C**: The notification dispatcher scheduled action is disabled.

**Fix C**:
1. Open **Settings → Technical → Automation → Scheduled Actions**.
2. Find the federation notification scan action.
3. Click **Run Manually** to test, then re-enable if it was disabled.

**Cause D**: The email ends up in the mail queue but is not sent because the
queue runner is not processing.

**Fix D**:
```bash
# Force the mail queue to flush
docker compose exec odoo odoo \
  -c /etc/odoo/odoo.conf -d odoo \
  --load=base,mail --stop-after-init \
  -e "self.env['mail.mail'].process_email_queue()"
```

---

## 4. Import Wizard Dry-Run Always Fails

**Symptom**: Running a dry-run in **Federation → Import Tools → Import Wizard**
raises a duplicate key or unique constraint error on every attempt, even for
a fresh payload.

**Cause**: Stale rows in the staging table (`federation.import.staged.delivery`
or the module-specific staging model) from a previous failed import still
occupy the unique key slot.

**Fix**:
1. Open **Federation → Import Tools → Inbound Deliveries**.
2. Filter for `state = staged` deliveries from the failing batch.
3. Archive or delete the stale staged rows.

Alternatively, trigger the cleanup scheduled action:
1. Open **Settings → Technical → Automation → Scheduled Actions**.
2. Run **Federation: GC Staged Deliveries** manually.

**Prevention**: the GC scheduled action runs daily. If it is disabled (see §5),
stale rows accumulate quickly.

---

## 5. Rate Limit Buckets Never Cleared

**Symptom**: The `federation.request.rate.limit` table grows unboundedly.
Public API calls succeed less frequently than expected even from legitimate
callers whose rate-limit window has expired.

**Cause**: The `Federation: GC Rate Limit Buckets` scheduled action is
disabled.

**Fix**:
1. Open **Settings → Technical → Automation → Scheduled Actions**.
2. Find **Federation: GC Rate Limit Buckets**.
3. Set **Active** = True and **Interval** to 1 Hour (the default).
4. Click **Run Manually** to clear the backlog immediately.

**Verify** bucket cleanup is working:
```bash
docker compose exec -T db psql -U odoo -d odoo \
  -c "SELECT COUNT(*) FROM federation_request_rate_limit;"
# Should decrease after the GC action runs
```

---

## 6. CI Container Fails to Start PostgreSQL

**Symptom**: Running `bash addons/ci/run_tests.sh` fails immediately with
a PostgreSQL startup error: `address already in use` or `port 5432 already
in use`.

**Cause**: The development Docker Compose stack is already running and its
`db` service occupies port 5432 (if the CI uses host networking) or the same
Docker network.

**Fix**:

```bash
# Option A: stop the dev stack before running CI
docker compose down
bash addons/ci/run_tests.sh --suite competition_core

# Option B: use a different network (check ci/run_tests.sh --help for options)
bash addons/ci/run_tests.sh --suite competition_core --network ci_net
```

After CI completes, restart the dev stack:
```bash
docker compose up -d
```

---

## 7. Portal Page Shows 403 / `AccessError`

**Symptom**: A portal user navigates to a federation portal page and receives
a 403 error or an `AccessError` in the logs.

**Cause A**: The user's `res.users` record is not linked to a
`federation.club.representative` record for the club that owns the resource.

**Fix A**:
1. Open **Federation → Portal → Club Representatives**.
2. Verify a record exists for the user and the correct club.
3. If missing, create it (see [WORKFLOW_CLUB_ONBOARDING.md](
   _workflows/WORKFLOW_CLUB_ONBOARDING.md)).

**Cause B**: The portal record rule for the affected model uses the wrong
domain expression (developer error introduced by a recent change).

**Fix B**:
1. Check **Settings → Technical → Security → Record Rules** for rules on the
   affected model.
2. Verify the domain matches the expected club-scoping pattern
   (`club_id.representative_ids.user_id`, etc.).

---

## 8. Public JSON Feed Returns `500`

**Symptom**: `GET /competitions/api/json` returns HTTP 500 instead of JSON.

**Cause A**: A new required computed field on `federation.tournament` throws
an exception when the tournament has incomplete data.

**Fix A**: Check the Odoo log for the traceback:
```bash
docker compose logs odoo 2>&1 | grep -A 30 "competitions/api/json"
```
Fix the underlying data or guard the computed field with a `try/except`.

**Cause B**: The rate-limit table has a corrupt bucket (e.g. `hit_count < 0`).

**Fix B**:
```bash
docker compose exec -T db psql -U odoo -d odoo \
  -c "DELETE FROM federation_request_rate_limit WHERE hit_count < 0;"
```

---

## 9. Player Shows `is_eligible = False` After License Activation

**Symptom**: A license is set to `state = active` but the player's
`is_eligible` computed field remains `False`.

**Cause A**: Odoo's compute cache is stale. This can happen after a direct
database write (e.g. during a migration or import) that bypasses the ORM.

**Fix A**:
```bash
# Force recompute of is_eligible for all players
docker compose exec odoo odoo shell -c /etc/odoo/odoo.conf -d odoo <<'EOF'
env['federation.player'].search([])._compute_is_eligible()
env.cr.commit()
EOF
```

**Cause B**: The player also has an active suspension sanction in
`sports_federation_discipline`. Suspension overrides the license-active state.

**Fix B**: Check **Federation → Discipline → Sanctions** for an active
suspension for the player. If the suspension is resolved, run the
reinstatement action (see [WORKFLOW_PLAYER_LICENSE.md](
_workflows/WORKFLOW_PLAYER_LICENSE.md)).

---

## 10. Finance Events Not Exporting to Partner

**Symptom**: A partner calls `GET /integration/v1/finance-events` and
receives an empty list even though events exist in the system.

**Cause A**: Events are still in `draft` state. The integration export endpoint
returns only `confirmed` or `exported` events.

**Fix A**: Federation finance staff must confirm the pending events:
**Federation → Finance → Finance Events → filter `state = draft` → Confirm**.

**Cause B**: The partner's `X-Federation-Partner-Code` header does not match
the code stored on the `federation.integration.partner` record.

**Fix B**: Verify the partner code with the administrator. The export route
returns `access_denied` (not an empty list) for authentication failures.
If the response is an empty list with status 200, the authentication succeeded
but no confirmed events match the filter.

---

## 11. Reporting Schedule Stuck in `running`

**Symptom**: A report schedule shows `state = running` indefinitely; no report
is generated and no error is visible.

**Cause**: The Odoo worker that started the report generation crashed (e.g.
OOM kill, container restart) mid-execution, leaving the state flag uncleared.

**Fix**:
1. Open **Federation → Reporting → Report Schedules**.
2. Set the stuck schedule back to `draft` or `ready` via the developer mode
   form editor, or use:

```bash
docker compose exec odoo odoo shell -c /etc/odoo/odoo.conf -d odoo <<'EOF'
env['federation.report.schedule'].search([('state','=','running')])\
  .write({'state': 'ready'})
env.cr.commit()
EOF
```

3. Trigger the schedule manually to confirm it completes.

**Prevention**: monitor the **Reporting → Report Schedules** list after every
container restart.

---

## 12. Roster `assignment_ready` False with No Clear Reason

**Symptom**: A roster line shows `assignment_ready = False` but the
`readiness_feedback` field is empty or unhelpful.

**Cause**: The eligibility service (`federation.eligibility.service`) failed
silently or the `readiness_feedback` compute method has a gap for a new
blocking condition that was added without a corresponding feedback string.

**Fix**:
1. Open the roster line form and check the **Readiness** tab.
2. If feedback is empty, check the player's license state, suspension status,
   and team/season scope manually.
3. If this is a new condition that lacks feedback, add the missing feedback
   string in `sports_federation_rosters/models/roster_line.py` →
   `_compute_readiness_feedback`.

---

## Getting Further Help

If none of the above applies:

1. Capture the full traceback from the Odoo log:
   ```bash
   docker compose logs odoo 2>&1 | grep -A 50 "Traceback"
   ```
2. Note the affected model, user, and action (what was clicked or called).
3. Check `CONTRIBUTING.md` for how to run focused module tests that may
   reproduce the issue.
4. Open a bug report in the project tracker with the log excerpt, module
   version (`__manifest__.py` `version` field), and reproduction steps.
