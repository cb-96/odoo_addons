# Implementation and validation: points 1–3

## Status and scope

Point 3 scope 1–8 is implemented in the additive `sports_federation_duty_coverage` addon. This is a source delivery, not a deployment or production approval. The existing assignment, club-duty, match, fixture and publication records remain the source of truth. No competing assignment database is introduced.

The uploaded source is the patch baseline. Earlier point 1 and point 2 packages are not reapplied or overwritten. The application manifest receives one dependency, and the owner registry receives one module entry. Use the merge-safe installer if these two files have changed locally.

### Point 3 implementation map

1. **Coverage board:** one row per match, including zero-assignment matches; edition and match-day entry points; role requirements, owner, effective kickoff, deadlines, blockers and separate counts.
2. **Resolve workflow:** one preview/apply wizard for individual assignment, club nomination requests, nomination linkage, reopening and replacement. Applies canonical records and returns to the same match coverage form.
3. **Individual workspace:** current/history filters, paginated responsive cards, response form, reasons, acceptance, eligibility, presence and completion. Existing referee-assignment URLs redirect to the new workspace. Old POST forms do not mutate records.
4. **Club workflow:** existing club portal remains the nomination surface. Coordinator linkage creates a draft assignment, never individual acceptance. Explicit player-to-official identity replaces name matching. Repeated linkage does not create another assignment.
5. **Escalation:** configurable nomination/response lead hours, dedicated coordinator activities, idempotent signatures, hourly cron and reconciliation on coverage commands. Superseded publications and completed/cancelled matches lose obsolete coverage activities. Missing attendance at kickoff is also escalated. Missing owners remain visible rather than receiving a fabricated owner.
6. **Presence/completion:** individual acknowledgement and schedule signature are distinct from manager-recorded attendance. Completion requires current acceptance, eligibility and presence. Evidence imports are rejected. Legacy confirmations are not automatically treated as acceptance.
7. **Replacement:** match/profile locks, stale-preview signature, savepoint, reason, preserved cancelled predecessor, linked successor, club-duty rebinding, unchanged unrelated assignments and repeat-submit protection. Replacement starts unaccepted. A completed assignment cannot be ordinarily replaced or cancelled.
8. **Tests:** 12 executable pure-policy tests; 21 Odoo ORM tests; two browser tests. Odoo tests are also tagged `sf_release_confidence`. Database concurrency, complete role journeys and real usability observations remain release qualification gates, not inferred passes.

## Checks actually executed here

- PASS: 12 standalone policy tests, rerun after changes.
- PASS: changed Python syntax, XML parsing and source XML reference checks.
- PASS: changed-code Flake8 with 88-character lines, E203/W503 excluded; Black formatting applied.
- PASS: application entry-point registry, module owners, ACL CSV integrity, literal HTTP route ownership and Odoo test discovery checks.
- OPEN: full addon-integrity and dependency-drift repository scans exceeded the execution time limit. No pass is claimed.
- OPEN: Odoo registry/install/upgrade, ORM tests, browser tests, PostgreSQL concurrency and all deployment qualification. Odoo and Docker were unavailable here.

## Apply safely

Commit or otherwise preserve local changes first. Do not use `git apply --reject` as an automatic merge strategy.

```bash
# Strict patch route, only when the source baseline matches:
git apply --check duty_coverage.patch
git apply duty_coverage.patch

# Alternative: extract the ZIP, then merge only this delivery:
python apply_duty_coverage.py --repo /path/to/repository --check
python apply_duty_coverage.py --repo /path/to/repository
```

The installer copies only new addon/test/document files. Existing identical files are accepted; differing files stop preflight before writes. It appends the dependency using the current manifest AST and adds the owner entry only if missing. It never replaces the existing app manifest or portal addon wholesale. Review the resulting diff and commit it.

The supported application entry point now depends on the new addon. On an existing database, explicitly install the new addon while updating the app. Merely restarting does not create its fields or views.

```bash
# Set these to your real Odoo 19 executable/configuration and disposable database.
: "${ODOO_BIN:?}" "${ODOO_ADDONS_PATH:?}" "${ODOO_DATABASE:?}"
"$ODOO_BIN" --database "$ODOO_DATABASE" --addons-path "$ODOO_ADDONS_PATH"   --init sports_federation_duty_coverage --update sports_federation_app   --stop-after-init --log-level=test
```

Do not run destructive test/restore commands against production. Use approved sanitized backups, disabled outbound delivery and private evidence storage.

## Upgrade review before testing

- The new fields default to **no acceptance**, **no presence** and **playing commitments not checked**. Do not backfill these from `state='confirmed'` or a name match.
- Link each official login explicitly. Link playing identity explicitly where applicable, then have a manager mark playing commitments checked. External non-playing officials may have no player link, but still need this review.
- Record availability windows. Missing availability now means not checked, not automatically available.
- Confirm the effective live slot, duration and court. Missing or blocked slots prevent eligibility.
- Configure role counts where the existing total referee count is insufficient. The fallback maps the existing total to head, assistant 1, assistant 2, fourth, table in that order. Counts above those five roles require explicit configuration. Club duties establish required slots without double-counting their linked assignments.
- Assign an active federation manager as coverage coordinator. The current security policy deliberately reserves resolution and attendance to federation managers; it does not silently grant portal users coordinator privileges.
- Review historical confirmed/completed records separately. History remains visible, but no individual acknowledgement is invented.
- The old unconditional match/referee/role uniqueness constraint is replaced by an active-only unique index so a cancelled official can later return through a new assignment while predecessor records remain intact. Verify this change in the restored database. Rollback after installation requires the rehearsed database/filestore/code restore, not simply deleting the addon directory.

## Common validation sequence

Run on the exact candidate commit, first on a fresh database, then on a restored approved sanitized database. Preserve logs, selected test names, test counts, failures, screenshots, invariants and environment/image versions. A command returning zero with zero selected tests is not a pass.

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_duty_coverage_policy.py -v
python ci/check_application_entrypoint.py
python ci/check_module_owners.py
python ci/check_access_csv_integrity.py
python ci/check_http_route_ownership.py
python ci/check_test_discovery.py
python ci/check_addon_integrity.py
python ci/check_module_dependency_drift.py --strict
bash ci/run_repo_lint.sh --strict

# Fresh database: install the supported app, then execute the new ORM tests.
"$ODOO_BIN" --database "$ODOO_DATABASE" --addons-path "$ODOO_ADDONS_PATH"   --init sports_federation_app --test-enable --test-tags sf_duty_coverage   --stop-after-init --log-level=test

# Browser run on a separate disposable database with Chromium available:
"$ODOO_BIN" --database "$ODOO_BROWSER_DATABASE" --addons-path "$ODOO_ADDONS_PATH"   --init sports_federation_app --test-enable --test-tags sf_duty_coverage_browser   --stop-after-init --log-level=test
```

Include your existing configuration file and database credentials through the approved environment. Browser tests require an HTTP server and supported browser runtime. Inspect logs for the actual 21 ORM and two browser test methods, not just the tags.

## Point 1: release-confidence items still open

### Restored-database qualification

1. Capture candidate commit, image digests, backup approval, DB/filestore hashes and migration baseline invariants.
2. Restore the sanitized backup into an isolated environment. Disable real SMTP, webhooks, payments and unrelated scheduled jobs.
3. Install/upgrade the exact candidate and run registry checks. Inspect every error/warning; classify rather than suppress it.
4. Capture post-upgrade invariants: logical fixtures, publications, assignments, club-duty links, results, standings, registrations, audit events and filestore attachments. Explain every permitted delta.
5. Run upgrade again. No duplicate records, notifications, activities or migration changes should appear.
6. Run full CI and release-focus/browser selections. Preserve selected test counts and failure classification.

**Pass evidence:** successful restore and upgrade logs, invariant comparison, second-run idempotency, exact test selection and reviewed exceptions. Demo-data success alone is insufficient.

### Concurrency and stale operations

Use two independent PostgreSQL transactions or two authenticated HTTP sessions, not two sequential calls in one test transaction.

- Simultaneously approve/reject the same registration or result. Exactly one permitted terminal transition; no duplicate effects.
- Publish/replace the same schedule from two stale previews. The losing operation rejects or retries safely; one current live publication.
- Replace the same official from two previews. One successor, one cancellation, no split club-duty links.
- Accept while a replacement is committed. Either acceptance precedes the cancellation, or the stale response is rejected; the successor never inherits acceptance.
- Assign one official to overlapping matches from separate sessions. Both matches must not remain ready. Check the refreshed board, not just successful create responses.
- Change a physical slot while a response form is open. Old signature is rejected; refreshed page shows the effective slot.

**Pass evidence:** both transaction traces, final canonical rows, unique-index checks, refreshed readiness and zero duplicate external side effects. Serialization retries must be bounded and visible.

### Notification recovery

Inject failures only in the isolated test environment: unavailable transport, timeout before delivery, retry after transport recovery, duplicate retry and a failure after the external system has acknowledged delivery.

Verify durable retry state, idempotency keys, no duplicate logical notifications, visible unresolved failures, bounded retry behaviour and retained audit evidence. Do not equate a queued mail/activity with delivered mail. Include coverage escalation cleanup, replacement notices and existing publication/result notifications.

### Rollback rehearsal

Declare an actual rollback owner and objective trigger before the run. Rehearse restoring pre-upgrade database, matching filestore and prior code/image together. Verify logins, public schedules, results, portal scopes and notification state afterwards. Record measured recovery duration against an owner-approved target. A written rollback plan without a restore rehearsal remains open.

### Role and usability qualification

Complete every role journey on the restored candidate, including denied actions and expired scopes. Observe a newly trained operator and an actual club representative without developer guidance. Record task completion, wrong turns, help requests and time. Set acceptance targets before observing; do not invent a universal time limit afterwards.

If point 1 automation is installed, use its existing commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_release_confidence.py -v
python ci/release_confidence.py plan
python ci/release_confidence.py run   --backup-dir /approved/sanitized-backup   --evidence-dir /private/release-evidence/candidate-run   --rollback-owner 'ACTUAL OWNER'   --rollback-trigger 'APPROVED OBJECTIVE TRIGGER'   --approved-sanitized-backup
python ci/release_confidence.py verify --evidence-dir /private/release-evidence/candidate-run
```

If those files are absent, first merge the earlier point 1 package. This point 3 delivery does not claim to recreate or run that automation.

## Point 2: role-journey validation still open

Run `sf_role_journeys` on the integrated candidate and preserve actual test selection. Run helper tests only if the earlier point 2 helper files are present.

For each case below, test the normal route, a stale browser tab, a denied user and the return path after submission:

- **Club representative:** My Work → club/team → registration/roster/shared game-day lineup → submit → correct queue and status. No duplicate lineup task per team/day. A foreign club ID or expired representative scope is rejected.
- **Competition administrator:** edition overview → readiness blocker → responsible workflow → same edition overview. Verify blockers are sourced from current records, not stale task rows.
- **Registration manager:** pending queue → approve/reject → status and notifications → queue. Repeat/stale submissions do not produce duplicate participants or effects.
- **Designer/planner:** structure → calendar → schedule preview → review submission → publication handoff. Context remains the same edition/match day; frozen or superseded records reject invalid changes.
- **Schedule approver:** current review → decision → correct planner/administrator return path. Stale revision and missing role are rejected.
- **Match-day operator:** current publication → operational deviation/lineup/result → correct match/day return. Public schedule stays distinct from operational changes.
- **Results officer:** submitted result → review/correction → standings/public result → same queue. Finalization and retry are idempotent.
- **Official:** existing My Work link → new individual assignment workspace → response → same assignment/current or history filter. Only the assigned login can respond.

### Cross-cutting point 2 gates

- Empty workspaces say there are no items, not that the whole competition is ready.
- Every badge has an explicit meaning. Missing data is not checked; a role denial is not a missing record; assigned is not accepted.
- Every displayed blocker links to a permitted resolution surface or clearly identifies the responsible role.
- Reconcile twice: task count/source keys do not multiply. Resolve a source blocker: its obsolete task disappears or is explicitly completed.
- Club-scoped duty tasks remain club-scoped. The new coordinator board is not exposed to a club representative.
- At 360–390 px widths, forms/cards remain usable, labels are visible and no essential control is offscreen. Check keyboard focus and error announcements.
- Notifications and existing links land on the new workspace without silently applying an old form response.

**Pass evidence:** role-account matrix, screenshots/video, selected test names, denied-action logs, source/task reconciliation and observed usability notes. Screenshots of menus alone do not close these gates.

## Point 3: scope-by-scope acceptance scenarios

### Coverage board

Create one current match with no assignments, one with a draft head, one accepted but ineligible, one accepted/eligible, one explicitly requiring zero officials and one without checked requirements. Expect respectively uncovered, needs action, needs action, accepted and eligible, not required, not checked. Verify all rows are present and no count is used as a substitute for another fact.

Set explicit head/table requirements. A table official cannot fill the head requirement. Two roles assigned to one individual must not produce ready coverage. Compare board counts to canonical records, including cancelled predecessors and club-duty links.

### Resolve and club nomination

From the edition or match day, open the board and resolve a missing duty. Check preview, apply and return context. Repeat the same submit: no duplicate assignment or club request. Modify the match, slot or assignment from another session: the stale wizard must reject.

Request a club table official, nominate a player from that club, then link as coordinator. The linked assignment is draft/unaccepted. Repeat linkage: one assignment. A same-name player from another club must not reuse an unrelated official profile. Wrong-club nomination, expired representative scope and direct portal state writes must fail.

### Individual responses and eligibility

Check the current/history filters and pagination with more than 40 owned assignments. Foreign assignment GET/POST must return hidden/denied without exposing its details. Missing/invalid CSRF and GET requests to response endpoints must not mutate records.

Accept as the assigned login: timestamp, actor and schedule signature appear; presence remains false. Accept twice: same acknowledgement. Decline without reason: error; decline with reason: cancelled record retained. A manager must not impersonate acceptance. An accepted official needing replacement uses the coordinator path.

Test inactive profile, expired certification on match date, no availability, partial availability, overlapping officiating, linked playing-team conflict, unreviewed playing commitments, missing/blocked slot and superseded publication. Each must be visible and prevent ready eligibility. Move court/time/duration: old acknowledgement becomes stale and the old response form is rejected.

### Escalation and attendance

Set deadlines relative to an upcoming test kickoff. Before deadline: no overdue activity. After nomination/response deadline: one dedicated activity for the configured coordinator. Run cron twice: still one. Change blocker/owner: activity is reconciled. Resolve acceptance/eligibility: activity disappears before kickoff. At kickoff, missing required presence generates an attendance escalation. Record presence: it disappears. Supersede/cancel/complete the match: obsolete coverage activities disappear. No coordinator: visible blocker, no invented owner.

Record presence as manager only. Completion before presence must fail. Presence does not change individual acceptance. Complete after current acceptance, eligibility and presence: done timestamp appears. Repeated completion is harmless. Portal/elevated-portal attendance writes, raw evidence imports and deletion of history must fail.

### Replacement and race safety

Replace an accepted official with a different eligible official and a reason. The old row is cancelled, the successor links to it, unrelated assignments remain untouched, linked club duty points to the successor and the successor is unaccepted/not present. An invalid candidate or a mid-operation error leaves the original unchanged. Repeat the wizard: one successor. Reject wrong-match records, blank reasons, same-person replacements, completed predecessors and a second replacement of an already replaced predecessor.

For club duties, replacement must use an explicitly linked player from the responsible club, otherwise cancel/reopen nomination. Verify the predecessor remains in history. Rehearse a later return of the original official through a new record and verify the active-only uniqueness index.

### Integrated readiness and performance

Verify match-day readiness still blocks when individual acceptance/eligibility is outstanding, even if legacy confirmed counts meet the total. Presence is a separate operational fact. Existing assignment-count reports remain assignment-count reports, not readiness reports.

Measure board/filter load, profile conflict scans, task reconciliation and hourly escalation on representative restored volumes. The nonstored board state filter currently projects readable matches in Python; do not assume it scales without measurement. Capture query counts, duration, worker memory and index plans against approved budgets. If it exceeds them, optimize before release rather than hiding the gate.

## Evidence ledger and release decision

For every open item record: candidate commit, environment, scenario ID, actor/role, source records, exact command, selected tests, expected outcome, actual outcome, log/screenshot paths, status, reviewer and exception rationale. Use `pass`, `fail`, `blocked`, `not_run`, never a blank interpreted as pass.

Close points 1–3 only when:

- Fresh and restored install/upgrade and full regression pass with nonzero intended selections.
- Concurrency, stale actions and recovery have observed evidence.
- No foreign-club/foreign-official access or false-ready condition remains.
- Notifications and coverage activities are idempotent and clean up correctly.
- Rollback is rehearsed with a named owner and measured recovery.
- Actual role journeys and usability observations pass approved targets.
- Performance and all unresolved repository scans are reviewed.

The validation guide is organized around observable outcomes and retained evidence, so implemented code is not confused with a qualified release.
