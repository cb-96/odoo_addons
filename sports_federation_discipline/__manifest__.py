{
    "name": "Sports Federation Discipline",
    "version": "19.0.1.1.0",
    "category": "Sports",
    "summary": "Incidents, cases, sanctions, and suspensions management",
    "description": """
        Implements incidents, disciplinary cases, sanctions, and suspensions
        for sports federation discipline management.
    """,
    "author": "Sports Federation",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "sports_federation_base",
        "sports_federation_people",
        "sports_federation_tournament",
        "sports_federation_officiating",
        "mail",
    ],
    "data": [
        "security/discipline_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "views/incident_views.xml",
        "views/disciplinary_case_views.xml",
        "views/sanction_views.xml",
        "views/suspension_views.xml",
        "views/player_views_inherit.xml",
        "views/match_views_inherit.xml",
        "views/menu_views.xml",
    ],
    "demo": [],
    "application": False,
    "installable": True,
    "auto_install": False,
}
