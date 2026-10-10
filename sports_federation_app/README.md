# Sports Federation

This is the single supported installation entry point for the production federation platform.

Domain addons remain the implementation units so model names, tables, XML IDs, permissions, migrations, and installed-database upgrade paths stay stable. The aggregate addon remains dependency-only. `sports_federation_navigation` applies the supported ordinary-versus-advanced menu contract after its domain dependencies exist; it does not remove actions or change model access.

## Navigation contract

Ordinary competition operators use:

```text
Federation > Competitions > Competition Hub
```

Raw competition, specialist, publishing, assurance, reporting, audit, recovery, and administration menus are opt-in through `sports_federation_base.group_federation_advanced_operator` or an owning specialist group. Contextual actions remain available regardless of menu discoverability.

## Install

```bash
odoo -d DATABASE -i sports_federation_app --stop-after-init
```

Install `sports_federation_demo` separately only in development or demonstration databases.
