// Run with: node ci/test_court_journal_pruning.mjs
import assert from 'node:assert/strict';
import { pruneCleanJournals, CLEAN_JOURNAL_MAX_AGE_DAYS } from '../sports_federation_live_workspace/static/src/mobile_recovery.js';

class MemoryStorage {
    constructor(entries = {}) { this.map = new Map(Object.entries(entries)); }
    get length() { return this.map.size; }
    key(index) { return [...this.map.keys()][index] ?? null; }
    getItem(name) { return this.map.has(name) ? this.map.get(name) : null; }
    setItem(name, value) { this.map.set(name, String(value)); }
    removeItem(name) { this.map.delete(name); }
}

const DAY = 24 * 60 * 60 * 1000;
const now = Date.parse('2026-11-06T12:00:00Z');
const prefix = 'sf-court:v1:db:7:';
const journal = (values) => JSON.stringify({schema: 2, draft: {home: 1, away: 0}, pending: [], dirty: false,
    saved_at: new Date(now - 30 * DAY).toISOString(), ...values});
const command = {key: 'k1', revision: 1, operation: 'save', signature: 's', payload: {home: 1, away: 0}};

const storage = new MemoryStorage({
    [`${prefix}1:2:10`]: journal({}),                                           // old and clean: removed
    [`${prefix}1:2:11`]: journal({saved_at: new Date(now - DAY).toISOString()}),  // recent: kept
    [`${prefix}1:2:12`]: journal({pending: [command]}),                         // queued command: kept
    [`${prefix}1:2:13`]: journal({dirty: true}),                                // unsent edit: kept
    [`${prefix}1:2:14`]: '{not json',                                           // unreadable evidence: kept
    [`${prefix}1:2:15`]: journal({saved_at: 'unknown'}),                        // no usable date: kept
    [`${prefix}last`]: JSON.stringify({matchday_id: 1, court_id: 2, match_id: 10}),
    ['sf-court:v1:db:8:1:2:10']: journal({}),                                   // other user: untouched
});

const removed = pruneCleanJournals(storage, prefix, now);
assert.deepEqual(removed, [`${prefix}1:2:10`]);
for (const suffix of ['1:2:11', '1:2:12', '1:2:13', '1:2:14', '1:2:15', 'last']) {
    assert.notEqual(storage.getItem(`${prefix}${suffix}`), null, suffix);
}
assert.notEqual(storage.getItem('sf-court:v1:db:8:1:2:10'), null);
assert.equal(CLEAN_JOURNAL_MAX_AGE_DAYS, 14);
assert.deepEqual(pruneCleanJournals(storage, prefix, now), []);
console.log('court journal pruning: ok');
