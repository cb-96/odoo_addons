# End-to-end release check

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

One command sequence that proves, for one commit, that a competition runs from
creation to a closed, publicly completed competition. Part of it is automated; the
browser walkthrough and the scenario tests are done by an agent with the
instructions in the [agent brief](agents/end-to-end-release.md); novice
sessions are done by people.

## What runs where

| Part | Who | Evidence |
|---|---|---|
| Release lanes: preflight, static, install, upgrade, full, performance, acceptance, focus, lifecycle | `run_end_to_end_release.sh automated` | `summary.json`, `lane-*.json`, `logs/` |
| Migration rehearsal and sign-off (needs an approved sanitized backup) | same command, when the backup variables are set | `migration/manifest.json` |
| Lifecycle scenarios in `sports_federation_app/tests/test_competition_lifecycle_e2e.py` | written once by the agent; run by the `lifecycle` lane | lifecycle lane log |
| Browser walkthrough on a disposable server | agent | `walkthrough/walkthrough.json`, screenshots |
| Novice sessions ([novice usability protocol](acceptance/novice-usability.md)) | people | `human-acceptance.json` |
| Verdict | `run_end_to_end_release.sh verify` | `end-to-end-summary.json` |

The scenario and walkthrough requirements live in
`ci/release_confidence/competition_lifecycle.json`. Change that contract only
through review; never to make a run pass.

## Run it

Requirements: Linux, Docker with Compose, Python 3, curl, a clean committed tree.
The lanes can run for over an hour.

```bash
# Optional, for the migration rehearsal and sign-off:
export RELEASE_BACKUP_DIR=/secure/sanitized-backup ROLLBACK_OWNER="Name" \
       ROLLBACK_TRIGGER="Objective condition"

scripts/ci/run_end_to_end_release.sh all        # automated, then walkthrough server
# hand <evidence>/walkthrough/handoff.json and the agent instructions to the agent
E2E_LEVEL=technical scripts/ci/run_end_to_end_release.sh verify
scripts/ci/run_end_to_end_release.sh stop
```

`all` stops before starting the walkthrough server when an automated lane fails.
Run `automated`, `serve`, `verify` and `stop` separately when needed. Evidence
goes to `${TMPDIR:-/tmp}/sports-federation-release-baseline/<commit>/` unless
`E2E_EVIDENCE_DIR` is set; it must stay outside the repository.

The walkthrough server listens on `127.0.0.1:${SF_WALKTHROUGH_PORT:-18069}` only.
Its database holds seeded role accounts with generated passwords, written to
`walkthrough/handoff.json` with owner-only permissions. Remove it with `stop`.

## Verdicts

- `not-qualified`: an automated lane failed or is missing, or a walkthrough step
  did not pass, or an unresolved blocker defect is recorded.
- `technically-qualified`: all automated lanes and walkthrough steps passed for
  this commit; novice sessions are missing or incomplete.
- `release-qualified`: the above plus completed novice sessions for this commit
  (at least five each for club representatives, organisers and court operators,
  with no critical incident).

`verify` exits 0 at the requested level (`E2E_LEVEL=technical` or `release`,
default `release`). Any commit after the evidence was produced invalidates it.

## Recording novice sessions

Write `human-acceptance.json` in the evidence directory after the sessions:

```json
{
  "commit": "<candidate commit>",
  "sessions": [
    {"participant": "P01", "role": "club_representative", "completed": true,
     "task_results": "see the novice usability protocol record fields"}
  ],
  "critical_incidents": []
}
```

Only the people who ran the sessions write this file.
