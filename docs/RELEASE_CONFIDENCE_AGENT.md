# Agent instructions: establish release confidence

## Objective and authority

Automate and execute release qualification for the actual candidate. Produce reproducible,
commit-bound evidence for installation, upgrade, permissions, browser journeys, interrupted
operations, backup restoration, notifications, jobs, integrations and match-day fallback.
You may implement missing tests and small fixes in a development branch. You may NOT deploy,
use production credentials, send real messages, charge payments, weaken approval controls,
change acceptance requirements to obtain a pass, or delete existing working-tree changes.

A missing capability is not a passing test. Where guardian/payer accounts are not supported,
prove that unsupported access is denied; document the functional limit. Do not introduce an
entire identity subsystem merely to finish this release gate. Offline capture is not required:
verify an honest network-loss state and the documented manual fallback instead.

## Prerequisites you must resolve before destructive test operations

1. Read repository CONTRIBUTING, TESTING_GUIDE, RELEASE_RUNBOOK and the existing scripts in
   scripts/ci. Read ci/release_confidence/scenarios.json and both new Python runners.
2. Inspect `git status`, branch and commit. Preserve existing work. Confirm the earlier
   usability patch is present if that is the intended candidate; do not apply it twice.
3. Obtain an approved SANITIZED production-like backup, with exactly one *.dump, one
  filestore_*.tar.gz and modules.txt, using the existing upgrade-tool backup format. Confirm
  the source version, source code commit, modules, attachment inventory and anonymisation. Disable
   outgoing SMTP, webhooks, live payment providers and automatic external fetches in the
   sanitized database before it becomes a test input. Use a dedicated local CI Docker daemon.
4. Require an accountable rollback owner and objective rollback trigger from the operator.
   Do not invent either. Missing backup/owner/credentials are BLOCKED, not skipped.
5. Use a private evidence directory outside the repository. Never point restore tooling at
   an existing database or production project. The new runner generates all target names.
6. Confirm Linux, Python 3, Bash, Docker Compose and enough disk/memory for the repository
   CI image, Chrome, PostgreSQL and multiple test databases. Browser dependency installation
   belongs in the CI image, not a silent SkipTest. Image builds need network access; test
   containers use an internal network. External integration tests must use local doubles.

## Inspect coverage before running the final candidate

Use AST/test discovery and inspect actual assertions, not only filenames. Build
`ci/release_confidence/case_maps/<scenario>.json` for each scenario. Each required check
maps to an exact Odoo test method. Reuse these starting points:

- Role journeys: sports_federation_demo/tests/test_operator_role_acceptance.py and
  test_browser_competition_lifecycle.py; portal/tests/test_competition_portal.py,
  test_season_registration.py, test_roster_portal_access.py, test_parental_approval_portal.py.
- Permissions: portal/tests/test_production_security_matrix.py, test_portal_ownership_guard.py,
  test_officiating_portal_access.py, test_result_portal_access.py and negative HTTP tests.
- Publication/result concurrency: scheduling/tests, schedule_approval/tests,
  result_control/tests and matchday/tests/test_matchday_operator_handoff.py.
- Recovery: setup_flow/tests, roster lineup tests and actual browser recovery tests.
- Notifications: notifications/tests/test_notification_triggers.py, test_notifications.py.
- Jobs/monitoring: standings job tests; reporting/tests/test_report_schedule_cron.py,
  test_operational_dashboard.py; shared operation-job tests.
- Integrations: import_tools/tests/test_integration_api.py and delivery tests.
- Mobile/accessibility: portal/tests/test_template_mobile.py and test_template_accessibility.py
  are only static starting points. Add real browser viewport, keyboard and focus assertions.

These paths are from the supplied source. Confirm names against the actual checkout.
A broad passing suite does not prove a check if its mapped test does not assert the outcome.

## Implement missing tests, then commit the candidate

For every required check, document fixture, actor, action, expected state and negative case.
Use model tests for invariants, HttpCase for real route permissions and browser tours for
actual interaction. Register new tests in tests/__init__.py. Use post_install tags for HTTP
and browser tests. Extend existing CI tags or add dedicated `sf_release_confidence` tests
with an explicit runner; do not rely on unselected tests. Commit tests, fixes and case maps
before the final run. Any code change afterwards invalidates the full run.

Required assertion depth:

- Role separation: use ordinary accounts, not admin. Exercise simple and controlled policy.
  Prove the planner cannot approve its own publication/result when independent review applies.
- Ownership: two clubs, unrelated team, anonymous user and direct crafted HTTP/RPC requests.
  Assert both denied response and unchanged database. UI hiding is not an access-control test.
- Interruption: duplicate commands, stale revision, rollback after injected failure and two
  independent database connections. Prove at most one official transition/event. Killing a
  worker is allowed only in the generated disposable stack; restore it afterwards.
- Drafts: refresh, restore, discard, failed POST, account switch, expired draft and disabled
  browser storage. Assert no cached token, document, free text or other user's draft.
- Attachment restore: choose a known sanitized attachment with an independently recorded
  checksum. Read its bytes THROUGH ODOO after upgrade and rollback. A host file or a restore
  success message alone is insufficient. Check attachment metadata and container file access.
- Notifications: inject a local delivery failure; verify business action commits, operator
  sees failure, retry is safe, and resolved tasks stop reminders. Never send real email.
- Jobs: force a stale running job; exercise retry/dead-letter handling and the actual operator
  dashboard/alert. Prove recovery is idempotent. Do not assume every job has a recovery policy.
- Integrations: invalid token, invalid payload, duplicate delivery and retry exhaustion;
  assert no partial mutation and visible failure. Use local mocked services only.
- Fallback: export the current published schedule; simulate connectivity loss; verify UI
  does not claim a result was saved. Reconcile a manually recorded result through normal
  submission/review. Do not claim offline sync exists if it does not.
- Mobile: real small viewport, keyboard-only navigation, focus after errors and usable court
  controls. Static HTML checks do not prove actual rendering.

## Execute the existing qualification through the new runner

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_release_confidence.py -v
python ci/release_confidence.py plan
python ci/release_confidence.py run \
  --backup-dir /approved/sanitized-backup \
  --evidence-dir /private/release-evidence/candidate-run-001 \
  --rollback-owner 'OPERATOR-SUPPLIED OWNER' \
  --rollback-trigger 'OPERATOR-SUPPLIED OBJECTIVE TRIGGER' \
  --approved-sanitized-backup
```

Replace placeholders with authorised values. The runner invokes existing release
qualification, which already runs baseline lanes, migration rehearsal and sign-off checks.
It additionally binds the restored filestore into Odoo's actual container path, generates
an isolated Compose configuration and records checksums. It does not create a backup or
anonymise one for you. It intentionally returns nonzero until additional scenarios pass.

## Execute additional scenarios with real test evidence

Create a committed case map containing every check in that scenario, for example:

```json
{
  "delivery_failure_does_not_rollback_business_action": "ActualTestClass.test_actual_method",
  "failed_delivery_visible_to_operator": "ActualTestClass.test_actual_method",
  "retry_does_not_duplicate_business_action": "ActualTestClass.test_actual_method",
  "resolved_task_stops_reminders": "ActualTestClass.test_actual_method"
}
```

Those method names are placeholders, not existing tests. Replace them after inspection.
Multiple checks may map to one method only when that method actually asserts all outcomes.

Run a scenario through the adapter and a committed scenario driver:

```sh
python ci/release_confidence.py scenario \
  --evidence-dir /private/release-evidence/candidate-run-001 \
  --name notification_recovery -- \
  python ci/release_confidence_adapter.py \
  --case-map ci/release_confidence/case_maps/notification_recovery.json -- \
  bash scripts/ci/run_confidence_scenario.sh --test-tags sf_release_confidence
```

The included generic driver prepares a fresh disposable database, runs selected Odoo
tests, preserves logs and cleans up in a trap. Tag your new tests sf_release_confidence,
or pass exact existing module/class/method tags. It inherits the generated
RC_COMPOSE_FILE, RC_COMPOSE_PROJECT and database names. Use the existing prepare/install
and tagged-test tooling; never an arbitrary production database. Qualification cleanup
removes ephemeral databases, so scenario drivers must prepare/restore their own fixtures.
The generic driver is for fresh fixtures, not backup-based attachment tests. The dedicated
`ci/attachment_restore_scenario.py` driver is accepted only through
`python ci/release_confidence.py scenario --name attachment_restore`. Before any restore it
requires all generated `SF_CONFIDENCE_*`/`RC_*` paths and names, a private operator-recorded
attachment inventory tied to the exact approved dump hash, and a separate clean source-version
addon checkout at the stated full git commit. The input record must contain `recorded_by`,
timezone-aware `recorded_at`, `backup_dump_sha256`, and attachment `id`, `name`, Odoo `checksum`,
`size`, and raw-byte `sha256`. It rejects backup/source paths inside the repository workspace,
arbitrary DB names and filestore paths, missing source manifests, dirty source, and source
manifest versions that do not match the rollback database.

Use the exact operator-input schema and reproduction command in
`docs/RELEASE_CONFIDENCE.md#attachment-restore-inputs-and-reproduction`. The driver restores the
original approved backup twice: once to the generated migration target (probe before, upgrade
with the existing RC `upgrade` lane, probe after) and once to a separate generated rollback
target (probe using source-version addon code, never upgrade that database). Every stage reads
the selected record through Odoo ORM `ir.attachment.raw`, checks the database fields, SHA-256,
Odoo checksum, `_full_path`, filestore bytes and container readability. Do not assume the
previous qualification's in-memory PostgreSQL databases still exist.

The adapter rejects zero tests, missing summaries, unobserved mapped methods, nonzero exit
codes and skips. It writes result.json only after execution. The outer runner seals logs
and evidence. Repeat for every scenario in scenarios.json. Return code 1 can mean other
scenarios are still missing; inspect result.json and release-confidence.json. Return code
2 means invalid inputs/environment. A failed recorded scenario requires a fresh full run
rather than overwriting its history. Diagnose and fix; do not rerun unchanged failures.

## Diagnose failures and re-run correctly

Classify infrastructure, product, fixture, migration or test defects. Preserve the original
logs. Do not weaken tests, disable browser execution, change required checks, mark missing
features passed, edit evidence or use historic passing logs. If a parser does not recognise
real log output, add a parser unit test and fix the parser, commit, then start a new run.
Every candidate change requires a new clean commit and fresh evidence directory.

## Final verification and deliverables

```sh
python ci/release_confidence.py verify \
  --evidence-dir /private/release-evidence/candidate-run-001
```

Deliver:
- Candidate commit, source backup/version identity and runtime image versions/digests.
- Full baseline/migration evidence and ten scenario result files with actual test IDs.
- JSON and Markdown release-confidence reports, remaining blockers and known limits.
- Changed tests/fixes, exact reproduction commands and a proposed commit message.
- Operational fallback and rollback runbooks reviewed by the responsible operator.

The gate is evidence validation, not independent certification of test quality. Review the
assertions and have the accountable operator authorise release separately. No deployment
is included. Protect evidence: logs may contain personal data; runtime contains temporary
credentials and restored files. Do not publish the entire evidence directory or backup.
