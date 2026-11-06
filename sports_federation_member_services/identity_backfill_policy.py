"""Pure planning for the identity backfill. It never decides a merge.

Players created before the identity review existed have no match key, so the
duplicate guard never protected them. The backfill gives every player with a
birth date a key, but only when that is safe:

* a key is written only when exactly one player has it and nobody else holds it;
* when several players share one key, none of them is keyed and the group is
  queued for the existing reviewed identity merge;
* players without a birth date cannot be matched and are only counted.
"""


def plan(players, key_holders, key_for):
    """Split un-keyed ``players`` into keys to write, review candidates and gaps.

    ``players``: dicts with id, first_name, last_name, birth_date.
    ``key_holders``: ``{key: [ids of players that already hold it]}``.
    ``key_for``: ``(first_name, last_name, birth_date) -> key``.
    """
    groups, needs_birth_date = {}, []
    for player in players:
        if not player.get("birth_date"):
            needs_birth_date.append(player["id"])
            continue
        key = key_for(player["first_name"], player["last_name"], player["birth_date"])
        groups.setdefault(key, []).append(player["id"])
    to_key, candidates = [], {}
    for key, ids in groups.items():
        holders = list(key_holders.get(key, []))
        if len(ids) == 1 and not holders:
            to_key.append((ids[0], key))
        else:
            candidates[key] = sorted(set(ids) | set(holders))
    return {"to_key": to_key, "candidates": candidates, "needs_birth_date": needs_birth_date}
