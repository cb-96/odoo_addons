/** @odoo-module **/
export function destinationLabel(row) {
    if (!row) return 'Not assessed';
    if (!row.valid) return 'Blocked: mandatory rule';
    if (row.unchanged) return 'Current slot';
    return row.warnings.length ? 'Allowed: preference warning' : 'Allowed destination';
}
export function canApply(preview, reason) {
    return Boolean(preview && reason?.trim() && !preview.after.validation.errors.length);
}
export function comparable(first, second) {
    return Boolean(first && second && first.id !== second.id && first.signature === second.signature && first.revision === second.revision);
}
export function navigationTarget(cells, index, key) {
    if (!cells.length || index < 0) return index;
    if (key === 'Home') return 0;
    if (key === 'End') return cells.length - 1;
    const current = cells[index];
    const vertical = key === 'ArrowUp' || key === 'ArrowDown';
    const forward = key === 'ArrowDown' || key === 'ArrowRight';
    const axis = vertical ? 'row' : 'column';
    const fixed = vertical ? 'column' : 'row';
    const candidates = cells.map((cell, i) => ({...cell, index: i}))
        .filter(cell => cell[fixed] === current[fixed] && (forward ? cell[axis] > current[axis] : cell[axis] < current[axis]))
        .sort((a,b) => Math.abs(a[axis]-current[axis]) - Math.abs(b[axis]-current[axis]));
    return candidates[0]?.index ?? index;
}

export function formatEventTime(value, timezone = 'UTC', locale) {
    if (!value) return '';
    const raw = String(value).replace(' ', 'T');
    const instant = new Date(/[zZ]$|[+-]\d{2}:\d{2}$/.test(raw) ? raw : raw + 'Z');
    if (!Number.isFinite(instant.getTime())) return '';
    return new Intl.DateTimeFormat(locale, {
        timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).format(instant);
}
