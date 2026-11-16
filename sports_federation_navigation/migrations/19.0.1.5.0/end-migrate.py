"""Remove what retired addons left behind in the database.

An addon whose source is deleted while it is still installed cannot be
uninstalled by Odoo any more: its menus, actions, views, rules and tables stay
in the database. Menus then open actions on models that no longer exist
("KeyError: 'federation.person.membership'"), and inherited views can show
fields that are gone.

This runs at the end of the upgrade, when every installed addon is loaded, and
removes only records that belong exclusively to a retired addon (by external
identifier). Records that another addon also declares, such as an inherited
model, are kept; only the retired addon's own fields are dropped from it.
Afterwards any menu whose window action points at a model that is no longer
registered is removed as well, whatever addon it came from.

Idempotent: a second run finds nothing to do.
"""

import logging

from psycopg2 import sql

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

RETIRED_ADDONS = (
    "sports_federation_member_services",
    "sports_federation_competition_engine",
)

# Deleted first, in this order, so that nothing still points at the models and
# fields removed afterwards.
ORDERED_MODELS = (
    "ir.ui.menu",
    "ir.cron",
    "ir.actions.act_window.view",
    "ir.actions.act_window",
    "ir.actions.server",
    "ir.actions.client",
    "ir.actions.act_url",
    "ir.actions.report",
    "ir.ui.view",
    "ir.rule",
    "ir.model.access",
)
SCHEMA_MODELS = (
    "ir.model.constraint",
    "ir.model.relation",
    "ir.model.fields.selection",
    "ir.model.fields",
    "ir.model",
)


def _code_present(name):
    try:
        from odoo.modules.module import get_module_path

        return bool(get_module_path(name, display_warning=False))
    except Exception:  # API differences between Odoo versions
        return False


def _owned(cr, module, model):
    """IDs of ``model`` records declared by ``module`` and by no other addon."""
    cr.execute(
        """
        SELECT d.res_id
          FROM ir_model_data d
         WHERE d.module = %s AND d.model = %s AND d.res_id IS NOT NULL
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_data o
                 WHERE o.model = d.model AND o.res_id = d.res_id
                   AND o.module <> d.module
           )
        """,
        (module, model),
    )
    return [row[0] for row in cr.fetchall()]


def _unlink(env, model, ids):
    if not ids or model not in env:
        return 0
    records = env[model].browse(ids).exists()
    removed = 0
    for record in records:
        try:
            with env.cr.savepoint():
                record.with_context(_force_unlink=True).unlink()
            removed += 1
        except Exception as error:  # keep going; report what is left
            _logger.warning("Could not remove %s %s: %s", model, record.id, error)
            if "active" in record._fields:
                with env.cr.savepoint():
                    record.write({"active": False})
    return removed


def _table_exists(cr, table):
    cr.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
    return cr.fetchone()[0]


# Columns every Odoo table has; never dropped one by one.
MAGIC_COLUMNS = frozenset(
    ("id", "create_uid", "create_date", "write_uid", "write_date", "display_name")
)


def _drop_fields(env, module):
    """Drop the columns the retired addon added to models that remain.

    Fields of models that are no longer registered are left alone: their whole
    table is dropped by ``_drop_models``, and dropping their columns one by
    one fails on columns other tables reference (``id``).
    """
    cr = env.cr
    cr.execute(
        """
        SELECT f.id, f.model, f.name, f.store, f.ttype
          FROM ir_model_fields f
          JOIN ir_model_data d ON d.model = 'ir.model.fields' AND d.res_id = f.id
         WHERE d.module = %s
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_data o
                 WHERE o.model = 'ir.model.fields' AND o.res_id = f.id
                   AND o.module <> d.module
           )
        """,
        (module,),
    )
    dropped = 0
    for field_id, model, name, store, ttype in cr.fetchall():
        if model not in env:
            continue  # the table goes with its model
        if name in env[model]._fields or name in MAGIC_COLUMNS:
            continue  # still defined by an installed addon
        dropped += 1
        table = env[model]._table
        if store and ttype not in ("one2many", "many2many") and _table_exists(
            cr, table
        ):
            # CASCADE removes indexes and foreign keys on this column only.
            cr.execute(
                sql.SQL("ALTER TABLE {} DROP COLUMN IF EXISTS {} CASCADE").format(
                    sql.Identifier(table), sql.Identifier(name)
                )
            )
        cr.execute("DELETE FROM ir_model_fields WHERE id = %s", (field_id,))
    return dropped


def _drop_models(env, module):
    """Drop tables and metadata of models only the retired addon declared."""
    cr = env.cr
    cr.execute(
        """
        SELECT m.id, m.model
          FROM ir_model m
          JOIN ir_model_data d ON d.model = 'ir.model' AND d.res_id = m.id
         WHERE d.module = %s
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_data o
                 WHERE o.model = 'ir.model' AND o.res_id = m.id
                   AND o.module <> d.module
           )
        """,
        (module,),
    )
    # A model that is still registered belongs to an installed addon.
    rows = [(model_id, name) for model_id, name in cr.fetchall() if name not in env]
    names = [name for _id, name in rows]
    if not names:
        return names
    # Chatter, attachments and federation work items of the removed records.
    for table, column in (
        ("mail_activity", "res_model"),
        ("mail_followers", "res_model"),
        ("mail_message", "model"),
        ("ir_attachment", "res_model"),
        ("federation_operation_task", "source_model"),
        ("federation_operation_job", "source_model"),
    ):
        if _table_exists(cr, table):
            cr.execute(
                sql.SQL("DELETE FROM {} WHERE {} = ANY(%s)").format(
                    sql.Identifier(table), sql.Identifier(column)
                ),
                (names,),
            )
    # Many2many tables the addon created.
    cr.execute(
        """
        SELECT r.id, r.name FROM ir_model_relation r
         WHERE r.module = (SELECT id FROM ir_module_module WHERE name = %s)
        """,
        (module,),
    )
    for relation_id, relation in cr.fetchall():
        cr.execute(
            sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                sql.Identifier(relation)
            )
        )
        cr.execute("DELETE FROM ir_model_relation WHERE id = %s", (relation_id,))
    for model_id, name in rows:
        cr.execute(
            sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                sql.Identifier(name.replace(".", "_"))
            )
        )
        cr.execute("DELETE FROM ir_model_constraint WHERE model = %s", (model_id,))
        cr.execute("DELETE FROM ir_model_fields WHERE model_id = %s", (model_id,))
        # Selections, access rights and rules cascade from ir_model.
        cr.execute("DELETE FROM ir_model WHERE id = %s", (model_id,))
    return names


def purge_retired_addon(env, module):
    cr = env.cr
    cr.execute("SELECT id, state FROM ir_module_module WHERE name = %s", (module,))
    row = cr.fetchone()
    if not row:
        return False
    if _code_present(module):
        _logger.warning(
            "Retired addon %s is still on the addons path; uninstall it from Apps "
            "instead. Nothing was removed.",
            module,
        )
        return False
    removed = {}
    for model in ORDERED_MODELS:
        removed[model] = _unlink(env, model, _owned(cr, module, model))
    cr.execute(
        """
        SELECT DISTINCT model FROM ir_model_data
         WHERE module = %s AND model <> ALL(%s)
        """,
        (module, list(ORDERED_MODELS + SCHEMA_MODELS)),
    )
    for (model,) in cr.fetchall():
        removed[model] = _unlink(env, model, _owned(cr, module, model))
    fields_dropped = _drop_fields(env, module)
    models_dropped = _drop_models(env, module)
    cr.execute("DELETE FROM ir_model_data WHERE module = %s", (module,))
    cr.execute(
        """
        UPDATE ir_module_module
           SET state = 'uninstalled', latest_version = NULL
         WHERE name = %s
        """,
        (module,),
    )
    _logger.info(
        "Removed leftovers of retired addon %s: %s; %s field(s); model(s) %s.",
        module,
        {key: value for key, value in removed.items() if value},
        fields_dropped,
        ", ".join(models_dropped) or "none",
    )
    return True


def remove_dangling_menus(env):
    """Remove menus whose action is gone or opens a model that is not registered."""
    cr = env.cr
    cr.execute("SELECT id, action FROM ir_ui_menu WHERE action IS NOT NULL")
    dangling = []
    for menu_id, reference in cr.fetchall():
        model, _sep, res_id = (reference or "").partition(",")
        if not res_id.isdigit():
            continue
        action = env[model].browse(int(res_id)).exists() if model in env else None
        if not action or (
            model == "ir.actions.act_window" and action.res_model not in env
        ):
            dangling.append(menu_id)
    if dangling:
        _logger.info(
            "Removing %s menu(s) with a missing action or model.", len(dangling)
        )
        _unlink(env, "ir.ui.menu", dangling)
    return dangling


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for module in RETIRED_ADDONS:
        purge_retired_addon(env, module)
    remove_dangling_menus(env)
    env.registry.clear_cache()
