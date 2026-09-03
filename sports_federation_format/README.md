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

Stage-graph access rules are loaded from `security/ir.model.access.csv`. The
structure form extension identifies the stage tab by its `stage_ids` field so
the view remains safe when translated page labels change.
## Supported format generation

The format studio now estimates fixture and round counts before generation. It supports single and double leagues, seeded knockout and placement brackets, match series, pool-to-knockout configuration, and championship/relegation splits. Dynamic Swiss, ladder, and double-elimination formats are deliberately not advertised as automatic because they require round-by-round or reset-final semantics outside the immutable fixture graph.
