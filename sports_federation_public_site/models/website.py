from textwrap import dedent

from odoo import models


class Website(models.Model):
    _inherit = "website"

    def _get_cleanup_websites(self):
        """Return the websites that should be normalized by the public-site cleanup."""
        websites = self.sudo()
        if websites:
            return websites
        website_id = self.env.context.get("website_id")
        if website_id:
            scoped = self.env["website"].sudo().browse(int(website_id)).exists()
            if scoped:
                return scoped

        current_website = self.env["website"].get_current_website()
        if current_website:
            return current_website.sudo()

        return self.env["website"].sudo().search([], limit=1)

    def _get_public_site_brand_name(self):
        """Return the canonical public-site brand name."""
        return "Sports Federation"

    def _has_placeholder_shell(self, website):
        """Return whether a website still carries the stock website shell branding."""
        placeholder_values = self._get_placeholder_company_values()
        company = website.company_id.sudo()
        return (
            website.name.startswith("My Website")
            or company.name in placeholder_values["name"]
            or company.phone == placeholder_values["phone"]
            or (
                company.street == placeholder_values["street"]
                and company.city == placeholder_values["city"]
                and company.zip == placeholder_values["zip"]
            )
        )

    def _is_placeholder_navigation_menu(self, menu):
        """Return whether a menu entry matches the stock website navigation shell."""
        menu_name = menu.name or ""
        menu_url = menu.url or ""
        return (
            (menu_name == "Events" and menu_url == "/event")
            or (menu_name == "News" and menu_url.startswith("/blog"))
            or (menu_name in ("About Us", "About us") and menu_url == "/about-us")
            or (menu_name == "Contact us" and menu_url == "/contactus")
        )

    def _get_placeholder_company_values(self):
        """Return stock company values that should be cleared or rebranded."""
        return {
            "name": {"YourCompany", "My Company"},
            "phone": "+1 555-555-5556",
            "street": "8000 Marina Blvd, Suite 300",
            "city": "Brisbane",
            "zip": "94005",
        }

    def _get_public_site_footer_arch(self):
        """Return the normalized footer view architecture."""
        return dedent("""
            <data inherit_id="website.layout" name="Sports Federation Footer" active="True">
                <xpath expr="//div[@id='footer']" position="replace">
                    <div id="footer" class="oe_structure oe_structure_solo border text-break" t-ignore="true" t-if="not no_footer" style="--box-border-top-width: 0px; --box-border-left-width: 0px; --box-border-right-width: 0px;">
                        <section class="s_text_block pt40 pb16" data-snippet="s_text_block" data-name="Federation Footer">
                            <div class="container">
                                <div class="row">
                                    <div class="col-lg-6 pt24 pb24">
                                        <h4>Sports Federation</h4>
                                        <p>Tournament hubs, schedules, results, standings, and club self-service all live here. Federation staff, clubs, and officials can use the website and portal to follow active competition work.</p>
                                    </div>
                                    <div class="col-lg-3 pt24 pb24">
                                        <h5>Explore</h5>
                                        <ul class="list-unstyled">
                                            <li><a href="/tournaments">Tournaments</a></li>
                                            <li><a href="/tournaments#published">Tournament Updates</a></li>
                                            <li><a href="/seasons">Seasons</a></li>
                                            <li><a href="/my/home">Portal</a></li>
                                        </ul>
                                    </div>
                                    <div class="col-lg-3 pt24 pb24">
                                        <h5>Support</h5>
                                        <p class="mb-3">Need help with registrations, compliance submissions, or match-day workflows?</p>
                                        <a href="/contactus" class="btn btn-outline-primary">Contact Federation Staff</a>
                                    </div>
                                </div>
                            </div>
                        </section>
                    </div>
                </xpath>
            </data>
            """).strip()

    def _cleanup_placeholder_navigation(self):
        """Remove stock website menu entries that do not belong in the federation shell."""
        menu_model = self.env["website.menu"].sudo()
        removed = 0

        for website in self._get_cleanup_websites():
            if not website.menu_id:
                continue
            menus = menu_model.search([("id", "child_of", website.menu_id.id)])
            placeholders = menus.filtered(
                lambda menu: self._is_placeholder_navigation_menu(menu)
            )
            if placeholders:
                removed += len(placeholders)
                placeholders.unlink()

        return removed

    def _cleanup_placeholder_company_details(self):
        """Rebrand placeholder company records and clear fake contact details."""
        placeholder_values = self._get_placeholder_company_values()
        cleaned = 0

        for website in self._get_cleanup_websites():
            company = website.company_id.sudo()
            company_updates = {}

            if company.name in placeholder_values["name"]:
                company_updates["name"] = self._get_public_site_brand_name()
            if company.phone == placeholder_values["phone"]:
                company_updates["phone"] = False
            if (
                company.street == placeholder_values["street"]
                and company.city == placeholder_values["city"]
                and company.zip == placeholder_values["zip"]
            ):
                company_updates.update(
                    {
                        "street": False,
                        "street2": False,
                        "city": False,
                        "zip": False,
                    }
                )

            if company_updates:
                company.write(company_updates)
                cleaned += 1

        return cleaned

    def _cleanup_placeholder_branding(self):
        """Replace stock website branding with federation branding."""
        brand_name = self._get_public_site_brand_name()
        renamed = 0

        for website in self._get_cleanup_websites():
            if website.name.startswith("My Website"):
                website.write({"name": brand_name})
                renamed += 1

        return renamed

    def _cleanup_placeholder_footer_views(self):
        """Replace stock footer view content with federation-specific copy."""
        view_model = self.env["ir.ui.view"].sudo()
        footer_arch = self._get_public_site_footer_arch()
        layout_view = self.env.ref("website.layout")
        cleaned = 0
        placeholder_tokens = (
            "Designed for companies",
            "My Company",
            "hello@mycompany.com",
            "+1 555-555-5556",
        )

        for website in self._get_cleanup_websites():
            footer_views = view_model.search(
                [
                    ("website_id", "=", website.id),
                    ("key", "=like", "website.template_footer_%"),
                ]
            )
            placeholder_views = footer_views.filtered(
                lambda view: any(
                    token in (view.arch_db or "") for token in placeholder_tokens
                )
            )
            for view in placeholder_views:
                view.write({"arch_db": footer_arch})
                cleaned += 1

            if not footer_views and self._has_placeholder_shell(website):
                view_model.create(
                    {
                        "name": "Sports Federation Footer",
                        "type": "qweb",
                        "mode": "extension",
                        "key": "website.template_footer_descriptive",
                        "website_id": website.id,
                        "inherit_id": layout_view.id,
                        "active": True,
                        "priority": 16,
                        "arch_db": footer_arch,
                    }
                )
                cleaned += 1

        return cleaned

    def _cleanup_default_public_site_content(self):
        """Normalize default website shell content for the federation public site."""
        summary = {
            "footers_cleaned": self._cleanup_placeholder_footer_views(),
            "branding_renamed": self._cleanup_placeholder_branding(),
            "company_records_cleaned": self._cleanup_placeholder_company_details(),
            "menus_removed": self._cleanup_placeholder_navigation(),
        }
        self.env["website.menu"]._cleanup_stale_public_site_menus()
        return summary
