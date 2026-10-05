import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
    ConfirmedTaskRunner,
    OdooJsonRpc,
    taskFingerprint,
} from "./competition_simulation_runner.mjs";

class FakePage {
    constructor(handler = async () => ({ result: true })) {
        this.handler = handler;
        this.calls = [];
    }

    async evaluate(_callback, input) {
        this.calls.push(input);
        return this.handler(input);
    }
}

test("fingerprints ignore object key order", () => {
    assert.equal(
        taskFingerprint({ b: 2, a: { d: 4, c: 3 } }),
        taskFingerprint({ a: { c: 3, d: 4 }, b: 2 })
    );
});

test("Odoo RPC accepts public actions and rejects arbitrary methods", async () => {
    const page = new FakePage();
    const rpc = new OdooJsonRpc(page);
    await rpc.callRecordAction("federation.match", "action_submit_result", [3, 2, 3]);
    assert.deepEqual(page.calls[0].body.params.args, [[3, 2]]);
    await assert.rejects(
        () => rpc.callRecordAction("federation.match", "write", [2]),
        /Only public Odoo action methods/
    );
});

test("two UI confirmations unlock one accelerated batch", async () => {
    const directory = await mkdtemp(join(tmpdir(), "competition-simulation-"));
    const evidencePath = join(directory, "evidence.json");
    const page = new FakePage();
    const runner = new ConfirmedTaskRunner({
        page,
        evidencePath,
        implementationRevision: "abc123",
    });
    const ui = [];
    const fast = [];
    const verified = [];

    const result = await runner.confirmAndComplete({
        key: "result-submit",
        items: [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }],
        taskInputs: { policy: "custom" },
        uiAction: async (item) => ui.push(item.id),
        fastAction: async (items) => fast.push(items.map((item) => item.id)),
        verifyItem: async (item) => verified.push(item.id),
        verifyBatch: async (items) => verified.push(...items.map((item) => item.id)),
    });

    assert.deepEqual(ui, [1, 2]);
    assert.deepEqual(fast, [[3, 4]]);
    assert.deepEqual(verified, [1, 2, 3, 4]);
    assert.equal(result.status, "passed");

    const evidence = JSON.parse(await readFile(evidencePath, "utf8"));
    assert.equal(evidence.runs.at(-1).status, "passed");
    assert.deepEqual(evidence.runs.at(-1).acceleratedItemKeys, [3, 4]);
});

test("a changed implementation revision requires fresh UI confirmation", async () => {
    const directory = await mkdtemp(join(tmpdir(), "competition-simulation-"));
    const evidencePath = join(directory, "evidence.json");
    const items = [{ id: 1 }, { id: 2 }, { id: 3 }];
    const counts = { first: 0, second: 0 };

    for (const [revision, counter] of [["one", "first"], ["two", "second"]]) {
        const runner = new ConfirmedTaskRunner({
            page: new FakePage(),
            evidencePath,
            implementationRevision: revision,
        });
        await runner.confirmAndComplete({
            key: "approve-result",
            items,
            uiAction: async () => counts[counter]++,
            fastAction: async () => {},
            verifyItem: async () => {},
            verifyBatch: async () => {},
        });
    }

    assert.deepEqual(counts, { first: 2, second: 2 });
});

test("a failed fast path remains failed evidence", async () => {
    const directory = await mkdtemp(join(tmpdir(), "competition-simulation-"));
    const evidencePath = join(directory, "evidence.json");
    const runner = new ConfirmedTaskRunner({
        page: new FakePage(),
        evidencePath,
        implementationRevision: "abc123",
        confirmationRuns: 1,
    });

    await assert.rejects(
        () =>
            runner.confirmAndComplete({
                key: "freeze-stage",
                items: [{ id: 1 }, { id: 2 }],
                uiAction: async () => {},
                fastAction: async () => {
                    throw new Error("backend guard rejected the batch");
                },
                verifyItem: async () => {},
                verifyBatch: async () => {},
            }),
        /backend guard rejected/
    );

    const evidence = JSON.parse(await readFile(evidencePath, "utf8"));
    assert.equal(evidence.runs.at(-1).status, "failed");
});
