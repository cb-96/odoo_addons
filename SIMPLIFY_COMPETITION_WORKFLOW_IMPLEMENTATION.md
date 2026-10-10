# Simplify Competition Workflow — Implementation and Patch Notes

Implementation date: 2026-10-10
Repository commit: `393dd899739bcb6b66eca99e1bcb942013273c4f` (`comp_planner`)
Patch baseline: the exact dirty working tree supplied in `current_sources.jsonl.txt` and `current_git_metadata.txt`

## Scope delivered

- Preserves all pre-existing unstaged parental-approval and shared game-day-lineup changes.
- Adds one canonical **Competition Hub** entry and a resumable planner with one primary action and unified readiness.
- Moves duplicate, raw-model, specialist, audit, recovery, and technical menus out of ordinary manager navigation while retaining their actions and opt-in advanced routes.
- Fixes planner routing dead ends and hands game-day setup directly to complete-competition schedule planning.
- Makes league, one-day tournament, cup, and custom presets supply remembered editable defaults.
- Rewords workflow modes as Streamlined, Independent Review, and Advanced / Custom; Streamlined continues to execute existing validation, transition, snapshot, and audit commands automatically.
- Adds direct team selection and simple format selection while materializing canonical registration entries, participant sets, structures, fixtures, match days, allocations, and schedules.
- Adds one game-day lineup preparation wizard over the existing shared match-sheet behavior.
- Keeps parental-consent enforcement and projects missing consent plus shared lineups through the existing `federation.operation.task` model.
- Updates migrations, manifests, workflow/navigation contracts, documentation, tests, and browser tours.

## Application order

The downloadable patch is an incremental diff against the supplied current dirty
working tree. It intentionally omits parental-approval, public-site, standings,
notification, workflow-documentation, and shared-lineup changes that are already
present, while retaining later simplification changes on the few overlapping
files.

Keep the working tree exactly as supplied and apply without `--index`, so current
unstaged and untracked work remains unstaged and untracked:

```bash
git apply --check simplify_competition_workflow_incremental.patch
git apply simplify_competition_workflow_incremental.patch
```

Do not apply the earlier cumulative patch before or after this incremental patch.

Odoo module upgrade order:

1. `sports_federation_base`
2. `sports_federation_competition_core`
3. `sports_federation_registration`
4. format/calendar/scheduling/schedule approval dependencies
5. `sports_federation_setup_flow`
6. `sports_federation_matchday` and `sports_federation_rosters`
7. `sports_federation_portal`
8. `sports_federation_navigation`
9. `sports_federation_app`
10. `sports_federation_demo` in non-production databases only

The supported aggregate upgrade command is documented in `RELEASE_RUNBOOK.md`.

## Validation results

Passed against a reconstructed repository with the exact supplied commit, 25
unstaged modifications, and two untracked parental-approval files:

- `git apply --check` on the authoritative dirty-tree preimage;
- application result matched the intended cumulative target for all 1,049 files;
- reverse application restored the exact supplied content, Git modes, file set,
  and 27-line porcelain status;
- `git diff --check`;
- syntax compilation of 42 changed Python files, XML parsing of 12 changed XML
  files, literal parsing of 10 changed manifests, and Node syntax checks for four
  changed JavaScript files;
- 34 focused repository checks covering addon/import/dependency and ACL integrity,
  application entry, test discovery, ordinary/advanced navigation, module owners,
  source collection, documentation, workflow/transition boundaries, competition
  pipeline, schedule handoff/amendment, publication, match day, results, fixture
  ownership, rules, officiating, registration, public competition, notifications,
  portal ownership/sudo, privileged commands/mutations, audit ACLs, migration
  review, and RC usability/product readiness.

The source-only environment has no Odoo server, database, or browser runtime, so
transaction suites, install/upgrade rehearsals, and browser tours remain runtime
release gates.

## Remaining runtime-only gates

- fresh Odoo 19 install of `sports_federation_app` after restoring the repository's CI Dockerfile/environment assets;
- upgrade rehearsal against a production-like database and paired filestore;
- Odoo transaction suites for competition core, people/rosters/rules, and portal/public operations;
- browser tours for the Competition Hub, keyboard use, lineup preparation, and public handoff;
- role-separated manual check for ordinary versus advanced menu visibility;
- Streamlined and Independent Review schedule, lineup, result, snapshot, audit, and rollback checks;
- canonical Black/Flake8 run with the repository-pinned tooling.

## Suggested commit message

```text
feat(competition): unify the end-to-end operator workspace

Add one resumable competition entry, direct team/format/game-day planning,
shared lineup preparation, unified readiness and task projection, while moving
raw and specialist menus behind advanced routing and preserving validation,
permissions, immutable evidence, audits, module ownership and existing work.
```
