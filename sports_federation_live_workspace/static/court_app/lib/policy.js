// Scoring rules the phone applies offline. The server (policy.py) stays the
// authority; ci/fixtures/court_scoring_cases.json is checked against both.

export const OUTCOMES = ["normal", "interrupted", "abandoned", "forfeit_home", "forfeit_away", "disputed"];
export const EXCEPTIONAL = new Set(["interrupted", "abandoned", "disputed"]);
const MAX_SCORE = 100000;

/** Points each team earns for one set: [home, away]. */
export function setPoints(period, win = 1, draw = 0) {
    if (period.home === period.away) return [draw, draw];
    return period.home > period.away ? [win, 0] : [0, win];
}

export function isDraw(period) {
    return period.home === period.away;
}

/** Match score from the periods: sum of set points (sets) or of scores. */
export function totals(periods, scoring) {
    const [win, draw] = scoring.set_points || [1, 0];
    let home = 0;
    let away = 0;
    for (const period of periods) {
        if (scoring.mode === "sets") {
            const [h, a] = setPoints(period, win, draw);
            home += h;
            away += a;
        } else {
            home += period.home;
            away += period.away;
        }
    }
    return { home, away };
}

function wonSets(periods) {
    return [
        periods.filter((p) => p.home > p.away).length,
        periods.filter((p) => p.away > p.home).length,
    ];
}

const isScore = (value) => Number.isInteger(value) && value >= 0 && value <= MAX_SCORE;

/**
 * Return the problems that would make the server refuse this draft.
 * ``complete`` is true for a submission.
 */
export function draftProblems(draft, scoring, complete) {
    const problems = [];
    const periods = Array.isArray(draft.periods) ? draft.periods : [];
    if (!OUTCOMES.includes(draft.outcome)) problems.push("Unknown match outcome.");
    if (draft.outcome !== "normal" && !(draft.reason || "").trim()) {
        problems.push("Record a reason for exceptional outcomes.");
    }
    if ((draft.reason || "").length > 2000) problems.push("Reason must be at most 2000 characters.");
    if (!isScore(draft.home) || !isScore(draft.away)) problems.push("Scores must be non-negative bounded integers.");
    if (periods.length > (scoring.max_periods || 100)) problems.push("Too many periods or invalid period data.");
    if (periods.some((p) => !isScore(p.home) || !isScore(p.away))) problems.push("Invalid period score.");
    if (scoring.mode === "aggregate" && periods.length) problems.push("This competition uses aggregate scoring.");
    if (complete && scoring.mode !== "aggregate" && draft.outcome === "normal" && !periods.length) {
        problems.push("Enter the sets or periods.");
    }
    if (periods.length) {
        const sum = totals(periods, scoring);
        if (scoring.mode === "sets" && scoring.set_target) {
            const wins = wonSets(periods);
            if (complete && draft.outcome === "normal" && Math.max(...wins) !== scoring.set_target) {
                problems.push("The winning set target has not been reached.");
            }
            const running = [0, 0];
            periods.forEach((p, index) => {
                if (p.home !== p.away) running[p.home > p.away ? 0 : 1] += 1;
                if (Math.max(...running) >= scoring.set_target && index !== periods.length - 1) {
                    problems.push("No sets may follow the winning set.");
                }
            });
        }
        if (sum.home !== draft.home || sum.away !== draft.away) {
            problems.push("Aggregate scores do not match periods or sets.");
        }
    }
    if (complete && draft.outcome === "forfeit_home" && draft.home >= draft.away) {
        problems.push("Home forfeit requires an away winning result.");
    }
    if (complete && draft.outcome === "forfeit_away" && draft.away >= draft.home) {
        problems.push("Away forfeit requires a home winning result.");
    }
    if (complete && EXCEPTIONAL.has(draft.outcome)) {
        problems.push("Save this exception for coordinator review; it is not an official result.");
    }
    return [...new Set(problems)];
}

/** Players listed to play, per line-up, against the per-match limit. */
export function participation(lineup, crossedOut) {
    const out = new Set(crossedOut || []);
    const playing = lineup.players.filter((player) => !out.has(player.id)).length;
    return { playing, limit: lineup.limit || null, over: Boolean(lineup.limit && playing > lineup.limit) };
}
