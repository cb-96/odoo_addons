{
    "name": "Competition Format",
    "version": "19.0.4.0.0",
    "category": "Sports",
    "summary": "Versioned competition structures, stages, progression and fixtures",
    "author": "Sports Federation",
    "license": "LGPL-3",
    "depends": [
        "sports_federation_registration",
        "sports_federation_result_control",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/format_views.xml",
        "views/stage_graph_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
