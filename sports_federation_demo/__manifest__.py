{
    "name": "Sports Federation Demo Data",
    "version": "19.0.1.0.0",
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
    ],
    "data": [],
    "demo": [
        "demo/demo_federation_data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "sequence": 90,
}
