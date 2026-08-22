---
name: custom-module-ci-loop
description: 'Run CI tests on custom Odoo modules in this sports federation repo. Use when asked to run module or suite CI, report errors or fails, inspect CI logs, implement bug fixes, rerun focused tests, and iterate until CI passes.'
argument-hint: 'Modules or suites to test, plus whether to stop at focused CI or finish with full CI'
user-invocable: true
---

# Custom Module CI Loop

## What This Skill Produces

This skill runs the repository's containerized CI for one or more custom modules or named suites, identifies the real failing cause from the generated logs, applies minimal bug fixes, reruns the relevant CI scope, and finishes only when the requested CI scope is green.

Use this for tasks like:
- Run CI tests on custom modules and report errors or fails.
- Investigate why a module install or test run is failing.
- Keep fixing regressions until CI passes.
- Validate a change with focused module CI and then broader suite or full CI.

This workflow is workspace-specific. It assumes the shared CI runner and log layout under `ci/` in this repository.

## Inputs To Extract

From the user's request, determine:
- Target modules named explicitly with `sports_federation_*` identifiers.
- Target suites if the user names a maintained suite.
- Whether the user wants only focused module validation or a broader final run.
- Whether the request is only for diagnosis/reporting or also for code fixes.

If the request does not name a module or suite, infer the likely scope from changed files first.

## Repo Facts

- Run CI from the repository root that contains `ci/run_tests.sh`.
- Primary entrypoint: `bash ./ci/run_tests.sh`
- Named suites:
  - `competition_core`
  - `portal_public_ops`
  - `finance_reporting`
- Logs are written to `ci/logs/<timestamp>/`
- Key log files:
  - `summary.log`
  - `raw.log`
  - `errors.log`

## Procedure

1. Check the working tree first.
   - Inspect changed files so you know the likely module scope.
   - Do not revert unrelated user changes.

2. Choose the smallest useful CI scope.
   - For a single module change, start with `bash ./ci/run_tests.sh --module <module>`.
   - For shared flows, use one or more named suites.
   - If the user asked for general coverage and the fix touches shared services or cross-module inheritance, plan for a final full run with `bash ./ci/run_tests.sh`.

3. Run CI and capture the newest log directory.
   - Use the command output to identify the newest `ci/logs/<timestamp>/` folder.
   - Read `summary.log` first, then `errors.log`, then the relevant sections of `raw.log`.

4. Treat the final result summary as authoritative.
   - Use the CI exit code and the final test summary to determine pass or fail.
   - Do not treat every line in `errors.log` as a real failure.

5. Separate real failures from expected log noise.
   - Duplicate-key SQL traces may be expected in uniqueness tests.
   - Docutils warnings may appear without failing the run.
   - If the summary ends with `0 failed, 0 error(s)`, treat the run as green unless the exit code or traceback proves otherwise.

6. Find the first real root cause.
   - Identify the first traceback, failed assertion, install error, or model registry error that explains the non-zero exit.
   - Search the affected module and any shared service code before editing.

7. Implement the smallest fix at the root cause.
   - Prefer fixing the shared seam rather than patching symptoms in tests.
   - Add or adjust regression tests when behavior changes.
   - Keep module boundaries intact and preserve unrelated behavior.

8. Watch for optional dependency seams.
   - When code touches models from optional addons, prefer safe registry lookup such as `env.get("model.name")` instead of direct registry access.
   - Guard logic when the optional model is unavailable.

9. Rerun targeted CI after each fix.
   - Re-run the smallest affected module or suite first.
   - Keep iterating until that scope is green.

10. Broaden verification before finishing.
   - If the change touched shared services, inherited models, workflow docs, portal/public behavior, or multiple modules, run the relevant suite or the full repository CI.

11. Report the outcome clearly.
   - State what failed first.
   - State the root cause.
   - State what was changed.
   - State the final CI scope that passed.
   - Mention residual noise separately if it did not fail the run.

## Decision Points

### If install fails before tests start

Check:
- `__manifest__.py` dependencies
- missing `data` registrations
- ACL or security XML issues
- XML view syntax
- direct access to models from optional addons

### If tests fail after install

Check:
- changed business logic first
- affected services in `services/`
- model constraints and onchanges
- test fixtures that now violate stricter rules
- cross-module inherit behavior

### If the log looks noisy

Prioritize:
- the first traceback tied to the failing exit code
- the final summary line in `raw.log`
- module-specific test counts and failure totals

### If a fix in one module breaks another

Expand from:
- single module CI
- to relevant suite CI
- to full CI when shared code changed

## Quality Bar For Completion

Do not stop at the first patch. Finish only when:
- the requested CI scope exits with code `0`
- the final summary shows no failing tests in that scope
- the real failure cause has been fixed, not bypassed
- regression tests were added or updated when behavior changed
- relevant docs were updated for workflow or user-facing behavior changes
- unrelated worktree changes were left intact

## Good Reporting Pattern

Include:
- target scope run
- first real failing symptom
- root cause
- files changed
- final focused CI result
- final broader CI result, if run

Keep non-failing warnings separate from real failures.

## Example Invocations

- `/custom-module-ci-loop sports_federation_format, sports_federation_scheduling, and sports_federation_venues; keep fixing until all pass`
- `/custom-module-ci-loop run CI for the portal_public_ops suite, report the first real failure, and fix it`
- `/custom-module-ci-loop inspect failing custom module CI, rerun the affected module first, then full CI when green`