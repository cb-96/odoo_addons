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
- **Custom stages:** *Open Stage Builder* creates a draft structure and opens it. Add stages and progressions, then reopen Format options and choose *Generate All Matches*.

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
