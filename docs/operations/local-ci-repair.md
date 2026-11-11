# Local full CI and bounded repair

This integration targets the existing `federation-ci` and `federation-repair`
containers. It does not create containers or change global firewall settings.
Desktop model endpoint: `192.168.178.90:11434`, model `qwen3.5:9b`.
No desktop filesystem sharing is required.

## Repository patch

Apply the patch on `feat/offline-gameday`. The original `ci.yml` stays unchanged,
including its hosted pull-request checks. New `ci-local.yml` runs only trusted
pushes to that development branch and `autofix/**`, or manual runs on those refs.
The controller watches push events only. Manual CI is diagnostic, not a repair trigger.

The local workflow retains every original lint command and all six Odoo matrix/
release suites. The formerly nightly report and release-surfaces jobs also run on
local pushes. All jobs use the `federation-ci` label; matrices use max-parallel 1.
A final gate rejects any failed, cancelled or skipped required job. This is the
complete existing CI workflow, not the separate manual release-qualification
process, restore rehearsal or human acceptance.

No production integration secrets are injected. Test database credentials are
random per run/attempt/suite. Logs are retained as seven-day artifacts and the
job cleans only its own Compose project. No global Docker prune is performed.
`ci/Dockerfile.odoo-ci` must exist in the real checkout. It was excluded from the
provided source bundle; this patch does not invent or replace its contents.

## Deploy to the existing repair container

Copy the trusted patched repository checkout to pve0 (not the agent workspace).
As root on pve0, from that checkout:

```bash
bash ci/local/deploy-existing.sh
```

The script reads `/root/federation-provision/state/created.json`, checks container
names, refuses CT 110, backs up current repair code/config, preserves credentials,
stops timers, and deploys the updated payload. It refuses an active/interrupted
incident. No agent is started during deployment. Configuration resets publishing
to false; state and processed commits are preserved. Controller now watches
`ci-local.yml`, allows all 33 actual application module directories, and requires
successful `Full CI gate` before accepting green CI.

The prior 30-minute wait was too short for a single runner executing the whole
matrix. Budget is now 8 hours per candidate and 25 hours total for at most three
attempts, with a 26-hour service ceiling. These are limits, not expected durations.
Agent remains bounded to 15 minutes per attempt. Desktop must remain awake.

The installed Hermes CLI flags are checked before activation. A pre-existing
Hermes gateway outside the worker service defeats cgroup lifecycle isolation:
verify no such gateway is running and that stopping worker stops its agent.
The deployment does not silently stop unrelated agent services.

## Commit and start

Commit/push the patch before activating repair; that push triggers local CI.
Then on pve0:

```bash
cd /root/federation-provision
bash activate.sh review
```

Review mode saves a patch/report without pushing. After reviewing a successful
controlled incident, use `bash activate.sh publish`, then push a new commit.
Processed commits are not automatically retried. Never merge automatically.

## Tests and recovery

```bash
python3 -m unittest discover -s ci/local -p 'test_*.py'
bash -n ci/local/prepare-env.sh ci/local/cleanup.sh ci/local/deploy-existing.sh
```

Deployment backups are under `/root/federation-repair-backup-*` INSIDE the repair
container. To roll back, stop both timers and services, restore its saved
`federation-repair` directories to their original `/opt` and `/etc` locations,
remove only the new `full-ci-budget.conf` drop-in, and daemon-reload. Inspect
state and remote branches before reactivating; do not delete all incident state.

Existing limitations remain: LXC shares the host kernel; no semantic guarantee
against weakened tests/business rules; source-only transfer is not hardened
against malicious concurrent writers; crash recovery and processed-SHA retry
are manual; controller fetches failed-step logs, not uploaded artifacts; no
automatic workspace cleanup. This is not production release signoff.
