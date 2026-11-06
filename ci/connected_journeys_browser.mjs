/** Live read-only browser regression. Business command and human acceptance remain separate. */
import { chromium } from 'playwright';
import { writeFile } from 'node:fs/promises';
const output = process.env.SF_JOURNEY_BROWSER_OUTPUT || 'connected-browser-results.json';
const base = process.env.SF_BASE_URL;
const accounts = JSON.parse(process.env.SF_JOURNEY_ACCOUNTS || '{}');
const roles = ['club', 'official', 'planner', 'reviewer', 'manager'];
const results = [];
if (!base || roles.some(role => !accounts[role]?.login || !accounts[role]?.password)) {
    await writeFile(output, JSON.stringify({status: 'blocked', reason: 'SF_BASE_URL and all five SF_JOURNEY_ACCOUNTS are required'}, null, 2));
    process.exit(2);
}
const browser = await chromium.launch();
try {
    for (const role of roles) {
        const context = await browser.newContext({baseURL: base, viewport: {width: 360, height: 800}});
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        try {
            await page.goto('/web/login' + (process.env.SF_DB ? '?db=' + encodeURIComponent(process.env.SF_DB) : ''));
            await page.locator('input[name="login"]').fill(accounts[role].login);
            await page.locator('input[name="password"]').fill(accounts[role].password);
            await Promise.all([page.waitForURL(url => !url.pathname.endsWith('/web/login')), page.locator('button[type="submit"]').click()]);
            const response = await page.goto('/my/work?role=' + role);
            if (response.status() !== 200) throw new Error('Role landing did not return 200');
            for (const bucket of ['now', 'soon', 'waiting', 'recent']) {
                if (await page.locator(`[data-journey-bucket="${bucket}"]`).count() !== 1) throw new Error('Missing or duplicated group ' + bucket);
            }
            for (const card of await page.locator('[data-journey-card]').all()) {
                for (const label of ['Next owner', 'Deadline', 'Blocker', 'Next action']) {
                    if (!await card.getByText(label, {exact: true}).isVisible()) throw new Error('Missing metadata ' + label);
                }
                if (!await card.locator('[data-journey-handoff]').isVisible()) throw new Error('Missing handoff');
            }
            if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error('Horizontal overflow at 360px');
            await page.locator('#journey-role').focus();
            await page.keyboard.press('Tab');
            if (!await page.getByRole('button', {name: 'Switch responsibility', exact: true}).evaluate(node => node === document.activeElement)) throw new Error('Keyboard switch inaccessible');
            await page.goto('/my/work');
            if (await page.locator('#journey-role').inputValue() !== role) throw new Error('Responsibility not remembered');
            const open = page.locator('[data-journey-card] a[data-journey-open]').first();
            if (await open.count() && !(await open.getAttribute('href')).startsWith('/odoo/')) {
                await open.click();
                await page.getByRole('link', {name: 'Back to my work', exact: true}).waitFor();
            }
            if (errors.length) throw new Error(errors.join('; '));
            results.push({role, status: 'passed', viewport: '360x800'});
        } catch (error) {
            results.push({role, status: 'failed', error: error.message});
        } finally { await context.close(); }
    }
} finally { await browser.close(); }
const status = results.every(result => result.status === 'passed') ? 'passed' : 'failed';
await writeFile(output, JSON.stringify({status, results, scope: 'Read-only browser regression, not business-command or human qualification'}, null, 2));
process.exitCode = status === 'passed' ? 0 : 1;
