# Repository Baseline

Owner: Federation Platform Team

Review cadence: Every release candidate

A release candidate is reproducible only when it is built and qualified from one
clean Git commit. Generated review bundles, runtime configuration, logs, and
release evidence are outputs and must not be mixed with product changes.

## Required baseline

Before structural, security, migration, or release work:

1. Resolve or intentionally discard every tracked worktree change.
2. Commit every source file required by the candidate.
3. Record the exact commit SHA and supported Odoo, Python, and PostgreSQL versions.
4. Run `scripts/ci/run_release_baseline.sh` from that commit.
5. Preserve the generated evidence outside the tracked source tree.

The baseline runner captures `codebase-inventory.json` before executing release
lanes. The inventory provides deterministic review lists for:

- addons and dependencies;
- HTTP routes and declared authentication/CSRF settings;
- calls using `sudo()`;
- raw-SQL candidates;
- scheduled jobs;
- migrations;
- Odoo model declarations;
- large Python files that require maintainability review.

The inventory does not approve these surfaces. Security and architecture owners
must review changes to them in the candidate diff.

All Odoo release lanes run inside the pinned `odoo:19` Docker image with the
canonical Compose file `ci/docker-compose.ci.yaml`. The baseline retains one
isolated Compose project while it runs the fresh-install, focused, and upgrade
lanes, then removes the project after evidence capture. No host `odoo-bin`
checkout is required.


## Evidence completeness

The baseline runs every required lane and records one `lane-<name>.json` file and
one immutable log digest per lane. Required lanes are:

- preflight;
- static validation;
- fresh install;
- same-version upgrade;
- competition core;
- portal;
- public site;
- performance;
- operator acceptance;
- release focus;
- full standard suite.

A lane record contains the candidate SHA, exact command, start and finish time,
duration, exit code, tool versions, runner identity, database name, and log hash.
Failed lanes require a failure classification. The runner initially records
`unclassified` unless the operator supplies a lane-specific environment value,
for example:

```bash
export RELEASE_FAILURE_CLASSIFICATION_UPGRADE=migration_defect
```

Allowed classifications are defined by `ci/capture_release_evidence.py`. An
unclassified failure remains a failed qualification and must be triaged before
release approval.

`ci/finalize_release_evidence.py` rejects missing, duplicate, skipped, malformed,
or cross-commit lane evidence. A release summary passes only when every required
lane is present for the current commit and every lane passed. Inventory JSON is
supporting evidence and is deliberately excluded from lane status calculation.

## Review bundles

Generate `current_sources.txt`, `current_sources.jsonl.txt`, and
`current_git_metadata.txt` with:

```bash
python3 source_collector.py
```

These files are review artifacts. Do not commit them and do not use their
regeneration as evidence of a product change.

## Failure policy

A failing validation lane remains failed until its root cause is classified and
corrected. Do not weaken a valid test, skip a migration rehearsal, or update an
evidence status manually to obtain a passing candidate.
