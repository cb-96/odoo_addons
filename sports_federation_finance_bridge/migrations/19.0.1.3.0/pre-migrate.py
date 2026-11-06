from odoo.tools import SQL


def migrate(cr, version):
    cr.execute("SELECT id FROM res_company ORDER BY id")
    companies = [row[0] for row in cr.fetchall()]
    for table in ("federation_finance_event", "federation_fee_type"):
        cr.execute(
            SQL(
                "ALTER TABLE %s ADD COLUMN IF NOT EXISTS company_id integer",
                SQL.identifier(table),
            )
        )
        if table == "federation_fee_type":
            cr.execute(
                "SELECT fee_type_id FROM federation_finance_event WHERE company_id IS NOT NULL GROUP BY fee_type_id HAVING COUNT(DISTINCT company_id)>1"
            )
            if cr.fetchone():
                raise RuntimeError(
                    "Legacy fee spans companies. Split and map fees before upgrade."
                )
            cr.execute(
                "UPDATE federation_fee_type f SET company_id=x.company_id FROM (SELECT fee_type_id, MIN(company_id) company_id FROM federation_finance_event WHERE company_id IS NOT NULL GROUP BY fee_type_id) x WHERE f.id=x.fee_type_id AND f.company_id IS NULL"
            )
        cr.execute(
            SQL(
                "SELECT COUNT(*) FROM %s WHERE company_id IS NULL",
                SQL.identifier(table),
            )
        )
        if cr.fetchone()[0]:
            if len(companies) != 1:
                raise RuntimeError(
                    "Explicitly map ambiguous legacy company_id in "
                    + table
                    + " before upgrading."
                )
            cr.execute(
                SQL(
                    "UPDATE %s SET company_id=%s WHERE company_id IS NULL",
                    SQL.identifier(table),
                    companies[0],
                )
            )
    cr.execute(
        "SELECT e.id FROM federation_finance_event e JOIN federation_fee_type f ON f.id=e.fee_type_id WHERE e.company_id != f.company_id LIMIT 1"
    )
    if cr.fetchone():
        raise RuntimeError("Resolve legacy event/fee company mismatch before upgrade.")
