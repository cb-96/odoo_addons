# Agent instructions: end-to-end competition release check

## Objective

Prove, for one exact commit, that a competition can be run from creation to a closed,
publicly completed competition by ordinary role accounts, and record evidence that
`scripts/ci/run_end_to_end_release.sh verify` accepts. You do two things the
script cannot: implement the contracted lifecycle test scenarios against a running
Odoo, and perform the browser walkthrough through the real UI.

A run that passes because something was skipped, elevated, bypassed or weakened is a
failed run. Report honestly; a clear "not qualified, here is why" is a good outcome.

## Authority and limits

You MAY:

- read the whole repository and run any script in `scripts/ci` and `ci/`;
- add `sports_federation_app/tests/test_competition_lifecycle_e2e.py` and register it
  in `sports_federation_app/tests/__init__.py`;
- fix defects in the test you wrote;
- propose product fixes as separate commits on a separate branch, each with its own
  commit message, only when a fix is small, obvious and covered by a test.

You MUST NOT:

- deploy, use production data or credentials, send real email/SMS, or call external
  services (use the disposable servers the scripts create);
- edit `ci/release_confidence/competition_lifecycle.json`, `ci/check_lifecycle_coverage.py`,
  `ci/check_end_to_end_evidence.py` or any existing test assertion to obtain a pass;
- use `sudo()`, `workflow_policy_bypass`, direct writes of `state`, `result_state`,
  `graph_state` or `operational_status`, `skipTest`, or administrator accounts for
  actions under test (setup of reference data in `setUpClass` may use the test's
  default environment);
- write or edit `human-acceptance.json`; novice sessions are run by people;
- discard or overwrite existing uncommitted work, force-push, or rewrite history.

Stop and report BLOCKED (do not improvise) when Docker, disk space, the repository
state or the walkthrough server is unavailable, or when a step needs a decision only
the federation can make (for example, which suspension rule applies).

## Inputs

- The repository checkout at the candidate branch.
- The contract `ci/release_confidence/competition_lifecycle.json`: the required test
  methods (with what each must cover) and the required walkthrough steps.
- After `serve`: `<evidence>/walkthrough/handoff.json` with the server URL, role
  accounts and passwords (disposable), seeded record ids and any seed step that failed.
- Background: `docs/operations/release-runbook.md`, `docs/development/testing.md`, `docs/release/README.md`,
  `docs/workflows/roster-management.md`, `docs/user-guide/competition-workflow.md`.

## Order of work

1. Record `git status`, branch and `git rev-parse HEAD`. Work on a new branch.
2. Implement the lifecycle scenarios (next section) until
   `python3 ci/check_lifecycle_coverage.py --source` passes and the lifecycle lane passes.
3. Commit the test (and any separate fix commits). Every commit changes the candidate:
   all evidence must be produced after your last commit.
4. Run `scripts/ci/run_end_to_end_release.sh all`. It runs every release lane,
   including `lifecycle`, then starts the walkthrough server. Lanes can take over an
   hour. If automated checks fail, triage (see "Triage") and stop before the walkthrough.
5. Perform the browser walkthrough and write `walkthrough.json`.
6. Run `E2E_LEVEL=technical scripts/ci/run_end_to_end_release.sh verify`.
7. Run `scripts/ci/run_end_to_end_release.sh stop`.
8. Write the final report.

## Implementing the lifecycle scenarios

File: `sports_federation_app/tests/test_competition_lifecycle_e2e.py`. Every required
method in the contract must exist with the tags
`post_install`, `-at_install`, `sf_competition_lifecycle`, `sf_release_confidence`.
The contract's `covers` text is the minimum assertion depth for each method.

Iterate quickly against a retained stack:

```bash
export RC_COMPOSE_PROJECT=sf_lifecycle_dev RC_COMPOSE_RETAIN=1
scripts/ci/run_rc_validation.sh prepare      # once: installs the platform
scripts/ci/run_rc_validation.sh lifecycle    # each iteration
scripts/ci/run_rc_validation.sh cleanup      # when finished
```

Drive each step through the same entry point an operator uses, as a user with only
that role (create users with `res.users` and `group_ids`; see
`sports_federation_demo/tests/test_browser_competition_lifecycle.py` for group xmlids):

| Step | Entry point (confirm names in the checkout) |
|---|---|
| Create | `federation.create.competition.wizard` (setup_flow extension: `setup_template`, `workflow_mode`, defaults) then `action_create_competition` |
| Teams | `edition.action_setup_participants()` opens `federation.competition.team.selection.wizard`; set teams; `action_apply` |
| Format | `edition.action_setup_format()` opens the format wizard; `action_apply` (it requires an explicit confirmation) |
| Gamedays | `edition.action_setup_gamedays()` opens `federation.competition.gameday.setup.wizard`; add days; apply |
| Schedule | `edition.action_setup_schedule()` opens `federation.competition.schedule.wizard`; `action_apply` |
| Publish | `schedule.action_submit_for_review()`, then as another user `review.action_approve_schedule()` and `review.action_publish_schedule()` |
| Rosters | season rosters via the Hub operation `edition.action_open_planner_operation("rosters")`; gameday roster via `matchday.action_prepare_lineups()`; crossing out via `sheet.action_set_crossed_out(player_ids)` |
| Open day | `federation.matchday.commands`: `open_matchday(matchday_id)` as the gameday manager |
| Results | court operator with a `federation.court.access` record: `federation.court.commands` `open_match(...)`, then `sync(...)` with `save` and `submit` commands (see `sports_federation_live_workspace/tests/test_commands.py` for the command format); then validator/approver actions on the match per workflow mode |
| Close day | `federation.matchday.commands`: `close_matchday(matchday_id)` without `force` |
| Tables | linked `federation.standing` records are created by the format engine; freeze via `standing.action_freeze()` |
| Finish | `edition.get_competition_planner_data()` must offer the finish actions; `edition.action_open_planner_operation("close_competition")` |
| Public | public competition queries / routes show the competition as Completed |

Fixture rules: create reference data (season, clubs, teams, licensed adult players,
venue, courts, a rule set with `gameday_roster_max_size=14` and
`match_player_max_size=12`) in `setUpClass`. Everything after "Create" must happen
through commands. After every denied action, assert the database is unchanged.
Assert outcomes, not just absence of errors: states, counts, table points, audit or
competition events, public visibility.

If an entry point does not exist, behaves differently from the contract, or needs
data the operator would never enter, that is a finding. Record it; do not work
around it in the test.

## Browser walkthrough

Use Playwright (Chromium) against `base_url` from `handoff.json`. Log in through
`/web/login` with the account for each step's `actor` from the contract (map
`anonymous` to a fresh context with no login). Desktop viewport 1440x900; mobile
viewport 390x844 with touch enabled. Use visible labels and roles to locate controls,
as a person would; do not call JSON-RPC directly to perform a step. You may read
backend state afterwards to confirm an outcome.

Perform the contract's steps in order on one competition. If a seed step failed,
complete it through the UI first and note it. For each step:

- take at least one full-page screenshot after the outcome is visible, saved under
  `<walkthrough_dir>/screenshots/<step_id>-<n>.png`;
- note the observable result in one or two factual sentences;
- check keyboard reachability of the step's primary action and visible focus;
- on failure, record a defect, then continue with later steps if they do not depend
  on it; otherwise mark later steps `blocked` referencing the defect.

For `denied_access`, sign in as `club_representative` and request the other club's
roster, lineup sheet and document URLs directly (ids from the backend). Expect a
refusal page and no change in the database.

Write `<walkthrough_dir>/walkthrough.json`:

```json
{
  "schema_version": 1,
  "commit": "<git rev-parse HEAD>",
  "base_url": "http://127.0.0.1:18069",
  "agent": {"name": "<agent>", "playwright_version": "<version>"},
  "started_at": "<UTC ISO-8601>",
  "finished_at": "<UTC ISO-8601>",
  "steps": [
    {
      "id": "create_competition",
      "status": "passed",
      "actor_login": "organiser@walkthrough.invalid",
      "viewport": "desktop",
      "screenshots": [
        {"path": "screenshots/create_competition-1.png", "sha256": "<sha256 of the file>"}
      ],
      "observations": "Factual description of what was visible.",
      "keyboard": "Primary action reachable by Tab; focus visible.",
      "defect_ids": []
    }
  ],
  "defects": [
    {
      "id": "D1",
      "step_id": "court_scoring",
      "severity": "blocker",
      "classification": "product",
      "status": "open",
      "summary": "One line.",
      "reproduction": "Numbered steps with account, URL and data.",
      "expected": "What the contract requires.",
      "actual": "What happened, with log excerpt or screenshot path."
    }
  ]
}
```

`status` is `passed`, `failed` or `blocked`. `severity` is `blocker` (the
competition cannot be completed or data/access is wrong), `major` (completed only
with a workaround) or `minor`. `classification` is `product`, `test` or
`environment`. A step is `passed` only if the contract's `expect` is fully visible.

## Triage

For every failing lane or scenario, read the lane log under `<evidence>/logs/` and
classify it:

- **product**: the application does something wrong. Record it as a defect with
  reproduction. Fix only under "Authority".
- **test**: your scenario code is wrong (wrong entry point, missing fixture). Fix it.
- **environment**: Docker, network, disk, image build. Retry once; then report BLOCKED.

Never change an assertion to match observed behaviour unless the contract says the
observed behaviour is correct. When unsure, it is a product defect.

## Final report

Reply with:

1. Candidate commit, branch, and the commits you added (hash and subject).
2. Verdict from `verify` (`technically-qualified` or `not-qualified`) and why.
3. A table of lanes and their status from `<evidence>/summary.json`.
4. A table of walkthrough steps: status and one-line observation.
5. Defects, most severe first, with classification and reproduction.
6. What remains for people: the novice sessions in `docs/release/acceptance/novice-usability.md`
   (at least five per role for club representatives, organisers and court operators),
   and the migration rehearsal if no approved backup was supplied.
7. Evidence directory path. Do not paste passwords.
