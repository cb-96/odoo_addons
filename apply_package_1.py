#!/usr/bin/env python3
# Apply Package 1 against the repository state supplied on 2026-08-15.

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path.cwd()
MOD = ROOT / "sports_federation_tournament"
BACKUP = ROOT / ".package_1_backups" / datetime.now().strftime("%Y%m%d_%H%M%S")

paths = {
    "manifest": MOD / "__manifest__.py",
    "readme": MOD / "README.md",
    "match": MOD / "models/federation_match.py",
    "bracket": MOD / "models/federation_match_bracket.py",
    "view": MOD / "views/federation_match_views.xml",
    "test_match": MOD / "tests/test_match.py",
    "test_bracket": MOD / "tests/test_bracket_linking.py",
}
migration = MOD / "migrations/19.0.1.2.0/post-migrate.py"


def fail(message):
    raise SystemExit(f"[ERROR] {message}")


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f"Expected exactly one {label}; found {count}. No files were changed.")
    return text.replace(old, new, 1)


if not MOD.is_dir():
    fail("Run from the addons repository root.")

current = {}
for key, path in paths.items():
    if not path.is_file():
        fail(f"Missing required file: {path}")
    current[key] = path.read_text(encoding="utf-8")

markers = [
    "def _validate_completion_result(self):",
    "resolution_type = fields.Selection(",
    "advancing_team_id = fields.Many2one(",
    '<field name="resolution_type"/>',
]
combined = "\n".join(current.values())
found = [marker for marker in markers if marker in combined]
if len(found) == len(markers):
    print("[OK] Package 1 already appears implemented. No changes made.")
    raise SystemExit(0)
if found:
    fail("Partial implementation already present: " + ", ".join(found))

planned = dict(current)

planned["match"] = replace_once(
    planned["match"],
    '''    def action_done(self):
        """Execute the done action."""
        for rec in self:
            rec.state = MATCH_STATE_DONE
            rec._advance_bracket_teams()
''',
    '''    def _validate_completion_result(self):
        """Validate that the recorded result can complete this match."""
        return True

    def action_done(self):
        """Complete the match after validating its sporting outcome."""
        for rec in self:
            rec._validate_completion_result()
            rec.state = MATCH_STATE_DONE
            rec._advance_bracket_teams()
''',
    "original action_done block",
)

planned["bracket"] = '''from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationMatchBracket(models.Model):
    _inherit = "federation.match"
    _description = "Federation Match – Bracket Wiring"

    bracket_position = fields.Integer(string="Bracket Position")
    resolution_type = fields.Selection(
        [
            ("regulation", "Regulation Score"),
            ("overtime", "Overtime"),
            ("tiebreak", "Tiebreak"),
            ("forfeit", "Forfeit"),
            ("walkover", "Walkover"),
            ("administrative", "Administrative Decision"),
        ],
        string="Resolution",
        default="regulation",
        tracking=True,
        help=(
            "How the advancing team was determined. A tied knockout score must "
            "use a non-regulation resolution and explicitly identify the advancing team."
        ),
    )
    advancing_team_id = fields.Many2one(
        "federation.team",
        string="Advancing Team",
        ondelete="restrict",
        tracking=True,
        help=(
            "Explicit winner used for tied, forfeited, walkover, or "
            "administrative knockout results."
        ),
    )
    bracket_type = fields.Selection(
        [
            ("winners", "Winners"),
            ("losers", "Losers"),
            ("consolation", "Consolation"),
            ("placement_3rd", "3rd Place"),
            ("placement_5th", "5th Place"),
            ("placement_7th", "7th Place"),
        ],
        string="Bracket Type",
    )
    source_match_1_id = fields.Many2one(
        "federation.match",
        string="Source Match 1",
        ondelete="set null",
        help="Winner or loser of this match feeds into the current match.",
    )
    source_match_2_id = fields.Many2one(
        "federation.match", string="Source Match 2", ondelete="set null"
    )
    source_type_1 = fields.Selection(
        [("winner", "Winner"), ("loser", "Loser")],
        string="Source 1 Type",
        default="winner",
    )
    source_type_2 = fields.Selection(
        [("winner", "Winner"), ("loser", "Loser")],
        string="Source 2 Type",
        default="winner",
    )
    next_match_ids = fields.One2many(
        "federation.match", compute="_compute_next_matches", string="Next Matches"
    )

    def _compute_next_matches(self):
        for rec in self:
            rec.next_match_ids = self.search(
                [
                    "|",
                    ("source_match_1_id", "=", rec.id),
                    ("source_match_2_id", "=", rec.id),
                ]
            )

    def _is_bracket_match(self):
        self.ensure_one()
        return bool(
            self.bracket_type
            or self.source_match_1_id
            or self.source_match_2_id
            or self.next_match_ids
        )

    def _validate_completion_result(self):
        super()._validate_completion_result()
        for match in self:
            if not match._is_bracket_match():
                continue
            participants = match.home_team_id | match.away_team_id
            if len(participants) < 2:
                raise ValidationError(
                    _("A knockout match needs both participating teams before it can be completed.")
                )
            if match.advancing_team_id and match.advancing_team_id not in participants:
                raise ValidationError(
                    _("The advancing team must be one of the teams in this knockout match.")
                )
            if match.resolution_type != "regulation" and not match.advancing_team_id:
                raise ValidationError(
                    _("Select the team that advances for this knockout resolution.")
                )
            if match.home_score == match.away_score:
                if match.resolution_type == "regulation":
                    raise ValidationError(
                        _(
                            "A tied knockout match needs an overtime, tiebreak, forfeit, "
                            "walkover, or administrative resolution."
                        )
                    )
            elif match.resolution_type == "regulation" and match.advancing_team_id:
                score_winner = (
                    match.home_team_id
                    if match.home_score > match.away_score
                    else match.away_team_id
                )
                if match.advancing_team_id != score_winner:
                    raise ValidationError(
                        _(
                            "For a regulation result, the advancing team must match "
                            "the winner indicated by the score."
                        )
                    )
        return True

    def _get_result_team(self, result_type):
        self.ensure_one()
        if self.state != "done":
            return False
        if self.advancing_team_id:
            participants = self.home_team_id | self.away_team_id
            if self.advancing_team_id not in participants:
                return False
            if result_type == "winner":
                return self.advancing_team_id
            return (participants - self.advancing_team_id)[:1]
        return super()._get_result_team(result_type)

    def _advance_bracket_teams(self):
        self.ensure_one()
        next_matches = self.search(
            [
                "|",
                ("source_match_1_id", "=", self.id),
                ("source_match_2_id", "=", self.id),
            ]
        )
        for next_match in next_matches:
            if next_match.source_match_1_id == self and not next_match.home_team_id:
                team = self._get_result_team(next_match.source_type_1 or "winner")
                if team:
                    next_match.home_team_id = team
            if next_match.source_match_2_id == self and not next_match.away_team_id:
                team = self._get_result_team(next_match.source_type_2 or "winner")
                if team:
                    next_match.away_team_id = team
'''

planned["view"] = replace_once(
    planned["view"],
    '''                                <group string="Source Matches">
                                    <field name="source_match_1_id"/>
''',
    '''                                <group string="Resolution">
                                    <field name="resolution_type"/>
                                    <field name="advancing_team_id"
                                           domain="[('id', 'in', [home_team_id, away_team_id])]"
                                           invisible="resolution_type == 'regulation' and home_score != away_score"/>
                                </group>
                                <group string="Source Matches">
                                    <field name="source_match_1_id"/>
''',
    "Source Matches view group",
)

planned["test_match"] = replace_once(
    planned["test_match"],
    '''    def test_bracket_advancement_draw_does_not_populate_next(self):
        """A draw leaves the next match teams unset."""
        match1 = self._make_match()
        match2 = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "source_match_1_id": match1.id,
            }
        )
        match1.home_score = 1
        match1.away_score = 1
        match1.action_done()
        self.assertFalse(match2.home_team_id)
''',
    '''    def test_bracket_draw_requires_explicit_resolution(self):
        """A tied bracket match cannot complete without an explicit winner."""
        match1 = self._make_match()
        self.env["federation.match"].create(
            {"tournament_id": self.tournament.id, "source_match_1_id": match1.id}
        )
        match1.write({"home_score": 1, "away_score": 1})
        with self.assertRaises(ValidationError):
            match1.action_done()
        self.assertEqual(match1.state, "draft")

    def test_bracket_draw_tiebreak_advances_selected_team(self):
        match1 = self._make_match()
        match2 = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "source_match_1_id": match1.id,
                "source_type_1": "winner",
            }
        )
        match1.write(
            {
                "home_score": 1,
                "away_score": 1,
                "resolution_type": "tiebreak",
                "advancing_team_id": self.team_away.id,
            }
        )
        match1.action_done()
        self.assertEqual(match2.home_team_id, self.team_away)
        self.assertEqual(match1._get_result_team("loser"), self.team_home)

    def test_bracket_resolution_rejects_unrelated_advancing_team(self):
        other_team = self.env["federation.team"].create(
            {"name": "Unrelated Team", "club_id": self.club.id}
        )
        match1 = self._make_match()
        self.env["federation.match"].create(
            {"tournament_id": self.tournament.id, "source_match_1_id": match1.id}
        )
        match1.write(
            {
                "home_score": 2,
                "away_score": 2,
                "resolution_type": "administrative",
                "advancing_team_id": other_team.id,
            }
        )
        with self.assertRaises(ValidationError):
            match1.action_done()
''',
    "old test_match draw test",
)

planned["test_bracket"] = replace_once(
    planned["test_bracket"],
    "from odoo.tests import TransactionCase\n",
    "from odoo.exceptions import ValidationError\nfrom odoo.tests import TransactionCase\n",
    "test_bracket import",
)
planned["test_bracket"] = replace_once(
    planned["test_bracket"],
    '''    def test_advance_bracket_does_not_advance_on_draw(self):
        """A draw should not trigger automatic advancement."""
        self.sf2.write({"home_score": 1, "away_score": 1, "state": "done"})
        self.sf2._advance_bracket_teams()
        # No team should be set in final.away_team_id
        self.assertFalse(self.final.away_team_id)
''',
    '''    def test_tied_bracket_requires_resolution_before_completion(self):
        self.sf2.write({"home_score": 1, "away_score": 1})
        with self.assertRaises(ValidationError):
            self.sf2.action_done()
        self.assertNotEqual(self.sf2.state, "done")
        self.assertFalse(self.final.away_team_id)

    def test_tied_bracket_advances_explicit_winner(self):
        self.sf2.write(
            {
                "home_score": 1,
                "away_score": 1,
                "resolution_type": "tiebreak",
                "advancing_team_id": self.teams[3].id,
            }
        )
        self.sf2.action_done()
        self.assertEqual(self.sf2.state, "done")
        self.assertEqual(self.final.away_team_id, self.teams[3])
''',
    "old test_bracket draw test",
)

planned["manifest"] = replace_once(
    planned["manifest"],
    '    "version": "19.0.1.1.0",\n',
    '    "version": "19.0.1.2.0",\n',
    "manifest version",
)

planned["readme"] = planned["readme"].rstrip() + '''

## Knockout result resolution (v19.0.1.2.0)

Knockout matches must have an unambiguous advancing team before they can be
completed. A tied numeric score requires a non-regulation resolution, such as
overtime, tiebreak, forfeit, walkover, or an administrative decision, plus an
explicit advancing team selected from the two match participants.

Winner and loser bracket progression uses this explicit decision, preventing a
completed knockout match from leaving downstream participants unresolved.
'''

migration_text = '''"""Backfill explicit regulation resolution for existing bracket matches."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE federation_match
           SET resolution_type = 'regulation'
         WHERE resolution_type IS NULL
           AND (
                bracket_type IS NOT NULL
                OR source_match_1_id IS NOT NULL
                OR source_match_2_id IS NOT NULL
           )
        """
    )
'''
if migration.exists() and migration.read_text(encoding="utf-8") != migration_text:
    fail(f"Unexpected existing migration: {migration}")

# Only write after every preflight replacement succeeded.
BACKUP.mkdir(parents=True, exist_ok=False)
for path in paths.values():
    target = BACKUP / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

for key, path in paths.items():
    path.write_text(planned[key], encoding="utf-8")

migration.parent.mkdir(parents=True, exist_ok=True)
migration.write_text(migration_text, encoding="utf-8")

print("[OK] Package 1 applied successfully.")
print(f"[OK] Backups saved under {BACKUP.relative_to(ROOT)}")
print("[OK] Existing 19.0.1.1.0 index migration was preserved.")
print("[OK] Tournament module version is now 19.0.1.2.0.")
print("Run: python3 -m compileall -q sports_federation_tournament")
print("Run: git diff --check")
print("Run: bash ./ci/run_tests.sh --module sports_federation_tournament")
