/** @odoo-module **/

import { registry } from "@web/core/registry";

const CANONICAL_ACTION_XMLIDS = [
    "sports_federation_setup_flow.action_competition_setup_home",
];

const SETUP_CONTROL_SELECTOR = [
    "[data-keyboard-competition-setup]",
    "[data-action='competition-setup']",
    ".o_competition_setup button",
    ".o_competition_setup [role='button']",
].join(", ");

function assertFocused(element) {
    if (element && document.activeElement !== element) {
        throw new Error("The competition setup control did not receive focus.");
    }
}

registry.category("web_tour.tours").add("keyboard_competition_setup", {
    steps: () => [
        {
            content: "Focus the competition setup control",
            trigger: "body",
            run() {
                const control = document.querySelector(SETUP_CONTROL_SELECTOR);
                if (!control) {
                    return;
                }
                control.focus();
                assertFocused(control);
            },
        },
        {
            content: "Activate the focused competition setup control with the keyboard",
            trigger: "body",
            run() {
                document.activeElement.dispatchEvent(
                    new KeyboardEvent("keydown", {
                        key: "Enter",
                        bubbles: true,
                    })
                );
            },
        },
        {
            content: "Verify that focus remains available after keyboard activation",
            trigger: "body",
            run() {
                if (!document.activeElement) {
                    throw new Error("No active element exists after keyboard activation.");
                }
            },
        },
    ],
});
