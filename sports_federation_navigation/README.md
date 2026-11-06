# Sports Federation Navigation

Owner: Federation Platform Team

This integration addon is loaded after the domain menus and is the single map of the Federation backend menu: every name, parent, sequence and group assignment for the addons it depends on lives in `views/navigation.xml`. Ordinary managers see eleven entries with one Competition Hub entry. Planning tools, raw records, specialist queues and configuration are opt-in through Advanced Federation Tools or an owning specialist group; audit and technical records sit under **Administration > System**, which is only shown in developer mode. The full map and its rules are in [backend navigation](../docs/user-guide/backend-navigation.md).

The addon changes only `ir.ui.menu` names, parents, ordering, and group discoverability. It does not own business models, actions, ACLs, record rules, controllers, or migrations. Contextual deep links and stable action XML IDs remain in the domain addons.

Menu group restrictions use Odoo 19's `ir.ui.menu.group_ids` field and are always written with `(6, 0, ...)`, so an upgrade replaces groups linked by earlier versions instead of adding to them. The manifest directly depends on every addon that owns a menu or group XML ID referenced by this integration, so a fresh install loads those records before `views/navigation.xml`.
