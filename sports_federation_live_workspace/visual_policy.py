"""Read-only impact policy. Potential downstream effects never move fixtures."""


def closure(roots, edges):
    roots = set(roots)
    visited = set(roots)
    pending = list(roots)
    while pending:
        for child in edges.get(pending.pop(), ()):
            if child not in visited:
                visited.add(child)
                pending.append(child)
    return sorted(visited - roots)


def impact_sets(changed, fixtures, stages):
    changed = set(changed)
    fixture_edges, stage_edges = {}, {}
    teams, source_stages = set(), set()
    for fixture in fixtures:
        if fixture["id"] in changed:
            teams.update(fixture.get("teams", []))
            source_stages.add(fixture["stage_id"])
        for source in (fixture.get("home_source"), fixture.get("away_source")):
            if source:
                fixture_edges.setdefault(source, []).append(fixture["id"])
    for stage in stages:
        stage_edges[stage["id"]] = [edge["id"] for edge in stage.get("next", [])]
    downstream_stages = set(closure(source_stages, stage_edges))
    direct_downstream = set(closure(changed, fixture_edges))
    return {
        "changed": sorted(changed),
        "shared_teams": sorted(
            f["id"]
            for f in fixtures
            if f["id"] not in changed and teams.intersection(f.get("teams", []))
        ),
        "fixture_dependants": sorted(direct_downstream),
        "stage_dependants": sorted(
            f["id"]
            for f in fixtures
            if f["id"] not in changed and f["stage_id"] in downstream_stages
        ),
    }


def pin_changes(before, after, methods):
    return sorted(
        fid
        for fid, method in methods.items()
        if method != "automatic" and before.get(fid) != after.get(fid)
    )
