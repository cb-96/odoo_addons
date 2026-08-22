{
    "name": "Match-Day Operations",
    "version": "19.0.1.1.0",
    "category": "Sports",
    "summary": "Live court control, delays and operational incidents",
    "author": "Sports Federation",
    "license": "LGPL-3",
    "depends": ["sports_federation_schedule_approval"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/matchday_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
