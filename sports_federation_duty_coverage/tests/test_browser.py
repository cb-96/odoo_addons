from odoo.tests.common import HttpCase, tagged
from .common import CoverageFixture


@tagged(
    "post_install", "-at_install", "sf_release_confidence", "sf_duty_coverage_browser"
)
class TestCoverageBrowser(CoverageFixture, HttpCase):
    def test_official_response_browser(self):
        self.browser_js(
            "/my/duty-assignments/%s" % self.assignment.id,
            """
            (async () => {
                const form = document.querySelector('form[action$="/respond"]');
                if (!form) throw new Error('Response form missing');
                const data = new FormData(form); data.set('action', 'confirm');
                const response = await fetch(form.action, {method:'POST',body:data});
                const html = await response.text();
                if (!response.ok || !html.includes('Response recorded.')) {
                    throw new Error('Acceptance failed');
                }
                if (!html.includes('Back to my assignments')) {
                    throw new Error('Return path missing');
                }
                console.log('test successful');
            })().catch(error => console.error(error));
        """,
            ready="document.querySelector('form[action$=\"/respond\"]')",
            login=self.official_user.login,
        )

    def test_other_official_get_is_hidden(self):
        # Browser login avoids assuming a test-user password.
        self.browser_js(
            "/my/duty-assignments",
            """
            (async () => {
                const response=await fetch('/my/duty-assignments/%s');
                if (response.status !== 404) {
                    throw new Error('Foreign assignment was exposed');
                }
                console.log('test successful');
            })().catch(error => console.error(error));
        """ % self.assignment.id,
            login=self.other_user.login,
        )
