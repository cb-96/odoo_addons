{
    "name": "Sports Federation Tournament",
    "version": "19.0.1.0.0",
    "category": "Sports",
    "summary": "Tournaments, stages, groups, participants, and matches",
    "description": """
Tournament structure and lifecycle management for the sports federation suite.

Provides competitions, tournaments, stages, groups, participants, and matches,
with rule-set support and workflow state management.
""",
    "author": "Sports Federation",
    "website": "",
    "license": "LGPL-3",
    "depends": ["sports_federation_base", "sports_federation_rules"],
    "data": [
        "security/ir.model.access.csv",
        "views/federation_tournament_participant_views.xml",
        "views/federation_match_views.xml",
        "views/federation_tournament_round_views.xml",
        "views/federation_tournament_group_views.xml",
        "views/federation_tournament_stage_views.xml",
        "views/federation_tournament_views.xml",
        "views/federation_competition_edition_views.xml",
        "views/federation_competition_views.xml",
        "views/federation_season_registration_views_inherit.xml",
        "views/federation_season_views_inherit.xml",
        "views/menu_items.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "sequence": 20,
}
