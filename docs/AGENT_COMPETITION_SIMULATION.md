# AI agent competition simulation

Use the Playwright helper when an agent must exercise a custom competition but
many records require the same already-proven operation.

The rule is simple:

1. The agent performs the operation through the real UI on one or two records.
2. The helper verifies the resulting backend state.
3. The remaining records use the same public Odoo `action_*` method in bounded
   batches under the current browser session.
4. A final `search_read` verifies the whole batch and writes evidence.

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
setup value in `taskInputs`. The helper combines those inputs with the current
Git revision. A changed policy or implementation therefore requires fresh UI
confirmation instead of reusing stale evidence.

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

## Direct JSON routes

For route-owned workflows such as the match-day operations board, use
`runner.confirmAndComplete(...)`. Let `uiAction` prove the first records, let
`fastAction` call the existing JSON route through `rpc.call(route, params)`, and
let `verifyBatch` fetch the operations workspace once and validate all remaining
matches. This keeps controller scope checks in place while avoiding repeated
page navigation.

## Evidence and failure behavior

The evidence file records:

- task key and fingerprint;
- Git revision and task inputs;
- records confirmed through the UI;
- records completed through the accelerated path;
- pass/fail status and failure message.

The confirmation is stored before accelerated execution. A backend validation
failure is not retried or hidden. The run is marked failed and the original
error is raised so the agent can inspect the custom setup.

## Run the helper tests

```bash
node --test scripts/playwright/competition_simulation_runner.test.mjs
```
