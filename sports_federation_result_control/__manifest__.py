{
    "name": "Sports Federation Result Control",
    "version": "19.0.1.1.0",
    "category": "Sports",
    "summary": "Result lifecycle control and approval workflow for matches",
    "description": "Result submission, verification, approval, and control workflows for matches.",
    "author": "Sports Federation",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "sports_federation_tournament",
        "mail",
    ],
    "data": [
        "security/result_control_security.xml",
        "security/ir.model.access.csv",
        "views/match_views_inherit.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "sequence": 30,
}
