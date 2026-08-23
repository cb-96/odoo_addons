import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("SELECT to_regclass('public.federation_tournament_registration')")
    if cr.fetchone()[0]:
        cr.execute("DROP TABLE federation_tournament_registration CASCADE")
        _logger.warning("Removed V1 federation_tournament_registration table")
    cr.execute(
        """DELETE FROM ir_model_data WHERE module = 'sports_federation_portal' AND name IN ('model_federation_tournament_registration','seq_tournament_registration','action_federation_tournament_registration','rule_tournament_registration_portal_own','access_tournament_registration_portal','access_tournament_registration_manager')"""
    )
