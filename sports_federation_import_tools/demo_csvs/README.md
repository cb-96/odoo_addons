# Demo CSVs for sports_federation_import_tools

Sample files for trying the import wizards. Each file includes rows that show
common validation results.

| File | Columns | Shows |
| --- | --- | --- |
| `clubs.csv` | `name,code,email,phone,city` | A row with a missing name |
| `teams.csv` | `club_code,team_name,code` | A duplicate row, a missing club code, an unknown club |
| `players.csv` | `first_name,last_name,birth_date,club_code` | An invalid date, an unknown club, a missing first name |
| `tournament_participants.csv` | `tournament_code,team_code` | A duplicate row, a missing division code, an unknown team (`SUMMER_CUP` must exist as a division code) |

References use codes only: clubs by `club_code`, divisions by
`tournament_code`, teams by `team_code`. Name-based matching is not supported.

## Import order

1. `clubs.csv`
2. `teams.csv`
3. `players.csv`
4. `tournament_participants.csv`

## Usage

Open the import wizard under **Federation > Administration > Imports &
Integrations**, upload the file and select **Parse & Import**. Wizards run as
a dry run by default; clear **Dry Run** to create records once the preview is
approved. Files must be UTF-8 (a BOM is allowed) and dates use `YYYY-MM-DD`.
