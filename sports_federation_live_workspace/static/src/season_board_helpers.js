/** @odoo-module **/
/* Pure helpers of the season match board; no Odoo services. */

export function timeLabel(value, timezone = "UTC", locale) {
    if (!value) {
        return "";
    }
    const raw = String(value).replace(" ", "T");
    const instant = new Date(/[zZ]$|[+-]\d{2}:\d{2}$/.test(raw) ? raw : raw + "Z");
    if (!Number.isFinite(instant.getTime())) {
        return "";
    }
    return new Intl.DateTimeFormat(locale, {
        timeZone: timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).format(instant);
}

export function dayLabel(value, locale) {
    if (!value) {
        return "";
    }
    const date = new Date(`${value}T12:00:00Z`);
    return new Intl.DateTimeFormat(locale, {weekday: "short", day: "numeric", month: "short", timeZone: "UTC"}).format(date);
}

/** Rows of a day grid: one per start time, one cell per court. */
export function gridRows(day) {
    const byStart = new Map();
    for (const slot of day.slots) {
        if (!byStart.has(slot.start)) {
            byStart.set(slot.start, {start: slot.start, end: slot.end, cells: {}});
        }
        byStart.get(slot.start).cells[slot.court_id] = slot;
    }
    return [...byStart.values()].sort((a, b) => (a.start < b.start ? -1 : 1));
}

export function matchesFilter(fixture, filters) {
    if (filters.division && fixture.division_id !== Number(filters.division)) {
        return false;
    }
    if (filters.stage && fixture.stage_id !== Number(filters.stage)) {
        return false;
    }
    if (filters.round && fixture.round !== Number(filters.round)) {
        return false;
    }
    const text = (filters.text || "").trim().toLowerCase();
    if (text && !`${fixture.home} ${fixture.away}`.toLowerCase().includes(text)) {
        return false;
    }
    return true;
}

/** Teams already busy at the same time on a day, for drop hints. */
export function clashes(fixture, slot, day, fixtures) {
    if (!fixture || !slot || !fixture.teams.length) {
        return false;
    }
    const slotById = new Map(day.slots.map((item) => [item.id, item]));
    return fixtures.some((other) => {
        if (other.id === fixture.id || other.day_id !== day.id || !other.slot_id) {
            return false;
        }
        const otherSlot = slotById.get(other.slot_id);
        if (!otherSlot || !(slot.start < otherSlot.end && otherSlot.start < slot.end)) {
            return false;
        }
        return other.teams.some((team) => fixture.teams.includes(team));
    });
}
