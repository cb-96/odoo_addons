import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE federation_tournament
           SET website_published = FALSE,
               public_featured = FALSE
         WHERE edition_id IS NULL
           AND (website_published IS TRUE OR public_featured IS TRUE)
    """)
    _logger.info(
        "V2 public cutover unpublished %s legacy tournament records", cr.rowcount
    )
    cr.execute("""
        UPDATE federation_tournament tournament
           SET website_published = FALSE,
               public_featured = FALSE
          FROM federation_competition_edition edition
         WHERE tournament.edition_id = edition.id
           AND COALESCE(edition.website_published, FALSE) IS FALSE
           AND (tournament.website_published IS TRUE OR tournament.public_featured IS TRUE)
    """)
    _logger.info(
        "V2 public cutover unpublished %s child divisions of private editions",
        cr.rowcount,
    )
