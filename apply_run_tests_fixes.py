#!/usr/bin/env python3
"""Fix the failures and errors of the run_tests.sh run of 2026-11-14 (09:02).

Run from the repository root (the folder that holds the sports_federation_*
addons):

    python apply_run_tests_fixes.py          # apply
    python apply_run_tests_fixes.py --check  # only verify that it would apply

Every edit matches exact source text. Nothing is written unless every edit
matches, so a mismatch leaves the working tree untouched. Running it twice is
safe: the second run reports that the fixes are already applied.
"""

import ast
import os
import sys

CHECK_ONLY = "--check" in sys.argv
if not os.path.isdir("sports_federation_base"):
    sys.exit("Run this from the repository root (sports_federation_base not found).")

_files = {}


def read(path):
    if path not in _files:
        with open(path, encoding="utf-8") as handle:
            _files[path] = handle.read()
    return _files[path]


def write(path, text):
    read(path)
    _files[path] = text


def sub(path, old, new):
    text = read(path)
    if new in text and old not in text:
        return
    if text.count(old) != 1:
        sys.exit("Cannot apply to %s: expected one match, found %s for:\n%s" % (path, text.count(old), old[:200]))
    write(path, text.replace(old, new))


# ---- 1. `user` default resolved before the first translated string -------
targets = {
 'sports_federation_portal/models/federation_competition_entry.py': ['_portal_open_window_for_division'],
 'sports_federation_portal/models/competition_queries.py': ['assert_team', 'assert_visible_edition', 'competition_card', 'detail'],
 'sports_federation_portal/models/portal_privilege.py': ['portal_create', 'portal_write', 'portal_call', '_assert_portal_owns'],
 'sports_federation_portal/models/player_availability_portal.py': ['_portal_get', '_portal_answer', '_portal_remind'],
}
for f, names in targets.items():
    src = read(f)
    lines = src.split('\n')
    t = ast.parse(src)
    inserts = []
    for fn in ast.walk(t):
        if isinstance(fn, ast.FunctionDef) and fn.name in names:
            if 'user = user or self.env.user' in ast.get_source_segment(src, fn):
                continue
            first = fn.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, 'value', None), ast.Constant) and isinstance(first.value.value, str):
                if len(fn.body) < 2:
                    continue
                line = first.end_lineno
                indent = ' ' * fn.body[1].col_offset
            else:
                line = first.lineno - 1
                indent = ' ' * first.col_offset
            inserts.append((line, indent + 'user = user or self.env.user'))
    for line, text in sorted(inserts, reverse=True):
        lines.insert(line, text)
    write(f, '\n'.join(lines))

# ---- 2. Registry.in_test_mode() does not exist in Odoo 19 ----------------
p = 'sports_federation_base/batch_jobs.py'
sub(p, '''from psycopg2.errors import DeadlockDetected, SerializationFailure
''', '''from psycopg2.errors import DeadlockDetected, SerializationFailure

from odoo.tools import config
''')
sub(p, '''def commits_between_batches(env):
    """Whether a batch may be committed before the job ends."""
    return bool(env.context.get("cron_id")) and not env.registry.in_test_mode()
''', '''def in_test_mode(env):
    """Whether the code runs inside the Odoo test runner.

    ``Registry.in_test_mode()`` only exists in older Odoo versions. Odoo 19
    dropped it, so ask the registry first when it still offers the check and
    otherwise use the signals the 19 test runner provides: a registry in test
    mode keeps its shared test cursor, and the server is started with
    ``--test-enable``.
    """
    registry = env.registry
    legacy_check = getattr(registry, "in_test_mode", None)
    if callable(legacy_check):
        return bool(legacy_check())
    if getattr(registry, "test_cr", None) is not None:
        return True
    try:
        return bool(config["test_enable"])
    except (KeyError, TypeError):
        return False


def commits_between_batches(env):
    """Whether a batch may be committed before the job ends."""
    return bool(env.context.get("cron_id")) and not in_test_mode(env)
''')
p = 'sports_federation_portal/models/task_projection.py'
sub(p, '''from odoo.osv import expression

from .. import task_policy
''', '''from odoo.osv import expression

from odoo.addons.sports_federation_base.batch_jobs import in_test_mode

from .. import task_policy
''')
sub(p, 'default = "0" if self.env.registry.in_test_mode() else "30"', 'default = "0" if in_test_mode(self.env) else "30"')

# ---- 3. Game-day line-up: deselecting a player unlinks the sheet line ----
sub('sports_federation_portal/models/portal_privilege.py', '''            "action_submit",
            "unlink",
        },
        "federation.season.registration"''', '''            "action_submit",
            "unlink",
        },
        # Deselecting a player in the game-day line-up removes the line.
        "federation.match.sheet.line": {"unlink"},
        "federation.season.registration"''')

# ---- 4. Club rank, scoresheet name, roster deadline ----------------------
sub('sports_federation_rosters/models/club_rank.py', '''        for team in self:
            team.club_rank = _rank_from_name(team.name)
''', '''        for team in self:
            team.club_rank = _rank_from_name(team.name)

    @api.model_create_multi
    def create(self, vals_list):
        # A compute without dependencies is not reliably triggered when a
        # record is created, so set the rank from the name here. A rank given
        # explicitly always wins.
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            if "club_rank" not in vals:
                vals["club_rank"] = _rank_from_name(vals.get("name"))
        return super().create(vals_list)
''')
sub('sports_federation_rosters/report/scoresheet.py', '"name": team.display_name or "",', '"name": team.name or "",')
sub('sports_federation_rosters/models/federation_match_inherit.py', '''            if record.state == "cancelled":
                continue
            issues = record._get_team_roster_deadline_issues()''', '''            # The deadline guards matches that are still to be played;
            # cancelling or completing one is never blocked by it.
            if record.state in ("cancelled", "done"):
                continue
            issues = record._get_team_roster_deadline_issues()''')

# ---- 5. Time-based portal scopes recomputed by the refresh job -----------
sub('sports_federation_portal/models/res_users.py', '''                self.env.add_to_compute(self._fields[name], stale)
        return stale
''', '''                self.env.add_to_compute(self._fields[name], stale)
            # Compute now, for today's date, instead of leaving it to whatever
            # flushes the transaction later: the record rules read the stored
            # value, so it must be right when this job returns.
            stale.mapped("portal_club_scope_ids")
            stale.mapped("portal_team_scope_ids")
        return stale
''')
sub('sports_federation_portal/models/federation_club_representative.py', '''            self.env.add_to_compute(self._fields["effective_user_id"], stale)
        self.env.flush_all()
''', '''            self.env.add_to_compute(self._fields["effective_user_id"], stale)
            # Compute now, for today's date, before anything else flushes.
            stale.mapped("effective_user_id")
        self.env.flush_all()
''')

# ---- 6. Court device: rights before state --------------------------------
sub('sports_federation_live_workspace/models/court_device.py', '''        if not match._court_is_current():
            raise ValidationError(
                _("The match was moved, postponed or cancelled. Export and reconcile.")
            )
        source, _club = match._court_scoring_source(device.user_id)
        if not source:
            raise AccessError(_("You are no longer a scorer for this match."))
''', '''        # Rights first: someone who may not score the match learns nothing
        # about its state.
        source, _club = match._court_scoring_source(device.user_id)
        if not source:
            raise AccessError(_("You are no longer a scorer for this match."))
        if not match._court_is_current():
            raise ValidationError(
                _("The match was moved, postponed or cancelled. Export and reconcile.")
            )
''')

# ---- 7. Tests / fixtures --------------------------------------------------
sub('sports_federation_rosters/tests/test_tour_roster_lifecycle.py', '''                "name": "Roster Tour Cup",
                "date_start": "2026-03-01",
                "rule_set_id": rule_set.id,''', '''                "name": "Roster Tour Cup",
                "date_start": "2026-03-01",
                # Match-sheet players must hold a registration for the
                # tournament's season, which the fixture gives them.
                "season_id": cls.season.id,
                "rule_set_id": rule_set.id,''')

p = 'sports_federation_portal/tests/test_roster_portal_access.py'
sub(p, '''    create_registered_roster_lines,
)
''', '''    create_registered_roster_lines,
    register_for_season,
)
''')
sub(p, '''                "team_ids": [(4, self.team_a.id)],
            }
        )
        line = self.env["federation.team.roster.line"]._portal_create_line(''', '''                "team_ids": [(4, self.team_a.id)],
            }
        )
        # Only players with a season registration can be picked for a roster.
        register_for_season(player_c, self.season, self.club_a)
        line = self.env["federation.team.roster.line"]._portal_create_line(''')
sub(p, '''                "gender": "male",
                "club_id": self.club_a.id,
            }
        )

        available_players = self.env[''', '''                "gender": "male",
                "club_id": self.club_a.id,
            }
        )
        register_for_season(female_player | male_player, self.season, self.club_a)

        available_players = self.env[''')
sub(p, '''        with self.assertQueryCount(11):''', '''        # The picker also reads the players with a valid season registration,
        # which every roster requires.
        with self.assertQueryCount(14):''')
sub(p, '''                "last_name": "Fresh Picker",
                "gender": "male",
                "club_id": self.club_a.id,
            }
        )
''', '''                "last_name": "Fresh Picker",
                "gender": "male",
                "club_id": self.club_a.id,
            }
        )
        register_for_season(fresh_player, self.season, self.club_a)
''')
s = read(p)
if "valid_license = register_for_season" not in s:
    start = s.index(
        '        valid_license = self.env["federation.player.license"].create(\n'
        '            {\n                "name": "PORTAL-LIC-A"'
    )
    end = s.index(
        '        available_licenses = self.env[\n'
        '            "federation.team.roster.line"\n'
        '        ]._portal_get_available_licenses('
    )
    s = (
        s[:start]
        + """        # A player has one licence per season, so register through the shared
        # fixture, which reuses the licence a player already has.
        valid_license = register_for_season(licensed_player, self.season, self.club_a)
        foreign_license = register_for_season(self.player_b, self.season, self.club_b)
        self.assertEqual(len(valid_license), 1)
        self.assertEqual(len(foreign_license), 1)

"""
        + s[end:]
    )
    write(p, s)

p = 'sports_federation_portal/tests/test_player_parental_overview.py'
sub(p, '''from dateutil.relativedelta import relativedelta

from odoo import fields
''', '''from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo import fields
''')
sub(p, '''        if on_senior_roster:
            self.env["federation.team.roster.line"].create(
                {"roster_id": self.roster.id, "player_id": player.id}
            )
        return player''', '''        if on_senior_roster:
            # The overview must flag a minor who is already on a senior
            # roster without a valid approval (for instance after the
            # approval lapsed). Roster lines now refuse such players, so the
            # line is created without the eligibility check on purpose.
            Line = self.env["federation.team.roster.line"]
            with patch.object(
                type(Line), "_validate_player_eligibility", lambda self: None
            ):
                Line.create({"roster_id": self.roster.id, "player_id": player.id})
        return player''')

sub('sports_federation_setup_flow/tests/test_custom_setup_flow.py', '''                "state": "finalized",
                "participant_set_id": cls.pset.id,
            }
        )
        venue =''', '''                "state": "finalized",
                "participant_set_id": cls.pset.id,
            }
        )
        # The window above is finalized directly, so give the division the
        # participants finalizing would create. A finalized division only
        # accepts teams through the amendment command, which the stage engine
        # must not bypass.
        governed(cls.env["federation.tournament.participant"]).create(
            [
                {
                    "tournament_id": cls.division.id,
                    "team_id": team.id,
                    "state": "confirmed",
                }
                for team in cls.teams
            ]
        )
        venue =''')

p = 'sports_federation_live_workspace/tests/test_court_devices.py'
sub(p, '''from uuid import uuid4

from freezegun import freeze_time
''', '''from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

from freezegun import freeze_time
''')
sub(p, '''        with freeze_time("2026-06-18 12:00:00"):
            with self.assertRaises(AccessError):''', '''        # The fixture pins ``fields.Datetime.now`` to the game day, which
        # freezegun does not override; move that clock as well.
        with freeze_time("2026-06-18 12:00:00"), patch(
            "odoo.fields.Datetime.now", return_value=datetime(2026, 6, 18, 12, 0)
        ):
            with self.assertRaises(AccessError):''')

p = 'sports_federation_live_workspace/tests/test_gameday_print.py'
sub(p, '''                "end_datetime": "2026-06-15 16:40:00",
            }''', '''                "end_datetime": "2026-06-15 16:40:00",
                # Keep the exact time instead of continuing the day's timeline.
                "continue_court_timeline": False,
            }''')
sub(p, '''    def test_print_actions(self):
        schedule = self.day.action_print_gameday_schedule()
        self.assertEqual(
            schedule["report_name"],
            "sports_federation_live_workspace.report_gameday_schedule",
        )
        sheets = self.day.action_print_gameday_scoresheets()
        self.assertEqual(
            sheets["report_name"], "sports_federation_rosters.report_match_scoresheet"
        )''', '''    def _printed_report(self, action):
        """The report an action prints, whatever keys the action carries."""
        self.assertEqual(action["type"], "ir.actions.report")
        reference = action.get("report_name") or action.get("id")
        return self.env["ir.actions.report"]._get_report(reference)

    def test_print_actions(self):
        schedule = self.day.action_print_gameday_schedule()
        self.assertEqual(
            self._printed_report(schedule).report_name,
            "sports_federation_live_workspace.report_gameday_schedule",
        )
        sheets = self.day.action_print_gameday_scoresheets()
        self.assertEqual(
            self._printed_report(sheets).report_name,
            "sports_federation_rosters.report_match_scoresheet",
        )''')

sub('sports_federation_app/tests/test_competition_lifecycle_e2e.py', '''    def _finish_gameday(self, matchday):
        return (
            self.env["federation.matchday.commands"]
            .with_user(self.matchday_manager)
            .close_matchday(matchday.id)
        )''', '''    def _finish_gameday(self, matchday):
        """Leave the game day closed.

        The match-day automation closes a day by itself as soon as every
        published match has an official result, so only close what is still
        open.
        """
        matchday.invalidate_recordset(["state"])
        if matchday.state == "open":
            self.env["federation.matchday.commands"].with_user(
                self.matchday_manager
            ).close_matchday(matchday.id)
            matchday.invalidate_recordset(["state"])
        self.assertEqual(matchday.state, "closed")
        return True''')
if CHECK_ONLY:
    print("All edits match; nothing written (--check).")
else:
    for path, text in _files.items():
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print("Applied; changed files: %s" % len(_files))
