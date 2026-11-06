# Workflow: Data Import

Owner: Federation Competition Operations
Last reviewed: 2026-11-06
Review cadence: Every release

Bulk data loading via CSV import wizards with validation, dry-run preview, and
error reporting.

## Overview

During initial federation setup or season transitions, large amounts of data need
to be loaded — clubs, seasons, teams, players, and tournament participants. The
import tools module provides guided wizards that validate data before committing,
support a dry-run mode, surface a per-wizard column guide, and report row-level
failures with explicit categories.

## Modules Involved

| Module | Role |
| ------ | ---- |
| `sports_federation_import_tools` | Shared import mixin plus all import wizards |
| `sports_federation_base` | Target for club and team imports |
| `sports_federation_people` | Target for player imports |
| `sports_federation_tournament` | Target for tournament participant imports |

## Available Import Wizards

| Wizard | Target Model | CSV Fields |
| ------ | ------------ | ---------- |
| Import Clubs | `federation.club` | name, code, city, etc. |
| Import Seasons | `federation.season` | name, code, date_start, date_end, state |
| Import Teams | `federation.team` | name, code, club reference |
| Import Players | `federation.player` | first_name, last_name, birth_date, club reference |
| Import Tournament Participants | `federation.tournament.participant` | team reference, tournament reference, seed |

## Step-by-Step Flow

### 1. CSV Preparation

**Actor**: Federation administrator
**Format Requirements**:

1. Prepare a UTF-8 CSV file (no BOM) with headers matching expected field names.
2. Use commas or semicolons as delimiters; the shared import mixin auto-detects both.
3. Reference existing records by code or name (e.g. club code for team→club link).
4. Include all required fields; optional fields can be left blank.

### 2. Wizard Launch

**Actor**: Federation administrator
**Module**: `sports_federation_import_tools`

1. Navigate to **Federation > Administration > Imports & Integrations > Import [Entity]**.
2. Open the appropriate wizard form.
3. Upload the CSV file via the `upload_file` Binary field.
4. Review the wizard's `mapping_guide` before the first run if you are using a new template.

### 3. Dry-Run Preview

**Actor**: Federation administrator
**Module**: `sports_federation_import_tools`

1. Check the **Dry Run** checkbox.
2. Click **Import**.
3. The wizard processes every row:
   - Validates required fields
   - Checks references with code-first lookup where supported (e.g. `club_code`, `team_code`)
   - Detects duplicates using the model's safe import key
   - Classifies failures by type (`missing_reference`, `duplicate_entry`, `format_error`, etc.)
4. Results are displayed in the `result_message` field:
   - Per-row status (success / error with reason)
   - Summary statistics: `line_count`, `success_count`, `error_count`
   - Error category totals for quick CSV cleanup
5. **No records are created** in dry-run mode — it's a pure validation pass.

### 4. Error Correction

**Actor**: Federation administrator

1. Review errors from the dry-run output.
2. Fix the CSV file:
   - Correct invalid references
   - Fill in missing required fields
   - Remove duplicate entries
   - Fix formatting problems such as invalid dates or non-numeric seeds
3. Re-upload and re-run dry-run until `error_count = 0`.

### 5. Commit Import

**Actor**: Federation administrator
**Module**: `sports_federation_import_tools`

1. Uncheck the **Dry Run** checkbox.
2. Click **Import**.
3. The wizard creates records for each valid non-duplicate row.
4. Existing records matched by the import key are reported and skipped rather than overwritten.
5. Final statistics confirm the import outcome.

### 6. Post-Import Verification

**Actor**: Federation administrator

1. Navigate to the target list view (clubs, teams, players, participants).
2. Verify imported records appear correctly.
3. Check linked references (e.g. players have correct club assignments).
4. Run compliance checks if applicable.

## Process Diagram

```text
                    ┌─────────┐
                    │ Prepare │
                    │   CSV   │
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │ Upload  │
                    │  File   │
                    └────┬────┘
                         │
                  ┌──────▼──────┐
               ┌──┤  Dry Run?   ├──┐
               │  └─────────────┘  │
              Yes                  No
               │                   │
        ┌──────▼──────┐    ┌──────▼──────┐
        │  Validate   │    │   Create    │
        │  (preview)  │    │  Records    │
        └──────┬──────┘    └──────┬──────┘
               │                   │
        ┌──────▼──────┐    ┌──────▼──────┐
        │  Errors?    │    │   Review    │
        │  Fix CSV    │    │  Results    │
        └──────┬──────┘    └─────────────┘
               │
          (loop back)
```

## Field Mappings

### Clubs CSV

| Column | Maps To | Required |
| ------ | ------- | -------- |
| `name` | `federation.club.name` | Yes |
| `code` | `federation.club.code` | No, but strongly recommended |
| `city` | `federation.club.city` | No |
| ... | Other club fields | No |

### Seasons CSV

| Column | Maps To | Required |
| ------ | ------- | -------- |
| `name` | `federation.season.name` | Yes |
| `code` | `federation.season.code` | Yes |
| `date_start` | `federation.season.date_start` | Yes |
| `date_end` | `federation.season.date_end` | Yes |
| `state` | `federation.season.state` | No |
| `notes` | `federation.season.notes` | No |

### Players CSV

| Column | Maps To | Required |
| ------ | ------- | -------- |
| `first_name` | `federation.player.first_name` | Yes |
| `last_name` | `federation.player.last_name` | Yes |
| `birth_date` | `federation.player.birth_date` | No |
| `club_code` | Lookup → `federation.club` | No |
| ... | Other player fields | No |

### Teams CSV

| Column | Maps To | Required |
| ------ | ------- | -------- |
| `team_name` or `name` | `federation.team.name` | Yes |
| `code` | `federation.team.code` | No, but strongly recommended |
| `club_code` or `club_name` | Lookup → `federation.club` | Yes |

### Tournament Participants CSV

| Column | Maps To | Required |
| ------ | ------- | -------- |
| `team_code` | Lookup → `federation.team` | Yes |
| `tournament_code` | Lookup → `federation.tournament` | Yes |
| `seed` | `federation.tournament.participant.seed` | No |

## Key Behaviours

1. **Duplicate-safe** — Running the same import twice reports existing rows and skips them rather than creating duplicates.
2. **Delimiter tolerant** — Comma and semicolon CSV files are accepted.
3. **BOM handling** — UTF-8 BOM characters are stripped automatically.
4. **Error isolation** — One bad row doesn't prevent other rows from importing.
5. **Categorized feedback** — Error summaries group failures so administrators can clean the source file predictably.

## Related Workflows

- [Season Registration](season-registration.md) — imported clubs feed into registration
- [Tournament Lifecycle](tournament-lifecycle.md) — imported participants feed into tournaments
