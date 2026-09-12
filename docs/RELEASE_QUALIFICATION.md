# Release Qualification

The authoritative release decision combines application qualification with a
migration and rollback rehearsal against one approved production-like backup.
Neither result may be inferred from an older commit or from manually edited
status files.

## Required environment

```bash
export RELEASE_BACKUP_DIR=/secure/path/to/approved-backup
export ROLLBACK_OWNER="Release owner"
export ROLLBACK_TRIGGER="Invariant comparison or acceptance validation fails"
```

## Execute qualification

```bash
scripts/ci/run_release_qualification.sh
```

The command runs the complete SHA-bound release baseline, validates browser
execution, restores and upgrades the approved backup, executes operator
acceptance, restores the rollback database, compares invariants, and validates
the resulting evidence as one release decision.

A release remains blocked when the approved backup is unavailable. Automation
cannot manufacture production-like migration or rollback evidence.

## Reliability contracts

`ci/contracts/reliability_contract.json` records the required destructive
operation tests, replay-safe capabilities, and reviewed runtime SQL boundaries.
Runtime SQL outside this allowlist fails static validation. Migrations and tests
remain separately reviewable and are excluded from the runtime allowlist.
