import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

function stableValue(value) {
    if (Array.isArray(value)) {
        return value.map(stableValue);
    }
    if (value && typeof value === "object") {
        return Object.fromEntries(
            Object.keys(value)
                .sort()
                .map((key) => [key, stableValue(value[key])])
        );
    }
    return value;
}

function fingerprint(value) {
    return createHash("sha256")
        .update(JSON.stringify(stableValue(value)))
        .digest("hex");
}

function requireNonEmptyString(value, label) {
    if (typeof value !== "string" || !value.trim()) {
        throw new Error(`${label} must be a non-empty string.`);
    }
}

function splitIntoChunks(items, size) {
    const chunks = [];
    for (let index = 0; index < items.length; index += size) {
        chunks.push(items.slice(index, index + size));
    }
    return chunks;
}

export class OdooJsonRpc {
    constructor(page) {
        if (!page || typeof page.evaluate !== "function") {
            throw new Error("OdooJsonRpc requires a Playwright page.");
        }
        this.page = page;
        this.requestId = 0;
    }

    async call(route, params = {}) {
        requireNonEmptyString(route, "route");
        const payload = {
            jsonrpc: "2.0",
            method: "call",
            params,
            id: ++this.requestId,
        };
        const response = await this.page.evaluate(
            async ({ target, body }) => {
                const result = await fetch(target, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(body),
                });
                const text = await result.text();
                let data;
                try {
                    data = JSON.parse(text);
                } catch {
                    throw new Error(
                        `JSON-RPC ${target} returned HTTP ${result.status}: ${text.slice(0, 500)}`
                    );
                }
                if (!result.ok) {
                    throw new Error(
                        `JSON-RPC ${target} returned HTTP ${result.status}: ${JSON.stringify(data)}`
                    );
                }
                return data;
            },
            { target: route, body: payload }
        );
        if (response.error) {
            const detail =
                response.error.data?.message ||
                response.error.data?.debug ||
                response.error.message ||
                JSON.stringify(response.error);
            throw new Error(`JSON-RPC ${route} failed: ${detail}`);
        }
        return response.result;
    }

    async callKw(model, method, args = [], kwargs = {}) {
        requireNonEmptyString(model, "model");
        requireNonEmptyString(method, "method");
        return this.call(`/web/dataset/call_kw/${model}/${method}`, {
            model,
            method,
            args,
            kwargs,
        });
    }

    async callRecordAction(model, method, recordIds, { chunkSize = 50, kwargs = {} } = {}) {
        if (!/^action_[a-z0-9_]+$/.test(method)) {
            throw new Error(
                `Only public Odoo action methods are accepted, received ${method}.`
            );
        }
        const ids = [...new Set(recordIds.map(Number))].filter(Number.isInteger);
        const results = [];
        for (const chunk of splitIntoChunks(ids, chunkSize)) {
            results.push(await this.callKw(model, method, [chunk], kwargs));
        }
        return results;
    }

    async searchRead(model, domain, fields, { limit = 0, order = "id" } = {}) {
        return this.callKw(model, "search_read", [], {
            domain,
            fields,
            limit,
            order,
        });
    }
}

export class JsonEvidenceStore {
    constructor(path) {
        requireNonEmptyString(path, "evidence path");
        this.path = path;
    }

    async load() {
        try {
            return JSON.parse(await readFile(this.path, "utf8"));
        } catch (error) {
            if (error.code === "ENOENT") {
                return { version: 1, confirmations: {}, runs: [] };
            }
            throw error;
        }
    }

    async save(evidence) {
        await mkdir(dirname(this.path), { recursive: true });
        await writeFile(this.path, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
    }
}

export class ConfirmedTaskRunner {
    constructor({
        page,
        evidencePath = "artifacts/agent-simulation/evidence.json",
        confirmationRuns = 2,
        implementationRevision = process.env.GIT_COMMIT || "working-tree",
    }) {
        if (!Number.isInteger(confirmationRuns) || confirmationRuns < 1) {
            throw new Error("confirmationRuns must be a positive integer.");
        }
        this.page = page;
        this.rpc = new OdooJsonRpc(page);
        this.store = new JsonEvidenceStore(evidencePath);
        this.confirmationRuns = confirmationRuns;
        this.implementationRevision = implementationRevision;
    }

    async confirmAndComplete({
        key,
        items,
        uiAction,
        fastAction,
        verifyItem,
        verifyBatch,
        taskInputs = {},
        itemKey = (item) => item.id ?? item,
        confirmationRuns = this.confirmationRuns,
    }) {
        requireNonEmptyString(key, "task key");
        if (!Array.isArray(items)) {
            throw new Error("items must be an array.");
        }
        if (typeof uiAction !== "function" || typeof fastAction !== "function") {
            throw new Error("uiAction and fastAction are required functions.");
        }
        if (typeof verifyItem !== "function" || typeof verifyBatch !== "function") {
            throw new Error("verifyItem and verifyBatch are required functions.");
        }

        const itemKeys = items.map(itemKey);
        const taskFingerprint = fingerprint({
            key,
            implementationRevision: this.implementationRevision,
            taskInputs,
        });
        const evidence = await this.store.load();
        const confirmation = evidence.confirmations[taskFingerprint] || {
            key,
            implementationRevision: this.implementationRevision,
            taskInputs,
            confirmedItemKeys: [],
        };
        const alreadyConfirmed = new Set(confirmation.confirmedItemKeys);
        const requiredConfirmationCount = Math.min(confirmationRuns, items.length);
        const freshConfirmationItems = [];
        for (const item of items) {
            if (alreadyConfirmed.size + freshConfirmationItems.length >= requiredConfirmationCount) {
                break;
            }
            const currentKey = itemKey(item);
            if (!alreadyConfirmed.has(currentKey)) {
                freshConfirmationItems.push(item);
            }
        }

        const run = {
            key,
            fingerprint: taskFingerprint,
            implementationRevision: this.implementationRevision,
            startedAt: new Date().toISOString(),
            itemCount: items.length,
            uiConfirmedItemKeys: [],
            acceleratedItemKeys: [],
            status: "running",
        };
        evidence.runs.push(run);

        try {
            for (const item of freshConfirmationItems) {
                const currentKey = itemKey(item);
                await uiAction(item, { page: this.page, rpc: this.rpc, currentKey });
                await verifyItem(item, { page: this.page, rpc: this.rpc, currentKey });
                alreadyConfirmed.add(currentKey);
                run.uiConfirmedItemKeys.push(currentKey);
            }

            if (alreadyConfirmed.size < requiredConfirmationCount) {
                throw new Error(
                    `${key} has ${alreadyConfirmed.size}/${requiredConfirmationCount} required UI confirmations.`
                );
            }

            confirmation.confirmedItemKeys = [...alreadyConfirmed];
            confirmation.confirmedAt = new Date().toISOString();
            evidence.confirmations[taskFingerprint] = confirmation;
            await this.store.save(evidence);

            const confirmedKeys = new Set(confirmation.confirmedItemKeys);
            const remainingItems = items.filter((item) => !confirmedKeys.has(itemKey(item)));
            if (remainingItems.length) {
                await fastAction(remainingItems, {
                    page: this.page,
                    rpc: this.rpc,
                    itemKeys: remainingItems.map(itemKey),
                });
                await verifyBatch(remainingItems, {
                    page: this.page,
                    rpc: this.rpc,
                    itemKeys: remainingItems.map(itemKey),
                });
                run.acceleratedItemKeys = remainingItems.map(itemKey);
            }
            run.status = "passed";
            run.completedAt = new Date().toISOString();
            await this.store.save(evidence);
            return run;
        } catch (error) {
            run.status = "failed";
            run.completedAt = new Date().toISOString();
            run.error = error instanceof Error ? error.message : String(error);
            await this.store.save(evidence);
            throw error;
        }
    }

    async confirmRecordAction({
        key,
        model,
        recordIds,
        actionMethod,
        stateField,
        expectedState,
        uiAction,
        taskInputs = {},
        confirmationRuns = this.confirmationRuns,
        chunkSize = 50,
    }) {
        const items = recordIds.map((id) => ({ id: Number(id) }));
        const acceptedStates = Array.isArray(expectedState)
            ? expectedState
            : [expectedState];
        const assertStates = async (selectedItems, { rpc }) => {
            const ids = selectedItems.map((item) => item.id);
            const rows = await rpc.searchRead(
                model,
                [["id", "in", ids]],
                ["id", stateField]
            );
            const byId = new Map(rows.map((row) => [row.id, row[stateField]]));
            const invalid = ids.filter(
                (id) => !byId.has(id) || !acceptedStates.includes(byId.get(id))
            );
            if (invalid.length) {
                throw new Error(
                    `${key} verification failed for record IDs: ${invalid.join(", ")}`
                );
            }
        };

        return this.confirmAndComplete({
            key,
            items,
            itemKey: (item) => item.id,
            confirmationRuns,
            taskInputs: {
                ...taskInputs,
                model,
                actionMethod,
                stateField,
                expectedState: acceptedStates,
            },
            uiAction,
            fastAction: async (remaining, { rpc }) =>
                rpc.callRecordAction(
                    model,
                    actionMethod,
                    remaining.map((item) => item.id),
                    { chunkSize }
                ),
            verifyItem: async (item, context) => assertStates([item], context),
            verifyBatch: assertStates,
        });
    }
}

export { fingerprint as taskFingerprint };
