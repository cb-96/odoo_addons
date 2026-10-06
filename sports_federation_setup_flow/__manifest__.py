{
    "name": "Competition Setup Flow",
    "version": "19.0.3.0.0",
    "category": "Sports",
    "summary": "Continuous and resumable competition setup",
    "author": "Sports Federation",
    "license": "LGPL-3",
    "depends": [
        "sports_federation_competition_core",
        "sports_federation_registration",
        "sports_federation_format",
        "sports_federation_calendar",
        "sports_federation_scheduling",
        "sports_federation_schedule_approval",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/competition_setup_views.xml",
        "views/gameday_setup_wizard_views.xml",
        "views/menu.xml",
        "views/setup_consolidation_views.xml",
        "views/setup_journey_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sports_federation_setup_flow/static/src/competition_planner/planner.js",
            "sports_federation_setup_flow/static/src/competition_planner/planner.xml",
            "sports_federation_setup_flow/static/src/competition_planner/planner.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
