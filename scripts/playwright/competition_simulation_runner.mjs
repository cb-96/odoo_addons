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

function requirePositiveInteger(value, label) {
    if (!Number.isSafeInteger(value) || value < 1) {
        throw new Error(`${label} must be a positive integer.`);
    }
}

function requirePublicActionMethod(method) {
    if (typeof method !== "string" || !/^action_[a-z0-9_]+$/.test(method)) {
        throw new Error(
            `Only public Odoo action methods are accepted, received ${String(method)}.`
        );
    }
}

function normalizeRecordIds(recordIds) {
    if (!Array.isArray(recordIds)) {
        throw new Error("recordIds must be an array.");
    }
    return recordIds.map((id) => {
        if (
            (typeof id !== "number" && typeof id !== "string") ||
            (typeof id === "string" && !id.trim())
        ) {
            throw new Error(`Invalid Odoo record ID: ${String(id)}.`);
        }
        const normalized = Number(id);
        if (!Number.isSafeInteger(normalized) || normalized < 1) {
            throw new Error(`Invalid Odoo record ID: ${String(id)}.`);
        }
        return normalized;
    });
}

function requireItemKeys(items, itemKey) {
    if (typeof itemKey !== "function") {
        throw new Error("itemKey must be a function.");
    }
    const keys = items.map(itemKey);
    const seen = new Set();
    for (const key of keys) {
        if (
            !((typeof key === "string" && key.trim()) ||
                (typeof key === "number" && Number.isSafeInteger(key)))
        ) {
            throw new Error("Each item must have a non-empty string or safe integer key.");
        }
        if (seen.has(key)) {
            throw new Error(`Duplicate task item key: ${String(key)}.`);
        }
        seen.add(key);
    }
    return keys;
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
        requireNonEmptyString(model, "model");
        requirePublicActionMethod(method);
        requirePositiveInteger(chunkSize, "chunkSize");
        const ids = [...new Set(normalizeRecordIds(recordIds))];
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
        requirePositiveInteger(confirmationRuns, "confirmationRuns");
        requireNonEmptyString(implementationRevision, "implementationRevision");
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
        isItemComplete,
        taskInputs = {},
        itemKey = (item) => item.id ?? item,
        confirmationRuns = this.confirmationRuns,
    }) {
        requireNonEmptyString(key, "task key");
        if (!Array.isArray(items)) {
            throw new Error("items must be an array.");
        }
        requirePositiveInteger(confirmationRuns, "confirmationRuns");
        if (typeof uiAction !== "function" || typeof fastAction !== "function") {
            throw new Error("uiAction and fastAction are required functions.");
        }
        if (typeof verifyItem !== "function" || typeof verifyBatch !== "function") {
            throw new Error("verifyItem and verifyBatch are required functions.");
        }
        if (typeof isItemComplete !== "function") {
            throw new Error("isItemComplete is required to make retries safe.");
        }

        const itemKeys = requireItemKeys(items, itemKey);
        const completedItemKeys = [];
        const pendingItems = [];
        for (const item of items) {
            const currentKey = itemKey(item);
            const complete = await isItemComplete(item, {
                page: this.page,
                rpc: this.rpc,
                currentKey,
                phase: "inspect",
            });
            if (typeof complete !== "boolean") {
                throw new Error("isItemComplete must return a boolean.");
            }
            (complete ? completedItemKeys : pendingItems).push(
                complete ? currentKey : item
            );
        }
        const taskFingerprint = fingerprint({
            key,
            implementationRevision: this.implementationRevision,
            taskInputs,
            itemKeys,
            completedItemKeys,
        });
        const evidence = await this.store.load();
        const confirmation = evidence.confirmations[taskFingerprint] || {
            key,
            implementationRevision: this.implementationRevision,
            taskInputs,
            confirmedItemKeys: [],
        };
        const pendingItemKeys = pendingItems.map(itemKey);
        const targetKeys = new Set(pendingItemKeys);
        const alreadyConfirmed = new Set(
            confirmation.confirmedItemKeys.filter((itemKeyValue) =>
                targetKeys.has(itemKeyValue)
            )
        );
        const requiredConfirmationCount = Math.min(
            confirmationRuns,
            pendingItems.length
        );
        const freshConfirmationItems = [];
        for (const item of pendingItems) {
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
            completedItemKeys,
            uiConfirmedItemKeys: [],
            acceleratedItemKeys: [],
            status: "running",
        };
        evidence.runs.push(run);
        let fastActionItems = [];

        const reportFastActionProgress = async (completedKeys) => {
            if (!Array.isArray(completedKeys)) {
                throw new Error("Fast-action progress must be an array of item keys.");
            }
            const expectedKeys = new Set(
                fastActionItems.map((item) => itemKey(item))
            );
            const reportedKeys = requireItemKeys(
                completedKeys,
                (completedKey) => completedKey
            );
            const unexpectedKeys = reportedKeys.filter(
                (completedKey) => !expectedKeys.has(completedKey)
            );
            if (unexpectedKeys.length) {
                throw new Error(
                    `Fast-action progress included unexpected item keys: ${unexpectedKeys.join(", ")}.`
                );
            }
            run.acceleratedItemKeys = [
                ...new Set([...run.acceleratedItemKeys, ...reportedKeys]),
            ];
            await this.store.save(evidence);
        };

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

            confirmation.confirmedItemKeys = pendingItemKeys.filter((itemKeyValue) =>
                alreadyConfirmed.has(itemKeyValue)
            );
            confirmation.confirmedAt = new Date().toISOString();
            evidence.confirmations[taskFingerprint] = confirmation;
            await this.store.save(evidence);

            const confirmedKeys = new Set(confirmation.confirmedItemKeys);
            const remainingItems = pendingItems.filter(
                (item) => !confirmedKeys.has(itemKey(item))
            );
            if (remainingItems.length) {
                fastActionItems = remainingItems;
                await fastAction(remainingItems, {
                    page: this.page,
                    rpc: this.rpc,
                    itemKeys: remainingItems.map(itemKey),
                    reportProgress: reportFastActionProgress,
                });
                await verifyBatch(remainingItems, {
                    page: this.page,
                    rpc: this.rpc,
                    itemKeys: remainingItems.map(itemKey),
                });
                run.acceleratedItemKeys = [
                    ...new Set([
                        ...run.acceleratedItemKeys,
                        ...remainingItems.map(itemKey),
                    ]),
                ];
            }
            run.status = "passed";
            run.completedAt = new Date().toISOString();
            await this.store.save(evidence);
            return run;
        } catch (error) {
            const recoveredKeys = [];
            const reconciliationErrors = [];
            const knownCompletedKeys = new Set(run.acceleratedItemKeys);
            for (const item of fastActionItems) {
                const currentKey = itemKey(item);
                if (knownCompletedKeys.has(currentKey)) {
                    continue;
                }
                try {
                    if (
                        await isItemComplete(item, {
                            page: this.page,
                            rpc: this.rpc,
                            currentKey,
                            phase: "reconcile",
                        })
                    ) {
                        recoveredKeys.push(currentKey);
                    }
                } catch (reconciliationError) {
                    reconciliationErrors.push(
                        `${String(currentKey)}: ${reconciliationError instanceof Error ? reconciliationError.message : String(reconciliationError)}`
                    );
                }
            }
            run.acceleratedItemKeys = [
                ...new Set([...run.acceleratedItemKeys, ...recoveredKeys]),
            ];
            run.recoveredAfterFailureItemKeys = recoveredKeys;
            if (reconciliationErrors.length) {
                run.reconciliationErrors = reconciliationErrors;
            }
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
        sourceStates,
        uiAction,
        taskInputs = {},
        confirmationRuns = this.confirmationRuns,
        chunkSize = 50,
    }) {
        requireNonEmptyString(key, "task key");
        requireNonEmptyString(model, "model");
        requirePublicActionMethod(actionMethod);
        requireNonEmptyString(stateField, "stateField");
        requirePositiveInteger(confirmationRuns, "confirmationRuns");
        requirePositiveInteger(chunkSize, "chunkSize");
        const ids = normalizeRecordIds(recordIds);
        if (new Set(ids).size !== ids.length) {
            throw new Error("recordIds must not contain duplicates.");
        }
        const items = ids.map((id) => ({ id }));
        const acceptedStates = Array.isArray(expectedState)
            ? expectedState
            : [expectedState];
        const allowedSourceStates = Array.isArray(sourceStates)
            ? sourceStates
            : [sourceStates];
        if (
            acceptedStates.length === 0 ||
            acceptedStates.some((state) => typeof state !== "string" || !state.trim())
        ) {
            throw new Error("expectedState must contain at least one non-empty state.");
        }
        if (
            allowedSourceStates.length === 0 ||
            allowedSourceStates.some((state) => typeof state !== "string" || !state.trim())
        ) {
            throw new Error("sourceStates must contain at least one non-empty state.");
        }

        const initialRows = ids.length
            ? await this.rpc.searchRead(model, [["id", "in", ids]], ["id", stateField])
            : [];
        const initialStates = new Map(
            initialRows.map((row) => [row.id, row[stateField]])
        );
        const missingIds = ids.filter((id) => !initialStates.has(id));
        if (missingIds.length) {
            throw new Error(
                `${key} could not read record IDs: ${missingIds.join(", ")}`
            );
        }
        const pendingItems = items.filter((item) => {
            const currentState = initialStates.get(item.id);
            return !acceptedStates.includes(currentState);
        });
        const invalidStates = pendingItems.filter(
            (item) => !allowedSourceStates.includes(initialStates.get(item.id))
        );
        if (invalidStates.length) {
            const details = invalidStates
                .map((item) => `${item.id} (${initialStates.get(item.id)})`)
                .join(", ");
            throw new Error(`${key} found records outside sourceStates: ${details}.`);
        }
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
            isItemComplete: async (item, { rpc, phase }) => {
                if (phase === "reconcile") {
                    const rows = await rpc.searchRead(
                        model,
                        [["id", "=", item.id]],
                        ["id", stateField],
                        { limit: 1 }
                    );
                    return rows.length > 0 && acceptedStates.includes(rows[0][stateField]);
                }
                return acceptedStates.includes(initialStates.get(item.id));
            },
            taskInputs: {
                ...taskInputs,
                model,
                actionMethod,
                stateField,
                expectedState: acceptedStates,
                sourceStates: allowedSourceStates,
                recordStates: items.map((item) => [
                    item.id,
                    initialStates.get(item.id),
                ]),
            },
            uiAction,
            fastAction: async (remaining, { rpc, reportProgress }) => {
                for (const chunk of splitIntoChunks(remaining, chunkSize)) {
                    await rpc.callRecordAction(
                        model,
                        actionMethod,
                        chunk.map((item) => item.id),
                        { chunkSize }
                    );
                    await assertStates(chunk, { rpc });
                    await reportProgress(chunk.map((item) => item.id));
                }
            },
            verifyItem: async (item, context) => assertStates([item], context),
            verifyBatch: assertStates,
        });
    }
}

export { fingerprint as taskFingerprint };
