import logging


_logger = logging.getLogger(__name__)

_VIEW_MODULE = "sports_federation_public_site"
_VIEW_NAME = "page_tournaments_hub_discovery_sections"
_OLD_ACTION = "/" + "tournaments"
_NEW_ACTION = "/competitions"


def migrate(cr, version):
    """Repair the stored inherited-view selector before parent views are reloaded."""
    cr.execute(
        """
        UPDATE ir_ui_view AS view
           SET arch_db = replace(view.arch_db::text, %s, %s)::jsonb
          FROM ir_model_data AS data
         WHERE data.module = %s
           AND data.name = %s
           AND data.model = 'ir.ui.view'
           AND data.res_id = view.id
           AND view.arch_db::text LIKE %s
        """,
        (
            _OLD_ACTION,
            _NEW_ACTION,
            _VIEW_MODULE,
            _VIEW_NAME,
            f"%{_OLD_ACTION}%",
        ),
    )
    if cr.rowcount:
        _logger.info(
            "Updated the stored competition-hub discovery selector to %s",
            _NEW_ACTION,
        )
