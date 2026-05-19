{
    "name": "Sports Federation Rosters",
    "version": "19.0.1.5.0",
    "category": "Sports",
    "summary": "Season/competition-bound team rosters and match sheets",
    "description": """
        Implements season/competition-bound team rosters and match sheets
        that connect players to operational competition use.
    """,
    "author": "Sports Federation",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "sports_federation_base",
        "sports_federation_people",
        "sports_federation_tournament",
        "sports_federation_rules",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/team_roster_views.xml",
        "views/match_sheet_views.xml",
        "views/tournament_participant_views_inherit.xml",
        "views/team_views_inherit.xml",
        "views/player_views_inherit.xml",
        "views/match_views_inherit.xml",
        "views/menu_views.xml",
    ],
    "demo": [],
    "application": False,
    "installable": True,
    "auto_install": False,
}
