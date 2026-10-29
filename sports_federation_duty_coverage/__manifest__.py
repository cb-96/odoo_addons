{
    "name": "Sports Federation Duty Coverage",
    "version": "19.0.1.0.0",
    "category": "Sports",
    "summary": (
        "Schedule-linked coverage, individual acceptance, "
        "attendance and governed replacements"
    ),
    "license": "LGPL-3",
    "depends": [
        "sports_federation_portal",
        "sports_federation_reporting",
        "sports_federation_setup_flow",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/coverage_cron.xml",
        "views/coverage_views.xml",
        "views/portal_templates.xml",
    ],
    "installable": True,
    "application": False,
}
