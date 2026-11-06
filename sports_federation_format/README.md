# Sports Federation Format

The format addon manages versioned competition structures, their stages, and
Format Studio stage graphs.

## Stage graph models

Format Studio uses `federation.structure.stage.progression` for edges between
stages in one `federation.competition.structure`. This is deliberately
separate from the competition engine's `federation.stage.progression` model,
which belongs to tournament-level progression workflows and uses a different
relation contract.

Before generating a structure, the graph is validated for cycles. Root stages
can then be prepared; dependent stages wait for incoming progression results.
Approved fixture results can populate dependent stages, and frozen standings
are stored as immutable snapshots.

Active progression edges must not overlap source rank ranges from the same
stage or target seed ranges in the destination stage. Bracket progression also
rejects tied approved results until an explicit tie-break outcome is recorded;
the engine never silently treats a tie as an away win.

Stage-graph access rules are loaded from `security/ir.model.access.csv`. The
structure form extension identifies the stage tab by its `stage_ids` field so
the view remains safe when translated page labels change.
## Supported format generation

The format studio now estimates fixture and round counts before generation. It
supports single and double leagues, seeded knockout and placement brackets,
match series, pool-to-knockout structures, and championship/relegation splits.
For pool-knockout, seeded teams are distributed across the selected groups in a
snake pattern, each group plays a single round robin, and the top two from each
group feed a seeded knockout bracket. The knockout fixtures are created as
placeholders before group results are known, so they can be included in the
original schedule publication. Freezing each group table applies its progression
edge; when all groups are frozen, teams fill the bracket without republishing.
Knockout tie-resolution fields are available on the logical-format match form.

Swiss pairing, ladder, and double-elimination services provide deterministic
planning helpers, but complete automatic fixture generation for those formats
remains deliberately out of scope until their full workflows are implemented.
Estimates are planning guidance; generation validates the final fixture graph.

## Final stage freeze access

Federation managers can create the immutable standing lines required by **Freeze & Progress**. The ACL grants create without granting write or delete, and a regression test exercises the manager workflow end to end.

Competition Designers can read finalized participant sets and their lines to
review the input to format selection. This is read-only access; registration
managers retain the permissions to create and change registration records.

## Format reuse

`format_reuse.py` describes a format as a JSON snapshot: guided options and, for
custom formats, every stage and active progression. Teams, fixtures and results
are never part of it.

- `action_save_as_template(name)` stores the snapshot in
  `federation.competition.format.template.configuration`. Templates accept the
  `custom` format type.
- `action_create_structure` on a template applies the snapshot to a new draft
  structure.
- `action_new_draft_version()` copies a generated format into a new editable
  draft. It is refused while fixtures are on game days or completed.
- `federation.tournament.format_source_structure_id` points a copied division
  to last season's format, which the format wizard offers as its starting
  point.

Competition designers can now create progressions and templates, because the
stage builder edits both. Upgrade the module so the new fields and access
rules are installed; no data migration is needed.
