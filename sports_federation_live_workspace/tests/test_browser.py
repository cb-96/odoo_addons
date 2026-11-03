"""Real backend client journeys, executed only on an installed Odoo database."""
from odoo.tests.common import HttpCase, tagged
from .test_commands import LiveFixture

HELPERS = """
const wait = async (predicate) => {
    for (let i=0; i<150; i++) { if (predicate()) return; await new Promise(r=>setTimeout(r,100)); }
    const status = [...document.querySelectorAll('.sf-status, .sf-error')]
        .map(element => element.textContent.trim()).filter(Boolean).join(' | ') || 'status unavailable';
    const scores = [...document.querySelectorAll('.sf-score')].map(input => ({
        value: input.value, readOnly: input.readOnly, fieldsetDisabled: input.closest('fieldset')?.disabled,
        controls: [...input.parentElement.querySelectorAll('button')].map(control => ({
            text: control.textContent.trim(), disabled: control.disabled,
        })),
    }));
    throw new Error(`Workspace condition timed out (${status}; scores=${JSON.stringify(scores)})`);
};
const button = (text) => [...document.querySelectorAll('main.sf-live-workspace button')].find(b=>b.textContent.trim()===text);
const change = (input,value) => { input.value=value; input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true})); };
const setOnline = (value) => Object.defineProperty(window.navigator, 'onLine', { configurable: true, get: () => value });
"""


@tagged("post_install", "-at_install", "sf_live_workspace", "sf_release_confidence")
class TestWorkspaceBrowser(LiveFixture, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.match._competition_workflow_edition().write({"court_scoring_mode": "aggregate"})

    def test_court_save_offline_capture_and_sync(self):
        self.browser_js("/odoo/action-sports_federation_live_workspace.action_run_court", HELPERS + """
(async () => {
    await wait(()=>document.querySelector('main.sf-live-workspace select option[value="0"]'));
    change(document.querySelector('main.sf-live-workspace select'),'0');
    await wait(()=>document.querySelectorAll('.sf-score').length===2);
    await wait(()=>document.querySelectorAll('.sf-score').length===2);
    change(document.querySelectorAll('.sf-score')[0],2); change(document.querySelectorAll('.sf-score')[1],1);
    const journalKey=Object.keys(localStorage).find(key=>key.startsWith('sf-court:v1:') && !key.endsWith(':last'));
    if (!journalKey) throw new Error('Local score draft was not persisted before save');
    const startingRevision=JSON.parse(localStorage.getItem(journalKey)).base.revision;
    button('Save draft').click();
    await wait(()=>{
        const journal=JSON.parse(localStorage.getItem(journalKey)||'null');
        return document.querySelector('.sf-status').textContent.includes('Synchronised draft')
            && !button('Save draft').disabled
            && journal?.pending.length===0
            && journal?.base.revision===startingRevision+1;
    });
    setOnline(false);
    if (navigator.onLine) throw new Error('Offline state could not be simulated');
    change(document.querySelectorAll('.sf-score')[0],3);
    await wait(()=>document.querySelector('.sf-status').textContent.includes('Saved on this device only')
        && Number(document.querySelectorAll('.sf-score')[0].value)===3);
    button('Save draft').click();
    await wait(()=>document.querySelector('.sf-status').textContent.includes('Saved on this device only')
        && JSON.parse(localStorage.getItem(journalKey)||'null')?.pending.length===1);
    const entries=Object.keys(localStorage).filter(k=>k.startsWith('sf-court:v1:') && !k.endsWith(':last'));
    if(!entries.some(k=>JSON.parse(localStorage.getItem(k)).pending.length===1)) throw new Error('Journal not persisted');
    setOnline(true); window.dispatchEvent(new Event('online'));
    await wait(()=>document.querySelector('.sf-status').textContent.includes('Synchronised draft')
        && !button('Save draft').disabled
        && entries.every(k=>JSON.parse(localStorage.getItem(k)).pending.length===0));
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
""", login=self.operator.login, timeout=90)
