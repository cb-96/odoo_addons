// Unit tests for the offline court app's pure logic (node --test).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const lib = join(here, "../../sports_federation_live_workspace/static/court_app/lib");
const policy = await import(join(lib, "policy.js"));
const journalLib = await import(join(lib, "journal.js"));
const { syncJournal, refreshPack } = await import(join(lib, "sync.js"));
const { ApiError, NetworkError } = await import(join(lib, "api.js"));

const cases = JSON.parse(readFileSync(join(here, "../fixtures/court_scoring_cases.json"), "utf8")).cases;

for (const item of cases) {
    test(`scoring parity: ${item.name}`, () => {
        const scoring = { mode: item.mode, set_target: item.set_target, set_points: item.set_points, max_periods: item.max_periods };
        const problems = policy.draftProblems(item.payload, scoring, item.complete);
        assert.equal(problems.length === 0, item.valid, problems.join(" | "));
    });
}

test("set points: won 2, drawn 1 each, lost 0", () => {
    assert.deepEqual(policy.setPoints({ home: 2, away: 2 }, 2, 1), [1, 1]);
    assert.deepEqual(policy.setPoints({ home: 3, away: 1 }, 2, 1), [2, 0]);
    assert.deepEqual(policy.totals([{ home: 3, away: 0 }, { home: 2, away: 2 }, { home: 1, away: 4 }], { mode: "sets", set_points: [2, 1] }), { home: 3, away: 3 });
});

const packMatch = (overrides = {}) => ({
    id: 7,
    name: "A - B",
    result_state: "draft",
    signature: "s".repeat(64),
    lineups: [{ sheet_id: 11, side: "home", limit: 12, state: "submitted", players: [{ id: 1, crossed_out: false }, { id: 2, crossed_out: true }] }],
    capture: { revision: 3, payload: { home: 0, away: 0, periods: [], outcome: "normal", reason: "", zero_confirmed: false }, match_log: [], submitted: false, closed: false, device_id: false },
    ...overrides,
});

test("journal: capture commands count from the confirmed revision", () => {
    let journal = journalLib.newJournal(packMatch(), 5);
    assert.deepEqual(journal.crossed, { 11: [2] });
    journal = journalLib.queueCapture(journal, "save");
    journal = journalLib.queueSide({ ...journal, crossed: { 11: [1, 2] } }, "participation");
    journal = journalLib.queueCapture(journal, "submit", { method: "self" });
    const capture = journalLib.capturePending(journal);
    assert.deepEqual(capture.map((c) => c.revision), [3, 4]);
    assert.equal(capture[1].confirmation.method, "self");
    assert.ok(journalLib.isLocked(journal));
    assert.throws(() => journalLib.queueCapture(journal, "save"), /already submitted/);
});

test("journal: an unsent side command is replaced by the newer full state", () => {
    let journal = journalLib.newJournal(packMatch(), 5);
    journal = journalLib.queueSide({ ...journal, log: [{ type: "timeout", side: "home" }] }, "log");
    journal = journalLib.queueSide({ ...journal, log: [] }, "log");
    assert.equal(journal.pending.length, 1);
    assert.deepEqual(journal.pending[0].payload, { events: [] });
});

test("journal: acknowledgement renumbers commands that were not sent", () => {
    let journal = journalLib.newJournal(packMatch(), 5);
    journal = journalLib.queueCapture(journal, "save");
    const sent = journal.pending.map((c) => c.key);
    journal = journalLib.queueCapture({ ...journal, draft: { ...journal.draft, home: 1 } }, "save");
    const current = { revision: 4, signature: "s".repeat(64), payload: journal.draft, result_state: "draft", submitted: false, closed: false, device_id: 9, this_device: true };
    const next = journalLib.applyAck(journal, current, sent, sent);
    assert.equal(next.pending.length, 1);
    assert.equal(next.pending[0].revision, 4);
    assert.equal(next.base.revision, 4);
    assert.throws(() => journalLib.applyAck(journal, current, [], sent), /did not confirm/);
});

test("journal: a changed match keeps unsent scores and raises a conflict", () => {
    let journal = journalLib.queueCapture(journalLib.newJournal(packMatch(), 5), "save");
    journal = journalLib.refreshFromPack(journal, packMatch({ signature: "t".repeat(64) }));
    assert.equal(journal.pending.length, 1);
    assert.equal(journal.conflict.code, "changed");
    const clean = journalLib.refreshFromPack(journalLib.newJournal(packMatch(), 5), packMatch({ capture: { ...packMatch().capture, revision: 8 } }));
    assert.equal(clean.base.revision, 8);
});

test("journal: take-over rebases queued commands on the server state", () => {
    let journal = journalLib.queueCapture(journalLib.newJournal(packMatch(), 5), "save");
    journal = journalLib.markConflict(journal, "being scored on another phone");
    const next = journalLib.rebase(journal, { revision: 6, signature: "u".repeat(64), result_state: "draft", submitted: false, closed: false, device_id: 3, this_device: true });
    assert.equal(next.conflict, null);
    assert.equal(next.pending[0].revision, 6);
    assert.equal(next.pending[0].signature, "u".repeat(64));
});

test("journal: invalid journals are rejected", () => {
    assert.throws(() => journalLib.validateJournal({ draft: {}, pending: [{ key: "a", operation: "drop" }] }), /Invalid unsent change/);
    const journal = journalLib.newJournal(packMatch(), 5);
    journal.pending = [{ key: "a1234567", operation: "submit" }, { key: "b1234567", operation: "save" }];
    assert.throws(() => journalLib.validateJournal(journal), /submission must be the last/);
});

test("journal: backend court app journals are found and adopted", () => {
    const items = {
        "sf-court:v1:db:2:4:9:7": JSON.stringify({ draft: { home: 3 }, pending: [{ key: "legacy-key-1", revision: 3, operation: "save", payload: { home: 3 }, signature: "x".repeat(64) }] }),
        "sf-court:v1:db:2:last": "{}",
        "sf-court:v1:db:3:4:9:8": JSON.stringify({ draft: {}, pending: [{ key: "other" }] }),
    };
    const storage = { length: 3, key: (i) => Object.keys(items)[i], getItem: (k) => items[k] };
    const found = journalLib.legacyJournals(storage, "db", 2);
    assert.equal(found.length, 1);
    assert.equal(found[0].match_id, 7);
    const adopted = journalLib.adoptLegacy(journalLib.newJournal(packMatch(), 5), found[0]);
    assert.equal(adopted.pending[0].key, "legacy-key-1");
    assert.equal(adopted.legacy_name, "sf-court:v1:db:2:4:9:7");
});

function fakeStore(initial = []) {
    const journals = new Map(initial.map((j) => [j.match_id, j]));
    const meta = new Map();
    let pack = null;
    return {
        journals: async () => [...journals.values()],
        journal: async (id) => journals.get(id),
        saveJournal: async (j) => { journals.set(j.match_id, JSON.parse(JSON.stringify(j))); },
        delete: async (_store, id) => { journals.delete(id); },
        pack: async () => pack,
        setPack: async (p) => { pack = p; },
        setMeta: async (k, v) => { meta.set(k, v); },
    };
}

test("sync: acknowledged changes leave the phone", async () => {
    const journal = journalLib.queueCapture(journalLib.newJournal(packMatch(), 5), "save");
    const store = fakeStore([journal]);
    const api = { sync: async (_id, commands) => ({ acknowledged_keys: commands.map((c) => c.key), current: { revision: 4, signature: "s".repeat(64), payload: journal.draft, match_log: [], result_state: "draft", submitted: false, closed: false, device_id: 1, this_device: true } }) };
    const result = await syncJournal(store, api, journal);
    assert.equal(result.sent, 1);
    assert.equal((await store.journal(7)).pending.length, 0);
});

test("sync: a refused change becomes a conflict, a network failure keeps it queued", async () => {
    const journal = journalLib.queueCapture(journalLib.newJournal(packMatch(), 5), "save");
    const store = fakeStore([journal]);
    const offline = await syncJournal(store, { sync: async () => { throw new NetworkError("down"); } }, journal);
    assert.ok(offline.offline);
    assert.equal((await store.journal(7)).conflict, null);
    const refused = await syncJournal(store, { sync: async () => { throw new ApiError("Conflict: schedule changed", 409, "conflict"); } }, journal);
    assert.match(refused.conflict, /schedule changed/);
    assert.equal((await store.journal(7)).pending.length, 1);
    const gone = await syncJournal(store, { sync: async () => { throw new ApiError("revoked", 401, "unauthorized"); } }, journal);
    assert.equal(gone.unauthorized, "revoked");
});

test("sync: a match removed from the pack keeps unsent scores as a conflict", async () => {
    const journal = journalLib.queueCapture(journalLib.newJournal(packMatch(), 5), "save");
    const store = fakeStore([journal]);
    await store.setPack({ pack_hash: "a", matches: [packMatch()], matchday: { id: 5 } });
    const result = await refreshPack(store, { pack: async () => ({ pack_hash: "b", matches: [], matchday: { id: 5 } }) });
    assert.equal(result.changes[0].type, "removed");
    assert.equal((await store.journal(7)).conflict.code, "removed");
});
