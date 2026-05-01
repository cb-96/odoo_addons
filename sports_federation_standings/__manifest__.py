{
    "name": "Sports Federation Standings",
    "version": "19.0.1.1.0",
    "category": "Sports",
    "summary": "Compute and store standings for tournament stages/groups",
    "description": """
        Compute and store standings for tournament stages/groups
        using configurable scoring and tie-break rules.
    """,
    "author": "Sports Federation",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "sports_federation_tournament",
        "sports_federation_rules",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/standing_views.xml",
        "views/tournament_views_inherit.xml",
        "views/menu_views.xml",
    ],
    "demo": [],
    "application": False,
    "installable": True,
    "auto_install": False,
}
