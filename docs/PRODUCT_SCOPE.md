# Product scope

The default product is the competition lifecycle, publication, match-day operations, rosters, officiating, standings, portal, and public site.

Optional capabilities stay separate only when they are legally required, independently deployed, actively used, separately owned, or materially reduce operational risk.

## Review register

Run:

```bash
python3 ci/audit_product_scope.py --json artifacts/product-scope.json
```

For each optional addon, record an owner and one decision: keep, consolidate, disable, or retire. Absence of usage evidence is not evidence that deletion is safe. Database records, XML IDs, routes, scheduled jobs, and downstream dependencies must be checked before retirement.

## Reporting review

The report catalog model and view are not part of the installed product. Review existing reports through their owning reporting models, menus, schedules, exports, and retention requirements before consolidating or retiring any report.
