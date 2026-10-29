/** @odoo-module **/
// Session navigation contains only allowlisted routes/filters and a user ID, never form data.
const returnPaths = new Set(['/my/work', '/my/action-items', '/my/referee-assignments']);
const filters = {scope: new Set(['my', 'club']), status: new Set(['open', 'recent']), task_type: new Set(['registration', 'roster_readiness', 'parental_consent', 'gameday_lineup', 'referee_duty', 'result_review'])};
const ttl = 2 * 60 * 60 * 1000;
function safeReturn(value) {
    if (typeof value !== "string" || value.startsWith("//") || /[\\%\r\n]/.test(value)) return null;
    try {
        const url = new URL(value, location.origin);
        if (url.origin !== location.origin || !returnPaths.has(url.pathname)) return null;
        const result = new URL(url.pathname, location.origin);
        for (const [key, allowed] of Object.entries(filters)) {
            const value = url.searchParams.get(key);
            if (allowed.has(value)) result.searchParams.set(key, value);
        }
        return result.pathname + result.search;
    } catch { return null; }
}
function storage(fn) { try { return fn(sessionStorage); } catch { return null; } }
async function init() {
    let user = document.querySelector('[data-journey-user]')?.dataset.journeyUser;
    // Existing detail pages carry user identity via the portal layout extension below.
    if (!user && location.pathname.startsWith('/my/')) {
        try {
            const response = await fetch('/my/work/context', {credentials: 'same-origin', cache: 'no-store'});
            if (response.ok) user = String((await response.json()).user_id || '');
        } catch { return; }
    }
    if (!user) return;
    const key = `federation:journey-return:${user}`;
    if (returnPaths.has(location.pathname)) {
        storage(s => s.removeItem(key));
        document.querySelectorAll('a[data-journey-open], a[href^="/my/referee-assignments/"]').forEach(link => {
            link.addEventListener('click', () => {
                const target = new URL(link.href, location.origin);
                if (target.origin !== location.origin) return;
                const path = safeReturn(location.href);
                if (path) storage(s => s.setItem(key, JSON.stringify({path, saved: Date.now()})));
            });
        });
        return;
    }
    if (!location.pathname.startsWith('/my/')) return;
    let record;
    try { record = JSON.parse(storage(s => s.getItem(key)) || 'null'); } catch { storage(s => s.removeItem(key)); }
    const path = record && safeReturn(record.path);
    if (!path || !Number.isFinite(record.saved) || Date.now() - record.saved > ttl || record.saved > Date.now() + 60000) { storage(s => s.removeItem(key)); return; }
    const main = document.querySelector('main .container, #wrap .container, main');
    if (!main) return;
    const link = document.createElement('a'); link.href = path;
    link.className = 'btn btn-outline-secondary my-3'; link.textContent = 'Back to my work';
    main.prepend(link);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
