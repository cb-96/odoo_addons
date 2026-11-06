# CI and quality gates

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

What runs automatically, where it is defined, and how to reproduce it
locally. Writing tests is covered in the [testing guide](testing.md);
release-candidate qualification in [release qualification](../release/README.md).

## Pipelines

| Workflow | Trigger | Runs |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Pull requests and pushes | Static and contract checks, a nightly lint report, Odoo test suites in Docker |
| `.github/workflows/release-candidate.yml` | Release candidates | `scripts/ci/run_rc_validation.sh` lanes in the Compose runtime (`upgrade`, `full`, `cleanup`, …) |
| `.github/workflows/upstream-compatibility.yml` | Scheduled or manual | The broad Odoo `standard` suite, kept out of release qualification |

## Odoo test suites

All Odoo tests run in the `odoo:19` image through `ci/run_tests.sh` and
`ci/docker-compose.ci.yaml`. CI runs these named suites:

| Suite | Coverage |
| --- | --- |
| `competition_core` | Base, tournament, scheduling, results and standings critical path |
| `portal_public_ops` | Portal ownership, public routes, compliance, standings, venue-facing flows |
| `finance_reporting` | Finance bridge and reporting |
| `people_rosters_rules` | People, rosters, rules and officiating |
| `ops_and_notifications` | Discipline, governance, notifications, import tools, demo |
| `release_surfaces` | Broader portal/public, match-day, compliance and notification release checks |
| `rosters_readiness_guard` | Participant readiness regression and post-test discovery gate |

`bash ci/run_tests.sh --list-suites` prints the current definitions.

## Static and contract checks

`ci.yml` runs these on every change; `scripts/ci/run_rc_validation.sh static`
runs the full set used for release candidates (it adds the transition,
privilege, reliability, readiness and documentation contracts).

| Area | Checks |
| --- | --- |
| Lint and structure | `ci/run_repo_lint.sh --strict` (Black, Flake8), `check_addon_integrity.py`, `check_application_entrypoint.py`, `check_module_dependency_drift.py`, `check_test_discovery.py`, `check_ci_hygiene.py`, `check_access_csv_integrity.py` |
| Documentation | `check_doc_freshness.py`, `check_markdown_links.py`, `check_delivery_language.py`, `check_release_train.py`, `check_module_owners.py`, `check_competition_ui_workflow.py`, `check_public_route_cutover_docs.py` |
| Migrations | `check_migration_review.py`, `check_constraint_index_contracts.py`, `check_explain_snapshots.py`, `check_migration_rehearsal_contract.py`, `check_legacy_engine_removed.py` |
| Security boundaries | `check_portal_sudo_guard.py`, `check_privileged_inventory_quality.py`, `check_privileged_mutation_boundaries.py`, `check_privileged_command_contracts.py`, `check_audit_acl_integrity.py`, `check_http_route_ownership.py` |
| Workflow contracts | `check_workflow_state_contracts.py`, `check_workflow_command_boundaries.py`, `check_workflow_transition_foundation.py`, `check_matchday_transition_contract.py`, `check_result_transition_contract.py`, `check_readiness_vocabulary.py`, `check_task_projection.py` |
| Competition contracts | `check_competition_pipeline_contract.py`, `check_fixture_ownership_contract.py`, `check_rules_contract.py`, `check_registration_contract.py`, `check_officiating_contract.py`, `check_schedule_handoff_contract.py`, `check_schedule_amendment_contract.py`, `check_publication_integrity_contract.py`, `check_public_competition_contract.py`, `check_portal_competition_ownership.py`, `check_competition_workflow_simplification.py` |
| Integrations and reliability | `check_openapi_contracts.py`, `check_notification_side_effect_contract.py`, `check_destructive_token_contract.py`, `check_reliability_contract.py`, `check_retention_visibility_contract.py` |
| Release | `check_rc_test_scope.py`, `check_release_focus_contract.py`, `check_release_qualification.py`, `check_rc_product_readiness.py`, `check_rc_usability.py`, `check_known_release_failures.py`, `check_source_collector_contract.py` |

All checks live in `ci/` and run with `python3 ci/<check>.py`. Machine-readable
contracts they read are in `ci/contracts/`.

## Documents read by CI

Some checks read documentation by path or require tokens in it. Moving or
renaming those files requires updating the check; the list is in the
[documentation map](../README.md#checks-that-read-the-documentation).

## Workflow contract upkeep

- Keep `ci/contracts/workflow_state_contracts.json` aligned with each
  workflow document and model state source.
- If CI reports undocumented states, add the state to the workflow and the
  contract, or remove or rename it in the code.
- If CI reports missing actions, add the guarded action method or update the
  contract when the workflow changed by design.

## Reading CI output

`ci/run_tests.sh` ends with a results block (exit code, tests run, passed,
failed, errors). A non-zero exit code is a failure. Each run keeps
`test_failures.log`, `expected_diagnostics.log`, `infrastructure.log` and
`full.log`; `--keep-on-failure` also keeps the containers, database, filestore
and configuration and prints inspection commands.

```bash
docker logs <container> 2>&1 | grep -A 20 "FAIL\|ERROR\|Traceback"
```

Prune old logs with `bash ci/prune_ci_logs.sh 30`.

## Release-candidate lane failures

Odoo lanes write `odoo-rc.log`. On a non-zero exit the runner prints an error
summary and the last 200 lines. gettext `Empty msgid` warnings alone do not
explain exit code 1; look for the first test failure or module-load traceback.

## Release orchestration entrypoint

`python ci/run_release.py <profile>` owns candidate, readiness and qualification
sequencing. The existing candidate/readiness/qualification shell commands are
compatibility adapters, not separate implementations. CI release-candidate and
upstream workflows call the same runner's `rc --lane` profile.

- `candidate`: product/readiness checks and the complete baseline. Without a
  backup it explicitly reports that migration and qualification were not run.
- `readiness`: reliability checks, baseline, exact-commit evidence validation
  and browser-log validation. It is not migration sign-off or human acceptance.
- `qualification`: readiness plus approved-backup migration/rollback rehearsal
  and exact-commit sign-off. Backup, rollback owner and trigger are mandatory
  before any expensive command executes.
- `rc --lane <name>`: existing Docker RC lane, including cleanup and upstream.
- `baseline`, `migration`, `walkthrough`, `confidence`: direct access to the
  specialized backends. Use `--` before backend arguments.

Examples:

```bash
python ci/run_release.py rc --lane static
python ci/run_release.py candidate
python ci/run_release.py readiness --evidence-dir /tmp/federation-evidence
python ci/run_release.py qualification --backup-dir /approved/backup \
  --rollback-owner "Release owner" --rollback-trigger "Failed invariants"
python ci/run_release.py walkthrough -- verify
python ci/run_release.py confidence -- verify --evidence-dir /tmp/confidence
```

The baseline backend remains the owner of lane logs, failure classification,
exact-commit manifests and Docker cleanup. Migration, walkthrough and confidence
backends retain their distinct data-preservation, browser and human acceptance
gates. The runner forwards argument arrays without shell interpolation and
preserves backend failure codes. It does not invent a combined passing verdict
from missing evidence or a skipped rehearsal.

Evidence defaults are outside the repository and shared across the profile's
commands. Candidate/readiness migration requests now require rollback owner and
trigger as well as the backup; an incomplete request fails before baseline work.
Existing qualification environment variables remain supported. RC environment
and retention settings pass through unchanged.

The public-competition structural check now runs in repository lint. Its dead
invocation after `exit` in the Odoo test script was removed. Test orchestration
with `python -m unittest ci.test_release_runner`; these tests use subprocess
doubles and do not run Docker, migration, Odoo or human acceptance.
