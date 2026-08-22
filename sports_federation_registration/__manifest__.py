{
    "name": "Competition Registration",
    "version": "19.0.1.1.0",
    "category": "Sports",
    "summary": "Role-separated registration desk and finalized participant sets",
    "author": "Sports Federation",
    "license": "LGPL-3",
    "depends": ["sports_federation_competition_core"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "wizards/create_competition_wizard_views.xml",
        "views/registration_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
