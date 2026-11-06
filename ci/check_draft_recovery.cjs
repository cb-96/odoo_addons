const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const values = new Map();
const context = {
    document: { readyState: 'loading', addEventListener() {} },
    window: { addEventListener() {} },
    location: { pathname: '/my/match-sheets/7', href: 'https://example.test/my/match-sheets/7' },
    URL, Date, Event: class {},
    sessionStorage: { getItem: k => values.get(k) || null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k) },
    assert,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(require('path').join(__dirname, '../sports_federation_portal/static/src/js/qol_draft_guard.js'), 'utf8') + `
const form = { dataset: { draftUser: '12' }, action: '/my/match-sheets/7/squad', elements: [
 { name: 'squad_player_ids', value: '45', type: 'checkbox', checked: true },
 { name: 'player_45_jersey', value: '7', type: 'text' },
 { name: 'guardian_name', value: 'private', type: 'text' },
 { name: 'notes', value: 'private', type: 'textarea' },
 { name: 'csrf_token', value: 'secret', type: 'hidden' },
 { name: 'approval_document', value: 'private.pdf', type: 'file' },
] };
assert.strictEqual(controls(form).length, 2);
save(form);
const draft = JSON.parse(sessionStorage.getItem(key(form)));
assert.strictEqual(draft.values.length, 2);
assert.strictEqual(draft.values[0].checked, true);
assert(!JSON.stringify(draft).includes('private'));
assert(!JSON.stringify(draft).includes('secret'));
const oldKey = key(form); form.dataset.draftUser = '13';
assert.notStrictEqual(key(form), oldKey);
assert.strictEqual(sessionStorage.getItem(key(form)), null);
form.dataset.draftUser = ''; assert.strictEqual(key(form), null);
`, context);
console.log('8 draft recovery behavior assertions passed');
