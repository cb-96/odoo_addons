{
    "name": "Sports Federation Demo Data",
    "version": "19.0.1.0.6",
    "category": "Sports",
    "summary": "Deterministic demo-data pack for end-to-end federation walkthroughs",
    "description": """
Provides a self-contained, deterministic set of demo records that exercise the
full federation workflow: clubs, teams, players, seasons, registrations,
competitions, tournaments, rosters, match sheets, and completed matches.

Install this module with demo data enabled to populate a development or
demonstration database with realistic walkthrough content.
""",
    "author": "Sports Federation",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "sports_federation_base",
        "sports_federation_rules",
        "sports_federation_people",
        "sports_federation_tournament",
        "sports_federation_rosters",
        "sports_federation_standings",
        "sports_federation_compliance",
        "sports_federation_discipline",
        "sports_federation_notifications",
        "sports_federation_competition_core",
        "sports_federation_registration",
        "sports_federation_format",
        "sports_federation_venues",
        "sports_federation_calendar",
        "sports_federation_scheduling",
        "sports_federation_schedule_approval",
        "sports_federation_matchday",
        "sports_federation_officiating",
        "sports_federation_result_control",
        "sports_federation_portal",
        "sports_federation_public_site",
        "web_tour",
    ],
    "data": [],
    "assets": {
        "web.assets_tests": [
            "sports_federation_demo/static/tests/tours/full_competition_lifecycle_tour.js",
        ],
    },
    "demo": [
        "demo/demo_federation_data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "sequence": 90,
}
