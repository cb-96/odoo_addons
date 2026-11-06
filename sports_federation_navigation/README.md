# Sports Federation Navigation

Owner: Federation Platform Team

This integration addon is loaded after the domain menus and applies the supported product navigation contract. Ordinary competition operators receive one Competition Hub entry. Duplicate, raw-model, specialist, audit, recovery, and technical menus are opt-in through Advanced Federation Tools or an owning specialist group.

The addon changes only `ir.ui.menu` names, parents, ordering, and group discoverability. It does not own business models, actions, ACLs, record rules, controllers, or migrations. Contextual deep links and stable action XML IDs remain in the domain addons.

Menu group restrictions use Odoo 19's `ir.ui.menu.group_ids` field. The manifest directly depends on every addon that owns a menu or group XML ID referenced by this integration, so a fresh install loads those records before `views/navigation.xml`.
