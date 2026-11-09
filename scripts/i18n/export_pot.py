"""Export one translation template per module. Runs inside ``odoo shell``.

Uses Odoo's own export (the Settings > Translations > Export wizard with
"New language"), so the templates contain exactly the texts Odoo loads:
views, templates, field labels, selections, data records and code strings.

Environment:
    SF_I18N_MODULES  comma-separated module names
    SF_I18N_OUT      output directory, one <module>.pot per module
"""

import base64
import os
from pathlib import Path

out = Path(os.environ["SF_I18N_OUT"])
out.mkdir(parents=True, exist_ok=True)
names = [name for name in os.environ["SF_I18N_MODULES"].split(",") if name]
Module = env["ir.module.module"]  # noqa: F821 - provided by odoo shell
for name in names:
    module = Module.search([("name", "=", name), ("state", "=", "installed")])
    if not module:
        print("[i18n] skipped %s: not installed" % name)
        continue
    wizard = env["base.language.export"].create(  # noqa: F821
        {"lang": "__new__", "format": "po", "modules": [(6, 0, module.ids)]}
    )
    wizard.act_getfile()
    (out / ("%s.pot" % name)).write_bytes(base64.b64decode(wizard.data))
    print("[i18n] exported %s" % name)
