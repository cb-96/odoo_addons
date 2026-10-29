# Release confidence automation

## What is included

- `ci/release_confidence.py`: plan/run/scenario/verify commands wrapping the existing
  `scripts/ci/run_release_qualification.sh`, not a second replacement release pipeline.
- `ci/release_confidence_adapter.py`: executes real Odoo test commands and requires mapped
  test methods to appear in a passing nonzero run before generating scenario evidence.
- `scripts/ci/run_confidence_scenario.sh`: fresh-database scenario driver with cleanup.
- `ci/attachment_restore_scenario.py`: attachment-only approved-backup driver; restores the
  original dump and filestore to two generated targets and probes `ir.attachment.raw` in Odoo.
- `ci/release_confidence/scenarios.json`: ten scenario groups, 44 required outcome checks.
- `ci/test_release_confidence.py`: harness unit tests, separate from product qualification.
- `docs/RELEASE_CONFIDENCE_AGENT.md`: detailed execution and missing-test implementation brief.
- Small guarded changes to the existing RC runner: a confidence test-tag lane and ownership
  repair for the isolated restored filestore only. Normal runs do not enable that repair.

## Coverage

Existing qualification handles preflight/static, clean install, upgrade, full suite,
performance, operator acceptance, browser focus, backup restore, migration invariants and
rollback. The new gate additionally requires role journeys, ownership/approval isolation,
interrupted operations, drafts, attachment readability, notification/job/integration recovery,
match-day fallback and mobile/accessibility evidence. Attachment restore has a specialized
driver; unrelated missing scenarios remain BLOCKED.

This package does not pretend all those application tests already exist. The agent must
inspect existing assertions, map them and implement gaps. The generic driver can execute
existing selected tests immediately; no fabricated result JSON or historic logs are accepted.
Attachment evidence uses the dedicated backup-based driver below; passing its harness tests
does not claim that a real backup restore has been executed.

## Assertion audit status

Complete exact-method maps currently exist for `access_isolation`, `integration_recovery`,
`job_recovery`, and `notification_recovery` under `ci/release_confidence/case_maps/`.
The other five scenarios remain blocked and have no case maps: `role_journeys`,
`interrupted_operations`, `draft_recovery`, `matchday_fallback`, and `mobile_accessibility`.
In particular, the current browser tour does not create and publish a
competition; static portal checks do not prove mobile rendering or touch usability; there is
no two-connection transition race test, disabled-storage/account-switch draft test, or manual
match-day reconciliation browser journey. Attachment readability remains unexecuted until an
operator supplies the independently recorded attachment metadata and source-version checkout.

The focused `sf_release_confidence` tag lane is a development check only. It is not a full
release qualification or backup-restore result. Integration delivery failures intentionally
surface as operator-action work for manual replay; the tests do not claim automatic retry
exhaustion or a production alert transport. Unsupported guardian and payer access is denied,
not implemented as a separate identity capability.

## Installation

Apply `release_confidence.patch` from the repository root, or copy the included files.
Do not apply both. The patch targets the supplied working-tree source; it does not include
or reapply the earlier usability patch. Commit the intended candidate, automation and any
new test mappings before recording final evidence.

```sh
git apply --check release_confidence.patch
git apply release_confidence.patch
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_release_confidence.py -v
python ci/release_confidence.py plan
```

Use a dedicated Linux CI runner with Docker Compose. A sanctioned sanitized backup and
filestore archive, rollback owner and trigger are mandatory. The tool does not obtain or
sanitize backups, and never deploys. See the agent brief for execution commands.

## Attachment restore inputs and reproduction

This scenario is accepted only through `python ci/release_confidence.py scenario --name
attachment_restore`. It does not accept a database name, arbitrary backup path, or filestore
path. It consumes the approved backup already bound to the successful release-confidence
`run.json`, then uses only its generated `MIGRATION_TARGET_DB`, `MIGRATION_ROLLBACK_DB`,
`FILESTORE_ROOT`, Compose project/config and private scenario-artifact directory. The backup
directory and source checkout must be outside the repository workspace; default repository
backup and filestore locations are rejected.

Before running it, an operator must independently inventory one known attachment in that
approved backup and place a private mode-0600 JSON record outside the repository and scenario
evidence. The driver never searches for or selects an attachment. Required record shape:

```json
{
  "schema_version": 1,
  "recorded_by": "operator identity",
  "recorded_at": "2026-10-29T12:00:00+00:00",
  "backup_dump_sha256": "64 lowercase hexadecimal characters",
  "attachment": {
    "id": 123,
    "name": "independently inventoried filename",
    "checksum": "40 lowercase hexadecimal Odoo SHA-1 characters",
    "size": 456,
    "sha256": "64 lowercase hexadecimal characters for the raw bytes"
  }
}
```

The example values above describe types only; replace them with independently captured
values. `backup_dump_sha256` must match the exact approved dump recorded by the full run.
The source input is a separate, clean git checkout at the exact full commit SHA supplied as
`--source-ref`. It must contain readable, literal-version manifests for every
`sports_federation_*` module listed in the backup's hashed `modules.txt`; rollback probing
also checks those manifest versions against the restored module registry. Use an approved
private backup directory (mode 0700) outside the workspace and a private record file.

After the standard release-confidence `run` has passed, reproduce with a fresh evidence
directory and operator values substituted below:

```sh
PYTHONDONTWRITEBYTECODE=1 python ci/release_confidence.py scenario \
  --evidence-dir /private/release-evidence/candidate-run-002 \
  --name attachment_restore --timeout 21600 -- \
  python3 ci/attachment_restore_scenario.py \
  --attachment-record /private/operator/attachment-record.json \
  --source-checkout /private/source/odoo-addons \
  --source-ref FULL_40_OR_64_HEX_SOURCE_COMMIT
```

The driver checks all inputs before the first restore, verifies the generated Compose project
contains no containers, then starts and readiness-checks only its `ci-db` service. It refuses
to reuse an existing project and cleans up only after claiming its own empty project. It restores
the same approved backup to the generated pre-upgrade target, probes it through Odoo, invokes the existing
`scripts/ci/run_rc_validation.sh upgrade` only for that target, probes after upgrade, restores
the original backup again to the distinct rollback target, and probes that target using the
source-version addon checkout. It never upgrades the rollback target. Three nonempty stage
JSON files, restore reports, an upgrade log and the copied private inventory record are sealed
in scenario evidence. Each of the four configured checks is passed only from those measured
stage results. No restore/upgrade/migration execution is implied by these unit tests.

## Evidence and gate behavior

Every full run uses a fresh external private directory, clean commit, generated project
and database names. Backup checksums, scenario requirement checksum and log/artifact hashes
bind evidence to the candidate. The Compose test network is internal, without published
ports. The restored host filestore is mounted at the container's actual filestore path.
Image builds still need network access; use local doubles for external runtime services.

Reports: `release-confidence.json` and `release-confidence.md` in the run directory.
The initial full run normally returns 1 until all additional scenarios have been executed.
The scenario command also returns 1 while other gates remain missing; inspect its result.json.
Invalid input returns 2. Tests failing, missing summaries, zero tests, skipped tests, changed
source or altered artifacts block release confidence. Upgrade itself is a registry/migration
operation, not a test lane; full tests on the upgraded database supply its runtime test proof.

Evidence checks are not independent test-quality certification. A human must review mapped
assertions, fallback/rollback procedures and release authorisation. No runtime claims are
made from the harness unit tests. Keep runtime files and backups private: they contain
restored data and temporary credentials. Cleanup deletes only generated CI containers/volumes;
private evidence and restored host files remain for diagnosis and operator-managed retention.

## Limits and required follow-through

- Focused Docker/Odoo test execution is available; final backup-based qualification remains
  pending until the operator supplies the required approved backup and rollback attestations.
- Full installation/upgrade/migration/restore evidence and all ten scenario executions remain
  pending. The focused browser tours are not substitutes for the full release browser lane.
- Remaining case maps must reference real tests, not placeholder method names.
- Current functionality is tested honestly; unsupported identity or offline capabilities
  must be documented and safely denied, not represented as implemented.
- Notification and job recovery tests must verify actual operator visibility. This package
  does not install a production monitoring stack or alert transport.
- After any fix or test change, commit and start a new full run. Do not overwrite failed evidence.
- Conservative skip detection may expose legitimate optional skips. Investigate and add the
  required dependencies; do not quietly waive critical coverage. Parser changes require tests.
