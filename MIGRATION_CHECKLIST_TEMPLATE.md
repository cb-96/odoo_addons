# Migration Checklist Template

Use this template in migration-sensitive pull requests (model/view/controller ownership changes).

## Change Summary

- PR/Change: 
- Affected modules:
- Affected surfaces: models / views / controllers
- Release train:

## Migration Impact

- [ ] Schema change (columns/constraints/indexes)
- [ ] Data backfill required
- [ ] View XML ownership changed
- [ ] Controller route ownership changed
- [ ] Security/record rule implications reviewed

## Required Evidence

- [ ] `ci/check_migration_review.py` passes for the branch diff
- [ ] Module README updated (or N/A justified)
- [ ] `TECHNICAL_NOTE.md` / `RELEASE_RUNBOOK.md` / `RELEASE_TRAIN.md` updated as needed
- [ ] `MIGRATION_DRY_RUN_EVIDENCE.md` updated with command output summary
- [ ] `MIGRATION_ROLLBACK_NOTES.md` updated with rollback plan

## Dry-run Plan

Commands used:

```bash
python3 addons/ci/check_migration_review.py --base-ref origin/main
bash addons/ci/run_tests.sh --module <affected_module>
```

Observed results:

- Migration script load/install outcome:
- Test outcomes:
- Known warnings (if any):

## Rollback Plan

- Trigger condition:
- Rollback command(s):
- Data restoration notes:
- Owner:
