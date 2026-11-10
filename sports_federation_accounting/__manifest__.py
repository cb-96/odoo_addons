{
    "name": "Federation Native Accounting",
    "version": "19.0.1.3.0",
    "license": "LGPL-3",
    "depends": [
        "sports_federation_finance_bridge",
        "sports_federation_portal",
        "account_payment",
    ],
    "data": [
        "views/accounting.xml",
        "views/club_season_invoice_views.xml",
        "views/club_invoice_portal_templates.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
