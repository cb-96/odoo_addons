/** @odoo-module **/

import { registry } from "@web/core/registry";

const tour = registry.category("web_tour.tours");

function openAction(xmlid, description) {
    return {
        content: description,
        trigger: "body",
        run() {
            window.location.assign(`/odoo/action-${xmlid}`);
        },
        expectUnloadPage: true,
    };
}

function assertView(model, description) {
    return {
        content: description,
        trigger: `.o_action_manager [data-res-model="${model}"], .o_action_manager .o_list_view, .o_action_manager .o_pivot_view`,
    };
}

// The HttpCase starts this tour directly on a deterministic draft finance
// event. The tour performs the irreversible state transitions in the browser,
// then walks the main Finance Bridge operator surfaces.
tour.add("finance_bridge_browser_lifecycle", {
    steps: () => [
        {
            content: "The finance event form is loaded",
            trigger: '.o_form_view [name="name"]',
        },
        {
            content: "Confirm the draft finance event",
            trigger: 'button[name="action_confirm"]',
            run: "click",
        },
        {
            content: "The event is confirmed and can be settled",
            trigger: 'button[name="action_settle"]',
            run: "click",
        },
        {
            content: "Accept the settlement confirmation",
            trigger: ".modal-dialog .btn-primary",
            run: "click",
        },
        {
            content: "The finance event reached the settled state",
            trigger: '.o_statusbar_status button.active[data-value="settled"], .o_statusbar_status .o_arrow_button_current[data-value="settled"]',
        },
        openAction(
            "sports_federation_finance_bridge.action_federation_fee_type",
            "Open the fee type catalogue"
        ),
        assertView("federation.fee.type", "Fee types are available"),
        openAction(
            "sports_federation_finance_bridge.action_federation_fee_schedule",
            "Open fee schedules"
        ),
        assertView("federation.fee.schedule", "Fee schedules are available"),
        openAction(
            "sports_federation_finance_bridge.action_federation_season_budget",
            "Open season budgets"
        ),
        assertView("federation.season.budget", "Season budgets are available"),
        openAction(
            "sports_federation_finance_bridge.action_federation_finance_event",
            "Return to finance events"
        ),
        assertView("federation.finance.event", "Finance events remain available after settlement"),
        {
            content: "The settled browser-tour event is listed",
            trigger: '.o_list_view .o_data_row:contains("Browser Finance Lifecycle")',
        },
    ],
});
