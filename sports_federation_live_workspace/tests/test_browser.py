"""Real backend client journeys, executed only on an installed Odoo database."""
from odoo.tests.common import HttpCase, tagged
from .test_commands import LiveFixture

HELPERS = """
const wait = async (predicate) => {
    for (let i=0; i<150; i++) { if (predicate()) return; await new Promise(r=>setTimeout(r,100)); }
    throw new Error('Workspace condition timed out');
};
const button = (text) => [...document.querySelectorAll('main.sf-live-workspace button')].find(b=>b.textContent.trim()===text);
const change = (input,value) => { input.value=value; input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true})); };
"""


@tagged("post_install", "-at_install", "sf_live_workspace", "sf_release_confidence")
class TestWorkspaceBrowser(LiveFixture, HttpCase):
    def test_court_save_offline_capture_and_sync(self):
        self.browser_js("/odoo/action-sports_federation_live_workspace.action_run_court", HELPERS + """
(async () => {
    await wait(()=>document.querySelector('main.sf-live-workspace select option[value="0"]'));
    change(document.querySelector('main.sf-live-workspace select'),'0');
    await wait(()=>button('Open match')); button('Open match').click();
    await wait(()=>document.querySelectorAll('.sf-score').length===2);
    change(document.querySelectorAll('.sf-score')[0],2); change(document.querySelectorAll('.sf-score')[1],1);
    button('Save draft').click();
    await wait(()=>document.querySelector('.sf-status').textContent.includes('Saved on server'));
    Object.defineProperty(navigator,'onLine',{value:false,configurable:true});
    change(document.querySelectorAll('.sf-score')[0],3); button('Save draft').click();
    await wait(()=>document.querySelector('.sf-status').textContent.includes('Unsynchronised'));
    const entries=Object.keys(localStorage).filter(k=>k.startsWith('sf-court:v1:'));
    if(!entries.some(k=>JSON.parse(localStorage.getItem(k)).pending.length===1)) throw new Error('Journal not persisted');
    Object.defineProperty(navigator,'onLine',{value:true,configurable:true}); window.dispatchEvent(new Event('online'));
    await wait(()=>document.querySelector('.sf-status').textContent.includes('Saved on server'));
    if(Number(document.querySelectorAll('.sf-score')[0].value)!==3) throw new Error('Synchronised score lost');
    console.log('test successful');
})().catch(error=>console.error(error));
""", login=self.operator.login, timeout=90)

    def test_visual_preview_and_apply(self):
        action = self.env["ir.actions.client"].create({"name": "Visual test", "tag": "federation_visual_plan",
            "context": repr({"active_id": self.schedule.id})})
        self.browser_js("/odoo/action-%s" % action.id, HELPERS + """
(async () => {
    await wait(()=>document.querySelector('.sf-grid table'));
    button('Preview regeneration, retain manual pins').click();
    await wait(()=>button('Apply exactly this preview'));
    const section=button('Apply exactly this preview').closest('section');
    change(section.querySelector('textarea'),'Browser-tested proposal');
    await wait(()=>!button('Apply exactly this preview').disabled);
    button('Apply exactly this preview').click();
    await wait(()=>!button('Apply exactly this preview'));
    if(!document.querySelector('.sf-grid table').textContent.includes('vs')) throw new Error('Applied fixtures not displayed');
    console.log('test successful');
})().catch(error=>console.error(error));
""", login=self.env.user.login, timeout=90)
