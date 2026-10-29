/** @odoo-module **/
const selector = "form[data-qol-draft-guard='1']";
const allowed = /^(home_score|away_score|squad_player_ids|player_\d+_(role|captain|jersey)|roster_id)$/;
const ttl = 24 * 60 * 60 * 1000;
const dirty = new Set();
const prefix = "federation:draft:";
const pendingKey = `${prefix}pending`;
function storage(operation) { try { return operation(sessionStorage); } catch { return null; } }
function key(form) {
    if (!form.dataset.draftUser) return null;
    return `${prefix}${form.dataset.draftUser}:${location.pathname}:${new URL(form.action, location.href).pathname}`;
}
function controls(form) {
    return [...form.elements].filter(el => allowed.test(el.name) && !el.disabled && !["file", "password", "hidden"].includes(el.type));
}
function save(form) {
    const id = key(form);
    if (!id) return;
    const values = controls(form).map(el => ({ name: el.name, value: el.value, checked: el.checked }));
    storage(s => s.setItem(id, JSON.stringify({ saved: Date.now(), values })));
}
function init() {
    const pending = storage(s => s.getItem(pendingKey));
    if (pending && document.querySelector(".alert-success") && (document.querySelector("[data-draft-user]")?.dataset.draftUser) && pending.startsWith(`${prefix}${document.querySelector("[data-draft-user]").dataset.draftUser}:`)) {
        storage(s => { s.removeItem(pending); s.removeItem(pendingKey); });
    }
    document.querySelectorAll(selector).forEach(form => {
        const id = key(form);
        if (!id) return;
        let draft;
        try { draft = JSON.parse(storage(s => s.getItem(id)) || "null"); } catch { storage(s => s.removeItem(id)); }
        if (!draft) return;
        if (!Array.isArray(draft.values) || Date.now() - draft.saved > ttl) { storage(s => s.removeItem(id)); return; }
        const banner = document.createElement("div");
        banner.className = "alert alert-info";
        banner.setAttribute("role", "status");
        banner.textContent = "An unfinished lineup is available in this browser tab. Names, free text and files are not saved. ";
        for (const [label, restore] of [["Restore draft", true], ["Discard draft", false]]) {
            const button = document.createElement("button");
            button.type = "button"; button.className = "btn btn-sm btn-outline-primary me-2"; button.textContent = label;
            button.addEventListener("click", () => {
                if (restore) {
                    const fields = controls(form);
                    draft.values.forEach(value => fields.filter(el => el.name === value.name && (!['checkbox', 'radio'].includes(el.type) || el.value === value.value)).forEach(el => {
                        if (["checkbox", "radio"].includes(el.type)) el.checked = Boolean(value.checked);
                        else el.value = value.value;
                        el.dispatchEvent(new Event("change", { bubbles: true }));
                    }));
                    dirty.add(form);
                } else storage(s => s.removeItem(id));
                banner.remove();
            });
            banner.append(button);
        }
        form.prepend(banner);
    });
}
document.addEventListener("input", event => { const form = event.target.closest(selector); if (form) { dirty.add(form); save(form); } });
document.addEventListener("change", event => { const form = event.target.closest(selector); if (form) { dirty.add(form); save(form); } });
document.addEventListener("submit", event => {
    const form = event.target;
    if (form.matches(selector)) {
        save(form); dirty.delete(form);
        const id = key(form); if (id) storage(s => s.setItem(pendingKey, id));
    }
});
window.addEventListener("beforeunload", event => { if (dirty.size) { event.preventDefault(); event.returnValue = ""; } });
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
