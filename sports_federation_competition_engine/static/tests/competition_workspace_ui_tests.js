/** @odoo-module **/

import {
    formatPlannerSelectionSummary,
    isPlannerValidationConfirmable,
    isPlannerBusyState,
    shouldHandlePlannerEscape,
    resolveWorkspaceSections,
    resolveWorkspaceMode,
} from "@sports_federation_competition_engine/client_actions/competition_workspace/competition_workspace";

QUnit.module("sports_federation_competition_engine > competition workspace ui");

QUnit.test("planner busy helper reflects write and loading states", function (assert) {
    assert.strictEqual(isPlannerBusyState({}), false, "Idle state is not busy");
    assert.strictEqual(
        isPlannerBusyState({ saving: true, plannerLoading: false, publishing: false }),
        true,
        "Saving state is busy"
    );
    assert.strictEqual(
        isPlannerBusyState({ saving: false, plannerLoading: true, publishing: false }),
        true,
        "Planner loading state is busy"
    );
    assert.strictEqual(
        isPlannerBusyState({ saving: false, plannerLoading: false, publishing: true }),
        true,
        "Publishing state is busy"
    );
});

QUnit.test("planner validation confirm helper requires a planned gameday", function (assert) {
    assert.strictEqual(
        isPlannerValidationConfirmable({ currentGamedayId: false, currentPlannerState: "planned" }),
        false,
        "Missing gameday cannot be confirmed"
    );
    assert.strictEqual(
        isPlannerValidationConfirmable({ currentGamedayId: 12, currentPlannerState: "draft" }),
        false,
        "Draft gamedays cannot be confirmed"
    );
    assert.strictEqual(
        isPlannerValidationConfirmable({ currentGamedayId: 12, currentPlannerState: "planned" }),
        true,
        "Planned gamedays can be confirmed when idle"
    );
    assert.strictEqual(
        isPlannerValidationConfirmable({
            currentGamedayId: 12,
            currentPlannerState: "planned",
            publishing: true,
        }),
        false,
        "Busy planners cannot confirm validation"
    );
});

QUnit.test("planner selection summary helper is explicit", function (assert) {
    assert.strictEqual(
        formatPlannerSelectionSummary({ selectedCount: 0, unscheduledCount: 0, assignedCount: 0 }),
        "No matches selected.",
        "Empty selection has a clear summary"
    );
    assert.strictEqual(
        formatPlannerSelectionSummary({ selectedCount: 3, unscheduledCount: 2, assignedCount: 1 }),
        "3 selected: 2 unscheduled and 1 assigned.",
        "Mixed selection includes unscheduled and assigned counts"
    );
});

QUnit.test("planner escape helper only clears when relevant", function (assert) {
    assert.strictEqual(
        shouldHandlePlannerEscape({
            key: "Escape",
            activeSection: "planner",
            selectedCount: 1,
            hasPendingValidation: false,
        }),
        true,
        "Escape clears when planner has a selection"
    );
    assert.strictEqual(
        shouldHandlePlannerEscape({
            key: "Escape",
            activeSection: "planner",
            selectedCount: 0,
            hasPendingValidation: true,
        }),
        true,
        "Escape clears pending validation in planner"
    );
    assert.strictEqual(
        shouldHandlePlannerEscape({
            key: "Enter",
            activeSection: "planner",
            selectedCount: 1,
            hasPendingValidation: true,
        }),
        false,
        "Non-escape keys do not trigger clear behavior"
    );
    assert.strictEqual(
        shouldHandlePlannerEscape({
            key: "Escape",
            activeSection: "teams",
            selectedCount: 1,
            hasPendingValidation: true,
        }),
        false,
        "Escape outside planner section does not clear planner state"
    );
});

QUnit.test("workspace journey unlocks steps progressively", function (assert) {
    const initial = resolveWorkspaceSections({ competition: { id: 10 }, division: false });
    assert.strictEqual(initial.find((step) => step.key === "overview").disabled, false);
    assert.strictEqual(initial.find((step) => step.key === "teams").disabled, true);

    const planning = resolveWorkspaceSections({
        competition: { id: 10 },
        division: {
            id: 20,
            entries_locked: true,
            match_count: 12,
            gameday_count: 2,
            slot_count: 12,
            unscheduled_match_count: 0,
            workspace_state: "planning",
        },
    });
    assert.strictEqual(planning.find((step) => step.key === "planner").disabled, false);
    assert.strictEqual(planning.find((step) => step.key === "planner").complete, true);
    assert.strictEqual(planning.find((step) => step.key === "publish").complete, false);
});

QUnit.test("workspace modes split creation from day planning", function (assert) {
    const division = { id: 20, entries_locked: true, match_count: 8, gameday_count: 2, slot_count: 16, unscheduled_match_count: 0 };
    assert.deepEqual(resolveWorkspaceSections({ competition: { id: 10 }, division, mode: "creation" }).map((item) => item.key), ["overview", "teams", "rounds"], "Tournament Creation exposes only pre-event structure tasks");
    assert.deepEqual(resolveWorkspaceSections({ competition: { id: 10 }, division, mode: "planner" }).map((item) => item.key), ["gamedays", "planner", "publish"], "Schedule Planner exposes only gameday and assignment tasks");
    assert.strictEqual(resolveWorkspaceMode("sports_federation_competition_engine.tournament_creation"), "creation");
    assert.strictEqual(resolveWorkspaceMode("sports_federation_competition_engine.schedule_planner"), "planner");
});
