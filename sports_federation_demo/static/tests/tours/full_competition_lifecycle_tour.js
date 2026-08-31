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

function assertBackendView(description) {
    return {
        content: description,
        trigger: ".o_action_manager .o_form_view, .o_action_manager .o_list_renderer, .o_action_manager .o_kanban_renderer, .o_action_manager .o_calendar_renderer",
    };
}

// Navigate through actions rather than menu nodes. Menu nodes can be absent from
// the DOM when an app section is collapsed. Odoo 19 list, kanban, and calendar
// actions expose renderer classes rather than the historical *_view wrappers.
tour.add("full_competition_lifecycle", {
    steps: () => [
        {
            content: "The competition overview form is ready",
            trigger: '.o_form_view .o_field_widget[name="workflow_next_action"]',
        },
        openAction(
            "sports_federation_registration.action_registration_desk",
            "Open the registration desk"
        ),
        assertBackendView("Registration windows are available"),
        openAction(
            "sports_federation_format.action_format_studio",
            "Open the format studio"
        ),
        assertBackendView("Competition structures are available"),
        openAction(
            "sports_federation_calendar.action_calendar_planner",
            "Open the calendar planner"
        ),
        assertBackendView("Competition match days are available"),
        openAction(
            "sports_federation_scheduling.action_schedule_planner_competition",
            "Open the schedule planner"
        ),
        assertBackendView("Working schedules are available"),
        openAction(
            "sports_federation_schedule_approval.action_schedule_review_queue",
            "Open the schedule review queue"
        ),
        assertBackendView("Schedule reviews are available"),
        openAction(
            "sports_federation_matchday.action_matchday_control",
            "Open match-day control"
        ),
        assertBackendView("Published match days are available"),
        openAction(
            "sports_federation_standings.action_federation_standing",
            "Open official standings"
        ),
        assertBackendView("Official standings are available"),
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
            trigger: 'a[href^="/competitions/"], .sf-competition-card, .o_public_competition_card',
        },
    ],
});
