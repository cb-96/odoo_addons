/** @odoo-module **/

import { registry } from "@web/core/registry";

const tour = registry.category("web_tour.tours");

function openMenu(xmlid, description) {
    return {
        content: description,
        trigger: `[data-menu-xmlid="${xmlid}"]`,
        run: "click",
    };
}

function assertView(model, description) {
    return {
        content: description,
        trigger: `.o_action_manager [data-res-model="${model}"], .o_action_manager .o_list_view, .o_action_manager .o_kanban_view`,
    };
}

tour.add("full_competition_lifecycle", {
    url: "/odoo",
    steps: () => [
        assertView("federation.competition.edition", "The competition overview is available"),
        openMenu("sports_federation_registration.menu_registration_desk", "Open the registration desk"),
        assertView("federation.registration.window", "Registration windows are available"),
        openMenu("sports_federation_format.menu_format_studio", "Open the format studio"),
        assertView("federation.competition.structure", "Competition structures are available"),
        openMenu("sports_federation_calendar.menu_calendar_planner", "Open the calendar planner"),
        assertView("federation.competition.matchday", "Competition matchdays are available"),
        openMenu("sports_federation_scheduling.menu_schedule_planner_competition", "Open the schedule planner"),
        assertView("federation.schedule", "Working schedules are available"),
        openMenu("sports_federation_schedule_approval.menu_schedule_review_queue", "Open the schedule review queue"),
        assertView("federation.schedule.review", "Schedule reviews are available"),
        openMenu("sports_federation_matchday.menu_matchday_control", "Open match-day control"),
        assertView("federation.matchday.session", "Match-day sessions are available"),
        openMenu("sports_federation_standings.menu_federation_standings", "Open official standings"),
        assertView("federation.standing", "Official standings are available"),
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
