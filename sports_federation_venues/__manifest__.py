{
    "name": "Sports Federation Venues",
    "version": "19.0.1.1.0",
    "category": "Sports",
    "summary": "Manage venues and playing areas for tournaments and matches",
    "description": """
        Manage venues and playing areas and integrate them
        into tournaments and matches.
    """,
    "author": "Sports Federation",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "sports_federation_base",
        "sports_federation_tournament",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/venue_views.xml",
        "views/round_views_inherit.xml",
        "views/tournament_views_inherit.xml",
        "views/match_views_inherit.xml",
        "views/menu_views.xml",
    ],
    "demo": [],
    "application": False,
    "installable": True,
    "auto_install": False,
}
