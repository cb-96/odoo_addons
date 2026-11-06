{
    "name": "Federation Native Accounting",
    "version": "19.0.1.1.1",
    "license": "LGPL-3",
    "depends": ["sports_federation_finance_bridge", "account_payment"],
    "data": ["views/accounting.xml"],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
