"""How many matches can one team play on a game day with the required rest?

Slots on different courts that start and end at the same time form one time
row; a team can use at most one slot per row.  Picking the row that ends
first, then the first row starting at least ``rest_minutes`` after it, and so
on, gives the maximum number of matches (classic interval scheduling with the
rest added to each interval).
"""
from datetime import timedelta


def time_rows(slots):
    """Return the distinct (start, end) windows of the given slot values."""
    return sorted({(slot["start_datetime"], slot["end_datetime"]) for slot in slots},
                  key=lambda row: (row[1], row[0]))


def max_matches_with_rest(rows, rest_minutes):
    rest = timedelta(minutes=max(0, rest_minutes or 0))
    count = 0
    last_end = None
    for start, end in sorted(rows, key=lambda row: (row[1], row[0])):
        if last_end is None or start >= last_end + rest:
            count += 1
            last_end = end
    return count
