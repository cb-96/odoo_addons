/** @odoo-module **/

import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("competition_planner_intent", {
    steps: () => [
        {
            content: "A returning operator can identify the current action",
            trigger: ".o_competition_planner [data-planner-current-action='true']",
        },
        {
            content: "The current action has one prominent direct action",
            trigger: ".o_competition_planner [data-planner-primary-action='true']",
        },
        {
            content: "Future areas are described as not ready rather than locked",
            trigger: ".o_competition_journey_step.is-blocked .fa-clock-o",
        },
        {
            content: "Every visible blocker is directly actionable",
            trigger: ".o_competition_planner [data-planner-issue]",
        },
        {
            content: "The direct action remains keyboard reachable",
            trigger: ".o_competition_planner [data-planner-primary-action='true']",
            run() {
                const action = document.querySelector(
                    ".o_competition_planner [data-planner-primary-action='true']"
                );
                action.focus();
                if (document.activeElement !== action) {
                    throw new Error("The planner primary action did not receive focus.");
                }
            },
        },
    ],
});
