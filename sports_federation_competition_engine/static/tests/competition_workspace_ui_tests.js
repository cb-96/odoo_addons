/** @odoo-module **/

import {
    formatPlannerSelectionSummary,
    isPlannerValidationConfirmable,
    isPlannerBusyState,
    shouldHandlePlannerEscape,
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
