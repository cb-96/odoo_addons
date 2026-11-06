"""Seed a disposable walkthrough database. Run inside ``odoo shell``.

Creates role accounts and reference data only. The competition itself is
created by the walkthrough agent through the real UI, because creating it here
would skip the steps under test. Never run this against a shared or production
database: it refuses to run when walkthrough accounts already exist.

Prints one line ``SF_WALKTHROUGH_SEED=<json>`` with logins, generated passwords
and any seed step that failed (so the agent can complete it in the UI).
"""

import json
import secrets
from datetime import date, timedelta

from odoo import Command

LOGIN_DOMAIN = "walkthrough.invalid"
report = {"accounts": {}, "data": {}, "failed_steps": []}


def ref(xmlid):
    return env.ref(xmlid).id  # noqa: F821 - provided by odoo shell


def step(name, func):
    try:
        with env.cr.savepoint():  # noqa: F821
            report["data"][name] = func()
    except Exception as exc:  # noqa: BLE001 - report and continue
        report["failed_steps"].append({"step": name, "error": f"{type(exc).__name__}: {exc}"})


def make_user(role, name, groups):
    login = f"{role}@{LOGIN_DOMAIN}"
    password = secrets.token_urlsafe(18)
    user = env["res.users"].with_context(no_reset_password=True).create(  # noqa: F821
        {
            "name": name,
            "login": login,
            "email": login,
            "password": password,
            "group_ids": [Command.set([ref(xmlid) for xmlid in groups])],
        }
    )
    report["accounts"][role] = {"login": login, "password": password, "user_id": user.id}
    return user


if env["res.users"].search_count([("login", "=like", f"%@{LOGIN_DOMAIN}")]):  # noqa: F821
    raise SystemExit("Walkthrough accounts already exist; use a fresh disposable database.")

INTERNAL = ["base.group_user", "sports_federation_base.group_federation_user"]
users = {}


def seed_internal_users():
    users["organiser"] = make_user(
        "organiser",
        "Walkthrough Organiser",
        INTERNAL
        + [
            "sports_federation_base.group_federation_manager",
            "sports_federation_competition_core.group_competition_administrator",
            "sports_federation_registration.group_registration_manager",
            "sports_federation_format.group_competition_designer",
            "sports_federation_calendar.group_calendar_planner",
            "sports_federation_scheduling.group_schedule_planner",
            "sports_federation_schedule_approval.group_schedule_approver",
        ],
    )
    users["schedule_approver"] = make_user(
        "schedule_approver",
        "Walkthrough Schedule Approver",
        INTERNAL + ["sports_federation_schedule_approval.group_schedule_approver"],
    )
    users["gameday_manager"] = make_user(
        "gameday_manager",
        "Walkthrough Gameday Manager",
        INTERNAL + ["sports_federation_matchday.group_matchday_manager"],
    )
    users["court_operator"] = make_user("court_operator", "Walkthrough Court Operator", INTERNAL)
    users["result_validator"] = make_user(
        "result_validator",
        "Walkthrough Result Validator",
        INTERNAL + ["sports_federation_result_control.group_result_validator"],
    )
    users["result_approver"] = make_user(
        "result_approver",
        "Walkthrough Result Approver",
        INTERNAL + ["sports_federation_result_control.group_result_approver"],
    )
    return sorted(users)


def seed_reference_data():
    today = date.today()
    season = env["federation.season"].create(  # noqa: F821
        {
            "name": f"Walkthrough Season {today.year}",
            "date_start": today - timedelta(days=30),
            "date_end": today + timedelta(days=330),
        }
    )
    rule_set = env["federation.rule.set"].create(  # noqa: F821
        {
            "name": "Walkthrough Rules (14 per gameday, 12 per match)",
            "gameday_roster_max_size": 14,
            "match_player_max_size": 12,
        }
    )
    competition = env["federation.competition"].create(  # noqa: F821
        {"name": "Walkthrough League", "competition_type": "league", "rule_set_id": rule_set.id}
    )
    venue = env["federation.venue"].create({"name": "Walkthrough Sports Hall"})  # noqa: F821
    courts = env["federation.playing.area"].create(  # noqa: F821
        [{"name": f"Court {number}", "venue_id": venue.id} for number in (1, 2)]
    )
    clubs = env["federation.club"].create(  # noqa: F821
        [{"name": f"Walkthrough Club {letter}"} for letter in "ABCD"]
    )
    teams = env["federation.team"].create(  # noqa: F821
        [{"name": f"{club.name} First Team", "club_id": club.id} for club in clubs]
    )
    licence_count = 0
    for team in teams:
        for number in range(1, 17):
            player = env["federation.player"].create(  # noqa: F821
                {
                    "first_name": team.club_id.name.split()[-1],
                    "last_name": f"Player {number:02d}",
                    "birth_date": date(1995, 1, 1) + timedelta(days=number * 37),
                    "gender": "male" if number % 2 else "female",
                }
            )
            licence = env["federation.player.license"].create(  # noqa: F821
                {
                    "name": f"WT-{team.id}-{number:02d}",
                    "player_id": player.id,
                    "season_id": season.id,
                    "club_id": team.club_id.id,
                    "issue_date": season.date_start,
                    "expiry_date": season.date_end,
                }
            )
            licence.action_activate()
            licence_count += 1
    report["data"]["ids"] = {
        "season": season.id,
        "rule_set": rule_set.id,
        "competition": competition.id,
        "venue": venue.id,
        "courts": courts.ids,
        "clubs": clubs.ids,
        "teams": teams.ids,
    }
    return {"teams": len(teams), "licensed_players": licence_count}


def seed_portal_accounts():
    clubs = env["federation.club"].search(  # noqa: F821
        [("name", "like", "Walkthrough Club")], order="name"
    )
    portal = ["base.group_portal", "sports_federation_portal.group_federation_portal_club"]
    for role, club in (("club_representative", clubs[0]), ("other_club_representative", clubs[1])):
        user = make_user(role, f"Walkthrough {club.name} Contact", portal)
        env["federation.club.representative"].create(  # noqa: F821
            {
                "club_id": club.id,
                "partner_id": user.partner_id.id,
                "user_id": user.id,
                "role_type_id": ref("sports_federation_portal.role_type_competition_contact"),
            }
        )
    official = make_user(
        "official",
        "Walkthrough Official",
        ["base.group_portal", "sports_federation_portal.group_federation_portal_official"],
    )
    env["federation.referee"].create({"name": official.name, "user_id": official.id})  # noqa: F821
    return ["club_representative", "other_club_representative", "official"]


step("internal_accounts", seed_internal_users)
step("reference_data", seed_reference_data)
step("portal_accounts", seed_portal_accounts)
env.cr.commit()  # noqa: F821
print("SF_WALKTHROUGH_SEED=" + json.dumps(report, sort_keys=True), flush=True)
