// Real staging browser smoke. Missing fixtures fail, never become acceptance evidence.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
const config = JSON.parse(process.env.SF_VISUAL_FIXTURES || '{}');
for (const key of ['login','password','action_id','schedule_id','fixture_id','first_slot','second_slot','blocked_slot']) {
    if (!config[key]) throw Error(`Missing SF_VISUAL_FIXTURES.${key}`);
}
const base = process.env.SF_BASE_URL;
if (!base) throw Error('Set SF_BASE_URL');
const browser = await chromium.launch();
try {
    const context = await browser.newContext({viewport: {width: 1280, height: 900}});
    const page = await context.newPage();
    await page.goto(`${base}/web/login`);
    await page.locator('input[name="login"]').fill(config.login);
    await page.locator('input[name="password"]').fill(config.password);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(url => !url.pathname.includes('/web/login'));
    const rpc = async (model, method, args) => page.evaluate(async ({model, method, args}) => {
        const response = await fetch(`/web/dataset/call_kw/${model}/${method}`, {method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({jsonrpc:'2.0',method:'call',params:{model,method,args,kwargs:{}},id:1})});
        const body=await response.json(); if(body.error)throw Error(body.error.data?.message || body.error.message); return body.result;
    }, {model, method, args});
    await page.goto(`${base}/odoo/action-${config.action_id}`);
    await page.locator('#visual-fixture').waitFor();
    const before = await rpc('federation.visual.planning','load',[config.schedule_id]);
    assert(before.slots.some(slot=>slot.id===config.blocked_slot));
    // Native keyboard fixture selection and destination navigation.
    const index = await page.locator('#visual-fixture option').evaluateAll((options,id)=>options.findIndex(option=>Number(option.value)===id), config.fixture_id);
    assert(index>0);
    await page.locator('#visual-fixture').focus(); await page.keyboard.press('Home');
    for(let i=0;i<index;i++)await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter'); await page.keyboard.press('Tab');
    await page.waitForFunction(()=>document.querySelector('[data-destination-button][aria-disabled="false"]'));
    const blocked = page.locator(`[data-slot="${config.blocked_slot}"]`);
    assert.equal(await blocked.getAttribute('aria-disabled'),'true');
    await blocked.focus(); await page.keyboard.press('Enter');
    await page.getByText('Mandatory blocker:',{exact:true}).first().waitFor();
    assert.equal((await rpc('federation.visual.planning','load',[config.schedule_id])).schedule.revision,before.schedule.revision);
    const first = page.locator(`[data-slot="${config.first_slot}"]`);
    await first.focus(); await page.keyboard.press('End');
    assert.equal(await page.evaluate(()=>document.activeElement?.hasAttribute('data-destination-button')),true);
    await first.focus(); await page.keyboard.press('Enter');
    await page.locator('[data-preview-heading]').waitFor();
    await page.getByRole('button',{name:'Keep this as candidate A',exact:true}).focus(); await page.keyboard.press('Enter');
    await page.locator(`[data-slot="${config.second_slot}"]`).focus(); await page.keyboard.press('Enter');
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(button=>button.textContent.trim()==='Compare A with current candidate' && !button.disabled));
    await page.getByRole('button',{name:'Compare A with current candidate',exact:true}).focus(); await page.keyboard.press('Enter');
    await page.getByText('Weighted fairness penalty (lower is better):',{exact:false}).waitFor();
    assert.equal((await rpc('federation.visual.planning','load',[config.schedule_id])).schedule.revision,before.schedule.revision);
    await page.locator('[data-preview-heading]').evaluate(node=>node.closest('section').querySelector('textarea').focus());
    await page.keyboard.type('Staging keyboard move, preserve governed preview boundary');
    await page.getByRole('button',{name:'Apply exactly this preview',exact:true}).focus(); await page.keyboard.press('Enter');
    await page.locator('[data-preview-heading]').waitFor({state:'detached'});
    const applied=await rpc('federation.visual.planning','load',[config.schedule_id]);
    assert.equal(applied.assignments.find(a=>a.fixture_id===config.fixture_id).slot_id,config.second_slot);
    // Native drag creates a preview only. Select the fixture first so assessment is ready.
    await page.locator(`[data-fixture="${config.fixture_id}"]`).first().click();
    await page.waitForFunction(()=>document.querySelector('[data-destination-button][aria-disabled="false"]'));
    await page.locator(`[data-fixture="${config.fixture_id}"]`).first().dragTo(page.locator(`[data-slot="${config.first_slot}"]`));
    await page.locator('[data-preview-heading]').waitFor();
    assert.equal((await rpc('federation.visual.planning','load',[config.schedule_id])).schedule.revision,applied.schedule.revision);
    // Regeneration is preview-only and must preserve every retained pin.
    const regen=await rpc('federation.visual.planning','preview',[config.schedule_id,'regenerate']);
    assert.deepEqual(regen.impact.pin_changes,[]);
    const record=await rpc('federation.visual.proposal','read',[[regen.id],['candidate']]);
    for(const assignment of applied.assignments){
        if(applied.methods[assignment.fixture_id]!=='automatic')assert.equal(record[0].candidate[assignment.fixture_id],assignment.slot_id);
    }
    console.log('Live visual scheduling smoke passed. Human usability and full integrity suite remain separate.');
} finally { await browser.close(); }
