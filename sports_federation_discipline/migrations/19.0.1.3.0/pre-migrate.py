def migrate(cr, version):
    cr.execute('ALTER TABLE federation_disciplinary_case ADD COLUMN IF NOT EXISTS company_id integer')
    cr.execute('SELECT COUNT(*) FROM federation_disciplinary_case WHERE company_id IS NULL')
    if cr.fetchone()[0]:
        cr.execute('SELECT id FROM res_company ORDER BY id')
        companies = [row[0] for row in cr.fetchall()]
        if len(companies) != 1:
            raise RuntimeError('Explicitly map legacy disciplinary case company_id before multi-company upgrade.')
        cr.execute('UPDATE federation_disciplinary_case SET company_id=%s WHERE company_id IS NULL', [companies[0]])
