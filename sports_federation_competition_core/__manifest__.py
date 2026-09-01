{
    "name": "Competition Core",
    "version": "19.0.1.4.0",
    "category": "Sports",
    "summary": "Stable competition lifecycle, role ownership, and domain events",
    "author": "Sports Federation",
    "license": "LGPL-3",
    "depends": ["sports_federation_base", "sports_federation_tournament"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/competition_edition_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
