from odoo import api, models


class WebsiteMenu(models.Model):
    _inherit = "website.menu"

    @api.model
    def _get_public_site_coverage_menu_values(self):
        """Return public site coverage menu values."""
        return {
            "name": "Published Coverage",
            "url": "/tournaments#published",
            "sequence": 10,
            "is_visible": True,
        }

    @api.model
    def _cleanup_stale_public_site_menus(self):
        """Handle cleanup stale public site menus."""
        menu_model = self.sudo()
        target_vals = self._get_public_site_coverage_menu_values()
        summary = {
            "normalized": 0,
            "reparented": 0,
            "removed": 0,
        }

        tournament_menus = menu_model.search(
            [
                ("name", "=", "Tournaments"),
                ("parent_id", "!=", False),
            ],
            order="id asc",
        )

        for tournament_menu in tournament_menus:
            published_children = menu_model.search(
                [
                    ("parent_id", "=", tournament_menu.id),
                    "|",
                    ("url", "=", target_vals["url"]),
                    ("name", "=", target_vals["name"]),
                ],
                order="sequence asc, id asc",
            )
            legacy_siblings = menu_model.search(
                [
                    ("parent_id", "=", tournament_menu.parent_id.id),
                    ("id", "!=", tournament_menu.id),
                    ("url", "=like", "/competitions%"),
                ],
                order="sequence asc, id asc",
            )
            legacy_children = menu_model.search(
                [
                    ("parent_id", "=", tournament_menu.id),
                    ("url", "=like", "/competitions%"),
                ],
                order="sequence asc, id asc",
            )
            legacy_candidates = (legacy_siblings | legacy_children).sorted(
                lambda menu: (menu.sequence, menu.id)
            )

            target_menu = published_children[:1]
            if target_menu:
                legacy_candidates -= target_menu
                target_menu.write(target_vals)
                summary["normalized"] += 1
            elif legacy_candidates:
                target_menu = legacy_candidates[:1]
                target_menu.write({**target_vals, "parent_id": tournament_menu.id})
                legacy_candidates -= target_menu
                summary["reparented"] += 1
            else:
                continue

            duplicate_published_children = published_children - target_menu
            duplicate_menus = duplicate_published_children | legacy_candidates
            if duplicate_menus:
                summary["removed"] += len(duplicate_menus)
                duplicate_menus.unlink()

        return summary
