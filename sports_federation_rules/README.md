# Sports Federation Rules

Competition rule configuration layer. Defines reusable **rule sets** with scoring
tables, tie-break criteria, eligibility requirements, and qualification rules —
all as configurable data rather than hard-coded logic.

## Purpose

Decouples competition logic from code. Any competition or tournament can reference
a rule set, and modules like Standings, Competition Engine, and Rosters consume
these rules to compute points, resolve ties, validate squads, and determine
progression.

## Dependencies

- `sports_federation_base`: Core entities.

## Models

### `federation.rule.set`

A named, reusable collection of rules. Attach it to a competition or tournament
to govern how that event works.

- `name` / `code`: Char identity fields, with a unique code.
- `description`: Human-readable explanation.
- `points_win` / `points_draw` / `points_loss`: Integer default scoring.
- `points_rule_ids`: One2many extended result-type scoring entries.
- `tie_break_rule_ids`: One2many ordered tie-break criteria.
- `eligibility_rule_ids`: One2many player and team eligibility rules.
- `qualification_rule_ids`: One2many stage progression rules.
- `squad_min_size` / `squad_max_size`: Integer roster limits.
- `referee_required_count`: Integer officials required per match.
- `seeding_mode`: Selection describing participant seeding.

### `federation.points.rule`

Maps a result type to a point value within a rule set.

- `rule_set_id`: Many2one parent rule set.
- `result_type`: Selection with `win`, `draw`, `loss`, `bye`, or `forfeit`.
- `points`: Integer points awarded.

- **Unique constraint**: one entry per (rule_set, result_type).

### `federation.tie_break_rule`

Ordered criteria to resolve teams with equal points.

- `rule_set_id`: Many2one parent rule set.
- `sequence`: Integer priority order.
- `tie_break_type`: Selection with `head_to_head`, `goal_difference`, `goals_scored`, `goals_against`, `fair_play`, `drawing_lots`, `ranking_points`, or `custom`.
- `description`: Char label.
- `reverse_order`: Boolean that inverts sort direction.

### `federation.eligibility.rule`

Defines who is allowed to participate.

- `rule_set_id`: Many2one parent rule set.
- `sequence`: Integer evaluation order.
- `name`: Char rule label.
- `eligibility_type`: Selection with `age_min`, `age_max`, `gender`, `license_valid`, `suspension`, `registration`, or `custom`.
- `age_limit`: Integer limit for age-based rules.
- `allowed_categories`: Char list of comma-separated category codes.
- `is_placeholder`: Boolean flag for not-yet-implemented rules.

### `federation.qualification.rule`

Determines how teams advance between stages.

- `rule_set_id`: Many2one parent rule set.
- `sequence`: Integer evaluation order.
- `name`: Char rule label.
- `qualification_type`: Selection with `top_n`, `top_percent`, `min_points`, `min_position`, `group_winner`, `group_runner_up`, or `custom`.
- `value_integer` / `value_percent`: Numeric threshold values.
- `target_stage_id`: Char extension point for stage linking.

## Services

### `federation.eligibility.service`

Central evaluation service consumed by rosters and match-day workflows.

- `check_player_eligibility(player, rule_set, context)`: Evaluate one player and return `eligible` plus human-readable `reasons`.
- `check_roster_eligibility(roster, rule_set=None)`: Evaluate every roster line in season, team, and club context.
- `check_match_eligibility(match, team, players)`: Evaluate players for a specific match and tournament context.

Important context keys:

- `season_id` and `club_id` scope license validation to the actual competition context.
- `team_id` scopes registration checks to the team that is trying to compete.
- `license_id` validates an explicitly selected roster-line license.
- `match_date` evaluates age and license windows against the operational date.

## Key Behaviours

1. **Reusable rule sets** — One rule set can be shared by many competitions.
2. **Configurable scoring** — Default win/draw/loss points plus extended result types.
3. **Ordered tie-breaks** — Sequence-based priority resolves equal points systematically.
4. **Operational eligibility enforcement** — Age, gender, license, suspension,
   and registration rules are enforced through the shared eligibility service.
5. **Context-aware license validation** — License rules can require the correct
   season, club, selected license, and active date window instead of checking
   only for any generic active license.
6. **Date-aware suspensions** — Suspension rules honor active
   `federation.suspension` windows for the operational match or roster date,
   instead of relying only on a player's static master-data state.
7. **Readable failure reasons** — Eligibility checks return structured reasons so
   workflow layers can block actions with operator-friendly messages.
