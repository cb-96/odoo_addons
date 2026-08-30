/** @odoo-module **/

import { registry } from "@web/core/registry";

const tour = registry.category("web_tour.tours");

function navigate(path, description) {
    return {
        content: description,
        trigger: "body",
        run() {
            window.location.assign(path);
        },
        expectUnloadPage: true,
    };
}

function assertPath(path, description) {
    return {
        content: description,
        trigger: "body",
        run() {
            if (window.location.pathname !== path) {
                throw new Error(
                    `Expected public path ${path}, got ${window.location.pathname}`
                );
            }
        },
    };
}

tour.add("public_site_browser_lifecycle", {
    steps: () => [
        assertPath("/competitions", "The canonical competition index is active"),
        {
            content: "The current competition is visible",
            trigger: '.sf-competition-card a[href="/competitions/browser-public-competition"]',
        },
        {
            content: "Search the competition index",
            trigger: "#competition-search",
            run: "edit Browser Public Competition",
        },
        {
            content: "Submit the competition search",
            trigger: 'form button[type="submit"], form button.btn-primary',
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "The filtered competition remains visible",
            trigger: '.sf-competition-card a[href="/competitions/browser-public-competition"]',
            run: "click",
            expectUnloadPage: true,
        },
        assertPath(
            "/competitions/browser-public-competition",
            "The competition detail uses its canonical path"
        ),
        {
            content: "The competition overview renders its public heading",
            trigger: ".sf-competition-hero h1",
        },
        {
            content: "Open the public schedule",
            trigger: '.sf-competition-nav a[href="/competitions/browser-public-competition/schedule"]',
            run: "click",
            expectUnloadPage: true,
        },
        assertPath(
            "/competitions/browser-public-competition/schedule",
            "The schedule route is available"
        ),
        {
            content: "The schedule navigation state is active",
            trigger: '.sf-competition-nav a.active[href$="/schedule"]',
        },
        {
            content: "Open format and standings",
            trigger: '.sf-competition-nav a[href="/competitions/browser-public-competition/format"]',
            run: "click",
            expectUnloadPage: true,
        },
        assertPath(
            "/competitions/browser-public-competition/format",
            "The format route is available"
        ),
        {
            content: "The format navigation state is active",
            trigger: '.sf-competition-nav a.active[href$="/format"]',
        },
        navigate("/tournaments", "Exercise the retired tournament index alias"),
        assertPath(
            "/competitions",
            "The retired tournament index redirects to competitions"
        ),
        navigate("/competitions/archive", "Open the public competition archive"),
        assertPath("/competitions/archive", "The competition archive is available"),
        {
            content: "The archive page renders an archive heading",
            trigger: "main h1",
        },
        navigate("/clubs", "Open the public club directory"),
        assertPath("/clubs", "The public club directory is available"),
        {
            content: "The club directory renders successfully",
            trigger: "main, #wrapwrap",
        },
        navigate("/players", "Open the public player directory"),
        assertPath("/players", "The public player directory is available"),
        {
            content: "The player directory renders successfully",
            trigger: "main, #wrapwrap",
        },
    ],
});
