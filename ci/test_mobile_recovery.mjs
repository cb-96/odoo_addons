import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('../sports_federation_live_workspace/static/src/mobile_recovery.js', import.meta.url), 'utf8');
const policy = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const cacheSource = readFileSync(new URL('../sports_federation_live_workspace/static/src/court_cache.js', import.meta.url), 'utf8');
const {restoreCourtCache} = await import(`data:text/javascript;base64,${Buffer.from(cacheSource).toString('base64')}`);
let count = 0;
function test(name, fn) { fn(); count++; console.log('PASS', name); }
const command = {key: 'original-key', revision: 0, operation: 'save', payload: {home: 2, away: 1}, signature: 'slot'};
const journal = {draft: {home: 2, away: 1}, pending: [command], dirty: false, base: {revision: 0, signature: 'slot'}};
const server = {match_id: 1, revision: 1, signature: 'slot', draft_signature: 'slot', payload: {home: 2, away: 1}, result_state: 'draft'};
function storage() { const data = new Map(); return {getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value)}; }
test('empty journal', () => assert.equal(policy.readJournal(null), null));
test('valid legacy journal preserves key', () => assert.equal(policy.readJournal(JSON.stringify(journal)).pending[0].key, 'original-key'));
test('corrupt journal rejects', () => assert.throws(() => policy.readJournal('{')));
test('invalid pending shape rejects', () => assert.throws(() => policy.readJournal(JSON.stringify({...journal, pending: {}}))));
test('duplicate keys reject', () => assert.throws(() => policy.readJournal(JSON.stringify({...journal, pending: [command, command]}))));
test('unknown command rejects', () => assert.throws(() => policy.readJournal(JSON.stringify({...journal, pending: [{...command, operation: 'approve'}]}))));
test('submit must be last', () => assert.throws(() => policy.readJournal(JSON.stringify({...journal, pending: [{...command, operation: 'submit'}, {...command, key: 'second'}]}))));
test('verified device write', () => { const s = storage(); const raw = policy.durableWrite(s, 'key', journal, null); assert.equal(s.getItem('key'), raw); });
test('quota failure is not saved', () => assert.throws(() => policy.durableWrite({getItem: () => null, setItem: () => {throw Error('quota');}}, 'key', journal, null)));
test('other-tab update never overwritten', () => { const s = storage(); s.setItem('key', 'other'); assert.throws(() => policy.durableWrite(s, 'key', journal, null)); assert.equal(s.getItem('key'), 'other'); });
test('readback failure rejects acknowledgement', () => assert.throws(() => policy.durableWrite({getItem: () => null, setItem: () => {}}, 'key', journal, null)));
test('missing server acknowledgement preserves commands', () => { assert.throws(() => policy.acknowledgedState(server, [command], [])); assert.equal(journal.pending[0].key, 'original-key'); });
test('wrong acknowledgement rejects', () => assert.throws(() => policy.acknowledgedState(server, [command], ['different'])));
test('exact acknowledgement clears only confirmed batch', () => assert.equal(policy.acknowledgedState(server, [command], ['original-key']).pending.length, 0));
test('lost response restores immutable replay', () => { const restored = restoreCourtCache(server, journal); assert.equal(restored.pending[0].key, command.key); assert.equal(restored.match.revision, 0); });
test('approved after lost response still allows receipt replay', () => { const restored = restoreCourtCache({...server, signature: 'approved', result_state: 'approved'}, {...journal, pending: [{...command, operation: 'submit'}]}); assert.equal(restored.conflict, false); });
test('dirty changed context never silently overwrites', () => { const restored = restoreCourtCache({...server, revision: 2}, {...journal, pending: [], dirty: true}); assert.equal(restored.conflict, true); assert.equal(restored.draft.home, 2); });
test('clean cache prefers server', () => assert.equal(restoreCourtCache({...server, payload: {home: 9}}, {...journal, pending: []}).draft.home, 9));
for (const [state, expected] of [[{storageFailed: true}, 'memory'], [{pending: [{operation: 'submit'}]}, 'submission_pending'], [{dirty: true}, 'device'], [{match: server}, 'synchronised'], [{match: {...server, result_state: 'submitted'}}, 'submitted'], [{match: {...server, result_state: 'verified'}}, 'verified'], [{match: {...server, result_state: 'approved'}}, 'approved'], [{match: {...server, submitted: true, result_state: 'contested'}}, 'contested']]) {
 test('save status ' + expected, () => assert.equal(policy.saveState(state), expected));
}
test('next current match', () => { const queue = [{id: 1, result_state: 'approved'}, {id: 2, result_state: 'draft', start: '2026-11-03 10:00:00', end: '2026-11-03 10:30:00'}]; assert.equal(policy.nextMatch(queue, Date.parse('2026-11-03T10:10:00Z')).id, 2); });
console.log(`${count} recovery policy cases passed; no live browser or server qualification implied.`);
