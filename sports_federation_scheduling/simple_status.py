"""Plain-language schedule status: what must be fixed and what could improve.

A volunteer should never have to interpret a constraint, a warning, a fairness
score, a preference and a publication blocker at the same time. The validator
already separates hard errors from soft warnings; this module only turns that
result into two short lists and one summary sentence.

Pure Python so it can be unit tested without an Odoo runtime.
"""

MUST_FIX = "must_fix"
COULD_IMPROVE = "could_improve"


def group_messages(items, fallback):
    """Collapse repeated messages into one line with a count."""
    order, counts = [], {}
    for item in items:
        text = (item.get("message") or item.get("code") or fallback).strip()
        if text not in counts:
            order.append(text)
            counts[text] = 0
        counts[text] += 1
    return [
        text if counts[text] == 1 else "%s (x%s)" % (text, counts[text])
        for text in order
    ]


def plural(count, singular, many):
    return singular if count == 1 else many


def split_validation(validation):
    """Return ``(must_fix, could_improve)`` message lists for one validation."""
    must_fix = group_messages(validation.get("errors", []), "Schedule conflict")
    unassigned = len(validation.get("unassigned_fixture_ids", []))
    if unassigned:
        must_fix.append(
            "%s %s a court and time."
            % (
                unassigned,
                plural(unassigned, "match still needs", "matches still need"),
            )
        )
    could_improve = group_messages(
        validation.get("warnings", []), "Schedule preference"
    )
    return must_fix, could_improve


def counts(validation):
    """Counts shown on the default screen (errors are counted individually)."""
    errors = len(validation.get("errors", [])) + len(
        validation.get("unassigned_fixture_ids", [])
    )
    return errors, len(validation.get("warnings", []))


def summary(scheduled, warnings, blockers):
    """The one sentence of the default scheduling screen."""
    return "%s %s scheduled \u00b7 %s preference %s \u00b7 %s blocking %s" % (
        scheduled,
        plural(scheduled, "match", "matches"),
        warnings,
        plural(warnings, "warning", "warnings"),
        blockers,
        plural(blockers, "conflict", "conflicts"),
    )
