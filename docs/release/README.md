# Release qualification

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

How a release candidate is qualified and approved. The authoritative release
decision combines application qualification with a migration and rollback
rehearsal against one approved production-like backup. Neither result may be
inferred from an older commit or from manually edited status files.

The operator procedure for the actual upgrade is the
[release runbook](../operations/release-runbook.md); current status and open
blockers are in the [roadmap](../roadmap.md).

## Documents in this section

| Document | Purpose |
| --- | --- |
| [Approval policy](approval-policy.md) | Automated evidence and human approvals required to tag a candidate |
| [Stabilization plan](stabilization-plan.md) | Release-risk areas that remain gates after the competition cutover |
| [Pilot scenario](pilot-scenario.md) | Deterministic federation storyline used by the release-focus lane |
| [End-to-end release check](end-to-end-check.md) | One command sequence that proves a competition runs from creation to close |
| [Release confidence automation](release-confidence.md) | Plan/run/scenario/verify runner around the qualification scripts |
| [Acceptance suites](acceptance/README.md) | Human and staging scenarios per capability |
| [Agent briefs](agents/) | Instructions for AI agents that execute the end-to-end and release-confidence work |

## Clean baseline

A candidate is reproducible only when it is built and qualified from one clean
Git commit. Generated review bundles, runtime configuration, logs and release
evidence are outputs and must not be mixed with product changes.

1. Resolve or intentionally discard every tracked worktree change.
2. Commit every source file required by the candidate.
3. Record the exact commit SHA and the supported Odoo, Python and PostgreSQL
   versions.
4. Run the baseline from that commit and keep the evidence outside the tracked
   source tree.

`scripts/ci/run_rc_validation.sh preflight` enforces the clean-worktree rule.

## Execute qualification

```bash
export RELEASE_BACKUP_DIR=/secure/path/to/approved-backup
export ROLLBACK_OWNER="Release owner"
export ROLLBACK_TRIGGER="Invariant comparison or acceptance validation fails"
scripts/ci/run_release_qualification.sh
```

The command runs the complete SHA-bound release baseline, validates browser
execution, restores and upgrades the approved backup, executes operator
acceptance, restores the rollback database, compares invariants and validates
the resulting evidence as one release decision. A release stays blocked when
the approved backup is unavailable: automation cannot manufacture
production-like migration or rollback evidence.

The parts can also be run separately:

| Command | Runs |
| --- | --- |
| `scripts/ci/run_release_baseline.sh` | All required lanes with evidence |
| `scripts/ci/run_release_candidate.sh --backup-dir <dir>` | Product-readiness and usability contracts, baseline lanes and, with a backup, the migration rehearsal |
| `scripts/ci/run_migration_rehearsal.sh --backup-dir <dir> …` | Restore, invariant capture, upgrade, acceptance and rollback drill |
| `scripts/ci/run_rc_validation.sh <lane>` | One lane: `preflight`, `static`, `prepare`, `install`, `upgrade`, `confidence`, `core`, `portal`, `public`, `performance`, `acceptance`, `focus`, `lifecycle`, `full`, `upstream`, `all`, `cleanup` |
| `scripts/ci/run_end_to_end_release.sh` | Lanes plus the browser walkthrough and novice-session evidence |

All Odoo lanes run inside the pinned `odoo:19` Docker image with
`ci/docker-compose.ci.yaml`; no host `odoo-bin` is required. The baseline
keeps one isolated Compose project across the install, focused and upgrade
lanes, then removes it.

## Evidence

The baseline writes one `lane-<name>.json` record and one log digest per lane
to `${TMPDIR:-/tmp}/sports-federation-release-baseline/<commit>/` (override with
`RELEASE_BASELINE_EVIDENCE_DIR`, outside the repository). The migration
rehearsal writes to `artifacts/release/migration/` by default (override with
`MIGRATION_EVIDENCE_DIR`).

Required baseline lanes: preflight, static validation, fresh install with
federation-scoped tests, same-version upgrade, complete federation suite on the
upgraded database, performance, operator acceptance, browser and release
focus, and lifecycle. The `lifecycle` lane runs the contracted end-to-end
competition scenarios in `ci/release_confidence/competition_lifecycle.json`
and fails when any of them is missing, skipped or did not run. The focused
`core`, `portal` and `public` lanes are for diagnosis and are not repeated in
the baseline. The broad Odoo `standard` suite runs separately in the
scheduled/manual **Upstream Odoo compatibility** workflow.

Each lane record contains the candidate SHA, command, start and finish time,
duration, exit code, tool versions, runner identity, database name and log
hash. Failed lanes need a failure classification (allowed values are defined in
`ci/capture_release_evidence.py`), for example:

```bash
export RELEASE_FAILURE_CLASSIFICATION_UPGRADE=migration_defect
```

The baseline also captures `codebase-inventory.json` (addons, routes with auth
and CSRF settings, `sudo()` calls, raw SQL candidates, scheduled jobs,
migrations, models, large files) for security and architecture review. The
inventory is supporting evidence, not an approval.

Validate existing evidence:

```bash
python3 ci/check_release_evidence.py \
  --evidence-dir /path/to/evidence \
  --commit "$(git rev-parse HEAD)" \
  --require-passing
```

The validator and `ci/finalize_release_evidence.py` reject missing, duplicate,
skipped, malformed, modified or cross-commit evidence. A releasable summary has
`status: passed`, `complete: true` and no failed, skipped, mismatched or
invalid lanes.

## Known failures

`ci/contracts/known_release_failures.json` is an accountability registry, not
a release waiver. Every entry needs an owner, issue, exact test, reason and
expiry date. Expired entries fail static validation, and a known failure still
keeps its lane red.

## Required qualification content

- Versioned role and prohibited-permission matrix (`ci/rc_role_matrix.json`).
- Recovery inventory for registration, schedule review, publication
  replacement, job retry and standings correction (`ci/rc_recovery_contract.json`).
- Certified demo federation with clubs, teams, rosters, played matches, results
  and standings (`sports_federation_demo`).
- Integrated lifecycle, keyboard, portal, public-site and release-focus tours.
- Useful empty states and no raw workflow values in user-facing templates.
- Small, medium and large performance profiles for 10, 100 and 500 clubs
  (`ci/rc_performance_profiles.json`).
- Clean install, full addon upgrade, full suite and migration rehearsal.

## Reliability contracts

`ci/contracts/reliability_contract.json` records the required
destructive-operation tests, replay-safe capabilities and reviewed runtime SQL
boundaries. Runtime SQL outside this allowlist fails static validation.
Migrations and tests are reviewed separately and excluded from the allowlist.

## Failure policy

A failing lane stays failed until its root cause is classified and corrected.
Do not weaken a valid test, skip the migration rehearsal or edit an evidence
status manually to obtain a passing candidate.

## Review bundles

```bash
python3 source_collector.py
```

generates `current_sources.txt`, `current_sources.jsonl.txt` and
`current_git_metadata.txt` for code review. They are review artifacts: do not
commit them and do not treat their regeneration as a product change.
