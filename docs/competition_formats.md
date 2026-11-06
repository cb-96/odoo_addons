# Competition formats and stage planning

## Choosing a format

Teams & format (one screen for all divisions) and **Format options** (per division, in the planner's division table) offer the same guided formats:

| Format | Stages created | Options |
| --- | --- | --- |
| League | One round robin | – |
| Home & away league | One double round robin | – |
| Knockout | One bracket | Play for every place (placement bracket) |
| Groups, then knockout | Groups A, B, … and a knockout | Number of groups, teams per group to the knockout, groups home & away, play for every place |
| Regular season, then split | Regular season, championship group, relegation group | Teams in the top group, home & away before and after the split, points after the split |
| Custom stages | Built in the stage builder | Any stage graph the engine supports |

Each option change updates the match count and a short outline of the stages before you confirm. The guided formats share one implementation with the engine (`sports_federation_format/services/format_presets.py`), so the preview always matches what gets generated.

- **A season in two halves:** pick *Regular season, then split* and put every team in the top group. The second half can start from zero or keep the points.
- **Knockout seeding:** group winners take the best seeds, then runners-up and so on. The group order is rotated so that two teams from one group avoid each other in the first knockout round wherever the bracket allows.
- **Custom stages:** *Open Stage Builder* creates a draft format and opens the [stage builder](#stage-builder).

The competition creation wizard no longer asks for a format. The format is chosen once teams are known.

## Every match exists after confirming

When you confirm a format, every match of every stage is created:

- First stages get their real teams.
- Stages fed by a table get placeholder matches between places, such as "#1 Group A vs #2 Group B". Round robins after a split are created this way too.
- Later knockout rounds reference earlier matches ("Winner R1 M2").

Placeholders get their teams when the source stage's standings are frozen, and follow-up rounds when results are approved. Scheduled slots are kept.

## Planning stages on game days

*Plan Competition* plans every stage in one run:

- Earlier stages are planned first.
- A stage fed by a table that is played over several game days starts on a later game day. On a single tournament day, the next stage starts after the last match of the stage that feeds it.
- To leave room, earlier stages keep the last game days of the division free: one day for each round of the stages that follow.
- The matches of one knockout round stay on one day, and follow-up rounds prefer a later day.
- **Stage game days** (optional, folded away in the wizard and also on the stage) fix a stage to chosen game days, for example a finals day.

The schedule validator enforces the same rules for automatic and drag-and-drop changes:

| Code | Meaning |
| --- | --- |
| `stage_game_day` | The match is on a game day that is not one of its stage's game days. |
| `stage_before_source` | The match starts before the stage it depends on has ended on that day, or the source stage still plays on a later game day. |

## Stage builder

The stage builder (*Format options → Custom stages → Open Stage Builder*, or *Stage builder* on a format) shows a custom format as cards in columns:

- The left column holds the stages that start with the registered teams. Each later column holds the stages fed by the column before it.
- Each card shows how the stage is played, its number of teams and matches, and where its teams come from. On a draft format you can rename it, change how it is played and choose the points carried over.
- **Add next stage** creates a stage that takes the next free places of this one. **Link places** sends a range of places to any later stage.
- Under *How teams move between stages* every link is written as a sentence, for example *Places 1–4 of League → Final four, all points carried over*.
- *Fix before generating* lists every problem and points to its stage or link: places that do not exist, seeds with gaps or doubles, a place sent to two stages, stages without teams, and links that go backwards. Links that would create a loop are refused.
- **Generate all matches** creates every match, including placeholders for later stages, and freezes the format.
- A generated format is read-only. **Edit as new version** copies its stages and links into a new draft, but only while none of its matches are on game days or played.

The builder edits the same stages and links as the stage graph; it stores nothing of its own. It needs the division's teams to be confirmed.

## Match board

*Match board* (the planner's **Schedule** step, or the button on the competition) shows every match of the competition:

- **Matches to plan** (left) lists matches without a time slot. You can filter by division, stage, round and team.
- **Game days** (top) shows how many slots each day uses. Dropping a match on a day puts it on the first slot that fits.
- **Day grid** (right) has courts across and start times down. Dropping a match on a slot places it there. Dropping it on a taken slot swaps the two matches, and dropping a match back on the list takes it off its day.
- Without a mouse: click a match, then click a slot or a day. Esc cancels.
- While dragging, slots show whether the match fits: green means free, red means a team already plays then, and faded means the division does not play that day.
- Matches you place by hand are **pinned**, so automatic planning keeps them. Matches placed on a day are not pinned. The pin icon toggles this.
- Every change is checked by the schedule validator and refused if it would add an error, for example a team playing twice at once or a stage played before the stage that feeds it. **Undo** reverts the last changes (up to 20).
- **Auto-plan the rest** opens *Plan Competition* to fill the remaining matches around everything already planned.
- A day without slots offers **Create time slots** from its courts and hours.

Changes made before publication need no reason. They are recorded in the schedule history as `board_move`. Published days are locked. Open their schedule to start an amendment.

## Reuse next season

- **Save as template** (in the stage builder) stores the format: guided options, or every stage and link of a custom format. It never stores teams or matches.
- In *Format options*, **Start from a saved format** fills in a template. A custom template opens in the stage builder so you can review it before generating.
- **Copy competition setup** copies divisions and game days to the next season. Game days move by whole weeks, so a Saturday stays a Saturday, and they keep their divisions. With **Reuse formats** each division starts from last season's format once its teams are known.
