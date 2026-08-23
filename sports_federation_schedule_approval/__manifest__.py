{
    "name": "Schedule Approval",
    "version": "19.0.2.0.0",
    "category": "Sports",
    "summary": "Independent review, approval and immutable publication snapshots",
    "author": "Sports Federation",
    "license": "LGPL-3",
    "depends": ["sports_federation_scheduling"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/approval_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
