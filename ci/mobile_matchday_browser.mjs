/** Live staging tests. Each interruption scenario needs a fresh disposable match. */
import {chromium} from 'playwright';
import {writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const config = JSON.parse(process.env.SF_MOBILE_FIXTURES || '{}');
const baseURL = process.env.SF_BASE_URL;
const output = process.env.SF_MOBILE_OUTPUT || 'mobile-browser-results.json';
const results = [];
if (!baseURL || !config.operator?.login || !config.operator?.password || !config.scenarios) {
    await writeFile(output, JSON.stringify({status: 'blocked', reason: 'SF_BASE_URL and SF_MOBILE_FIXTURES are required'}, null, 2));
    process.exit(2);
}
const browser = await chromium.launch();
async function login(account) {
    const context = await browser.newContext({baseURL, viewport: {width: 360, height: 800}});
    const page = await context.newPage();
    page.on('dialog', dialog => dialog.accept());
    await page.goto('/web/login');
    await page.locator('input[name="login"]').fill(account.login);
    await page.locator('input[name="password"]').fill(account.password);
    await Promise.all([page.waitForURL(url => !url.pathname.endsWith('/web/login')), page.locator('button[type="submit"]').click()]);
    return {context, page};
}
async function tabTo(page, locator) {
    for (let index = 0; index < 150; index++) {
        if (await locator.evaluate(node => node === document.activeElement)) return;
        await page.keyboard.press('Tab');
    }
    throw Error('Keyboard could not reach requested control');
}
async function press(page, locator) { await tabTo(page, locator); await page.keyboard.press('Enter'); }
async function number(page, locator, value) {
    await tabTo(page, locator); await page.keyboard.press('ControlOrMeta+A'); await page.keyboard.type(String(value));
}
async function inspect(page, fixture) {
    return page.evaluate(async fixture => {
        const response = await fetch('/web/dataset/call_kw/federation.court.commands/inspect', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {model: 'federation.court.commands', method: 'inspect',
                args: [fixture.matchday_id, fixture.court_id, fixture.match_id], kwargs: {}}, id: Date.now()})});
        const body = await response.json();
        if (body.error) throw Error(body.error.data?.message || 'Inspection failed');
        return body.result;
    }, fixture);
}
async function openCourt(page, fixture) {
    await page.goto('/odoo/action-sports_federation_live_workspace.action_run_court');
    const court = page.locator('.sf-court-mobile select').first();
    await court.waitFor();
    if (!await page.locator(`.sf-court-mobile[data-current-match="${fixture.match_id}"]`).count()) {
        await court.selectOption(String(fixture.court_index || 0));
        const show = page.getByRole('button', {name: 'Show or hide match queue', exact: true});
        if (await show.count()) await show.click();
        await page.locator(`[data-match-id="${fixture.match_id}"]`).click();
    }
    await page.locator(`.sf-court-mobile[data-current-match="${fixture.match_id}"]`).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, '360px horizontal overflow');
}
async function score(page) {
    await number(page, page.getByRole('spinbutton', {name: 'Home score', exact: true}), 2);
    await number(page, page.getByRole('spinbutton', {name: 'Away score', exact: true}), 1);
}
async function journal(page, matchId) {
    return page.evaluate(matchId => {
        const key = Object.keys(localStorage).find(key => key.startsWith('sf-court:v1:') && key.endsWith(':' + matchId));
        return key ? JSON.parse(localStorage.getItem(key)) : null;
    }, matchId);
}
try {
    for (const name of ['before_submission', 'during_submission', 'after_submission', 'duplicate_replay', 'reload_reconnect', 'changed_context', 'second_tab', 'storage_failure']) {
        const fixture = config.scenarios[name];
        if (!fixture) { results.push({scenario: name, status: 'blocked', reason: 'Fresh fixture missing'}); continue; }
        const {context, page} = await login(config.operator);
        try {
            await openCourt(page, fixture);
            const before = await inspect(page, fixture);
            if (name === 'second_tab') {
                const second = await context.newPage();
                await second.goto('/odoo/action-sports_federation_live_workspace.action_run_court');
                await second.getByRole('alert').filter({hasText: 'another tab'}).waitFor();
                assert.equal((await inspect(page, fixture)).receipt_count, before.receipt_count);
                results.push({scenario: name, status: 'passed'}); continue;
            }
            if (name === 'storage_failure') {
                await page.evaluate(() => {
                    const original = Storage.prototype.setItem;
                    Storage.prototype.setItem = function(key, value) { if (key.startsWith('sf-court:v1:')) throw Error('Controlled quota failure'); return original.call(this, key, value); };
                });
                await score(page);
                await page.locator('[data-save-state="memory"]').waitFor();
                assert.equal((await inspect(page, fixture)).receipt_count, before.receipt_count);
                results.push({scenario: name, status: 'passed'}); continue;
            }
            await score(page);
            if (name === 'changed_context') {
                const other = await login(config.operator);
                try {
                    await other.page.goto('/my/matchday-mobile');
                    await other.page.evaluate(async ({fixture, before}) => {
                        const command = {key: crypto.randomUUID(), revision: before.revision, signature: before.signature,
                            operation: 'save', payload: {...before.payload, home: 7, away: 3}};
                        const response = await fetch('/web/dataset/call_kw/federation.court.commands/sync', {method: 'POST', headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {model: 'federation.court.commands', method: 'sync', args: [fixture.matchday_id, fixture.court_id, fixture.match_id, [command]], kwargs: {}}, id: 1})});
                        const result = await response.json(); if (result.error) throw Error(result.error.data?.message || 'Other-session save failed');
                    }, {fixture, before});
                } finally { await other.context.close(); }
                await press(page, page.getByRole('button', {name: 'Check server result status', exact: true}));
                await page.getByRole('alert').filter({hasText: 'Another session changed'}).waitFor();
                assert.equal((await journal(page, fixture.match_id)).draft.home, 2);
                assert.equal((await inspect(page, fixture)).payload.home, 7);
                results.push({scenario: name, status: 'passed'}); continue;
            }
            let dropped = false;
            if (name === 'before_submission') await context.setOffline(true);
            else await page.route('**/web/dataset/call_kw/**', async route => {
                const body = route.request().postDataJSON();
                if (!dropped && body?.params?.model === 'federation.court.commands' && body.params.method === 'sync') {
                    dropped = true;
                    if (name !== 'during_submission') await route.fetch(); // Commit, then lose the response.
                    await route.abort('failed');
                } else await route.continue();
            });
            await press(page, page.getByRole('button', {name: name === 'reload_reconnect' ? 'Save draft' : 'Submit for review', exact: true}));
            if (name === 'before_submission') {
                await page.locator('[data-save-state="submission_pending"]').waitFor();
            } else await page.getByRole('alert').waitFor();
            const queued = await journal(page, fixture.match_id);
            assert.equal(queued.pending.length, 1, 'Original command not durably retained');
            const originalKey = queued.pending[0].key;
            await page.unroute('**/web/dataset/call_kw/**');
            if (name === 'before_submission') await context.setOffline(false);
            if (name === 'reload_reconnect') { await page.reload(); await page.locator('.sf-court-mobile[data-current-match]').waitFor(); }
            const synchronise = page.getByRole('button', {name: 'Synchronise queued work', exact: true});
            if (await synchronise.isEnabled()) await press(page, synchronise);
            await page.locator(`[data-save-state="${name === 'reload_reconnect' ? 'synchronised' : 'submitted'}"]`).waitFor();
            const after = await inspect(page, fixture);
            assert.equal(after.receipt_count, before.receipt_count + 1, 'Duplicate receipt or missing acknowledged save');
            assert.equal(after.payload.home, 2); assert.equal(after.payload.away, 1);
            assert.equal((await journal(page, fixture.match_id)).pending.length, 0);
            if (name === 'duplicate_replay') {
                await page.evaluate(async ({fixture, command}) => {
                    const response = await fetch('/web/dataset/call_kw/federation.court.commands/sync', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {model: 'federation.court.commands', method: 'sync', args: [fixture.matchday_id, fixture.court_id, fixture.match_id, [command]], kwargs: {}}, id: 1})});
                    const result = await response.json(); if (result.error) throw Error(result.error.data?.message || 'Replay failed');
                }, {fixture, command: queued.pending[0]});
                assert.equal((await inspect(page, fixture)).receipt_count, before.receipt_count + 1);
            }
            results.push({scenario: name, status: 'passed', original_key: originalKey, receipt_delta: 1});
        } catch (error) { results.push({scenario: name, status: 'failed', error: error.message}); }
        finally { await context.close(); }
    }
    // Actual official/organiser keyboard workflows use separate disposable fixtures.
    for (const journey of ['official_accept_venue', 'organiser_replace']) {
        const fixture = config[journey];
        const account = journey === 'official_accept_venue' ? config.official : config.manager;
        if (!fixture || !account?.login || !account?.password) { results.push({journey, status: 'blocked', reason: 'Account or fixture missing'}); continue; }
        const {context, page} = await login(account);
        try {
            if (journey === 'official_accept_venue') {
                await page.goto('/my/duty-assignments/' + fixture.assignment_id);
                await page.getByRole('heading', {name: 'Venue and check-in'}).waitFor();
                await press(page, page.getByRole('button', {name: 'Accept assignment', exact: true}));
                await press(page, page.getByRole('button', {name: 'Request check-in', exact: true}));
                await page.getByText('Check-in requested. The organiser still confirms attendance.').waitFor();
            } else {
                await page.goto('/my/matchday-mobile/assignments/' + fixture.assignment_id + '/replace');
                const select = page.getByLabel('Replacement official', {exact: true});
                const options = await select.locator('option').evaluateAll(nodes => nodes.map(node => node.value));
                const index = options.indexOf(String(fixture.referee_id)); assert.ok(index > 0);
                await tabTo(page, select); await page.keyboard.press('Home');
                for (let i = 0; i < index; i++) await page.keyboard.press('ArrowDown');
                await tabTo(page, page.getByLabel('Reason', {exact: true})); await page.keyboard.type('Mobile keyboard replacement test');
                await press(page, page.getByRole('button', {name: 'Record replacement', exact: true}));
                await page.getByRole('status').filter({hasText: 'Replacement recorded'}).waitFor();
            }
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
            results.push({journey, status: 'passed', keyboard: true, viewport: 360});
        } catch (error) { results.push({journey, status: 'failed', error: error.message}); }
        finally { await context.close(); }
    }
} finally { await browser.close(); }
const status = results.every(result => result.status === 'passed') ? 'passed' : 'failed_or_blocked';
await writeFile(output, JSON.stringify({status, results, human_acceptance: 'not_measured'}, null, 2));
process.exitCode = status === 'passed' ? 0 : 1;
