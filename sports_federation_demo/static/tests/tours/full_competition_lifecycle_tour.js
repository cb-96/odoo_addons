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

// The ordinary lifecycle intentionally starts and resumes from one entry. Raw
// registration, format, calendar, schedule and approval actions are covered by
// their owning addon tests and remain available through contextual deep links.
tour.add("full_competition_lifecycle", {
    steps: () => [
        openAction(
            "sports_federation_setup_flow.action_competition_setup_home",
            "Open the canonical competition workspace"
        ),
        {
            content: "Competition rows expose the resumable workspace",
            trigger: ".o_list_renderer button[name='action_open_competition_planner']",
        },
        {
            content: "Resume without choosing a technical module",
            trigger: ".o_list_renderer button[name='action_open_competition_planner']",
            run: "click",
        },
        {
            content: "The simplified competition workspace is ready",
            trigger: ".o_competition_planner [data-planner-primary-action='true']",
        },
        {
            content: "Unified readiness covers planning and operations",
            trigger: ".o_competition_planner [data-planner-unified-readiness='true']",
        },
        {
            content: "Exactly one next action is promoted",
            trigger: ".o_competition_planner [data-planner-primary-projection='true']",
            run() {
                const actions = document.querySelectorAll(
                    ".o_competition_planner [data-planner-primary-action='true']"
                );
                if (actions.length !== 1) {
                    throw new Error(`Expected one primary action, found ${actions.length}.`);
                }
            },
        },
        {
            content: "Open the public competition index",
            trigger: "body",
            run() {
                window.location.assign("/competitions");
            },
            expectUnloadPage: true,
        },
        {
            content: "The public competition index renders successfully",
            trigger: "main, #wrapwrap",
        },
        {
            content: "The canonical competition route remains active",
            trigger: "main h1, #wrapwrap h1",
        },
    ],
});
