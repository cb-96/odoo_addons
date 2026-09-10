# Sports Federation

This is the single supported installation entry point for the production
federation platform.

The addon deliberately contains no models, views, security rules, controllers,
or business logic. Existing focused addons remain the implementation units so
model names, tables, XML IDs, access rules, migrations, and installed-database
upgrade paths remain stable.

## Install

```bash
odoo -d DATABASE -i sports_federation_app --stop-after-init
```

Install `sports_federation_demo` separately only in development or demonstration
databases.
