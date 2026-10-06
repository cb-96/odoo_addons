# AI agent competition simulation

Use the Playwright helper when an agent must exercise a custom competition but
many records require the same already-proven operation.

The rule is simple:

1. The agent performs the operation through the real UI on one or two records.
2. The helper verifies the resulting backend state.
3. The remaining records use the same public Odoo `action_*` method in bounded
   batches under the current browser session.
4. The helper verifies every accelerated batch and writes evidence.

This preserves model validation, role checks, workflow transitions, audit hooks,
and transaction behavior. It only removes repetitive browser interaction. It
does not write workflow state fields directly and does not use `sudo()`.

## Minimal Playwright usage

```javascript
import { test } from "@playwright/test";
import { ConfirmedTaskRunner } from "../scripts/playwright/competition_simulation_runner.mjs";

test("custom competition", async ({ page }) => {
    await page.goto(process.env.ODOO_URL);
    // Supply the normal login/setup used by the agent before this point.

    const runner = new ConfirmedTaskRunner({
        page,
        implementationRevision: process.env.GIT_COMMIT,
        evidencePath: "artifacts/agent-simulation/custom-competition.json",
        confirmationRuns: 2,
    });

    await runner.confirmRecordAction({
        key: "submit-entered-results",
        model: "federation.match",
        recordIds: matchIds,
        actionMethod: "action_submit_result",
        stateField: "result_state",
        sourceStates: ["draft", "corrected"],
        // In simple workflow mode submission may auto-verify or auto-approve.
        expectedState: ["submitted", "verified", "approved"],
        taskInputs: {
            workflowMode,
            resultVerificationRequired,
            resultApprovalRequired,
        },
        uiAction: async ({ id }) => {
            await page.goto(`/odoo/federation.match/${id}`);
            await page.getByRole("button", { name: "Submit Result" }).click();
        },
    });
});
```

Use a stable task key for one behavior, and put every behavior-changing custom
setup value in `taskInputs`. `sourceStates` must list the allowed pre-action
states, and `expectedState` must list the state(s) that mean the task is already
complete. The helper combines those values, the target record IDs, and the
current Git revision in its fingerprint. A changed target set, policy, state,
or implementation therefore requires fresh UI confirmation instead of
reusing stale evidence.

## Task design

Good candidates for accelerated completion are homogeneous record actions:

- submit, verify, or approve many prepared results;
- confirm many equivalent referee assignments;
- prepare or start equivalent stages;
- freeze standings after every result prerequisite has been met.

Keep unique or decision-heavy work in Playwright:

- competition, division, participant, format, calendar, and schedule design;
- warnings and exception handling;
- request-changes and contest paths;
- publication replacement and destructive recovery;
- any operation where records are not equivalent.

Do not combine different policy settings, roles, source states, or expected
outcomes under one task key. Split those into separate confirmed tasks.
For direct `confirmAndComplete(...)` calls, provide `isItemComplete(item,
context)`. It must inspect persisted state and return `true` only when that item
already has the requested outcome. The runner uses it to exclude completed
items before confirmation and to reconcile a failed partial batch safely.

## Direct JSON routes

For route-owned workflows such as the match-day operations board, use
`runner.confirmAndComplete(...)`. Let `isItemComplete` inspect the persisted
match-day state, `uiAction` prove the first records, `fastAction` call the
existing JSON route through `rpc.call(route, params)`, and `verifyBatch` fetch
the operations workspace once and validate all remaining matches. After each
successfully verified route chunk, call `reportProgress(itemKeys)` from the
`fastAction` context so progress is durable if a later chunk fails. This keeps
controller scope checks in place while avoiding repeated page navigation.

## Evidence and failure behavior

The evidence file records:

- task key and fingerprint;
- Git revision and task inputs;
- target IDs and items already complete at the start of the run;
- records confirmed through the UI;
- records completed through the accelerated path;
- pass/fail status and failure message.

The confirmation is stored before accelerated execution. A backend validation
failure is not retried or hidden within that run: it is marked failed and the
original error is raised so the agent can inspect the custom setup. Verified
chunk progress is persisted. On a later invocation, `confirmRecordAction(...)`
re-reads current states, skips records already at an expected state, and only
processes records still in an allowed source state. The changed pending set
requires fresh UI confirmation. Generic `confirmAndComplete(...)` tasks get
the same retry behavior only when their `isItemComplete` callback accurately
reflects persisted state.

## Run the helper tests

```bash
node --test scripts/playwright/competition_simulation_runner.test.mjs
```
