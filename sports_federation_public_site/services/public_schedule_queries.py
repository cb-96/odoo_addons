from collections import defaultdict

from odoo import fields, models


class PublicScheduleQueries(models.AbstractModel):
    _name = "federation.public.schedule.queries"
    _description = "Public Published Schedule Queries"

    def matchday_board(self, matchday, team_id=None, court_id=None):
        publication = matchday.current_publication_id
        if not publication or publication.state != "live":
            return {
                "publication": False,
                "matches": [],
                "courts": [],
                "times": [],
                "grid": {},
                "by_time": [],
            }
        domain = [
            ("schedule_publication_id", "=", publication.id),
            ("logical_fixture_id", "!=", False),
        ]
        matches = self.env["federation.match"].sudo().search(domain)
        if team_id:
            team_id = int(team_id)
            matches = matches.filtered(
                lambda m: team_id in (m.home_team_id.id, m.away_team_id.id)
            )
        if court_id:
            court_id = int(court_id)
            matches = matches.filtered(
                lambda m: (m.operational_slot_id or m.published_slot_id).court_id.id
                == court_id
            )
        rows = []
        for match in matches:
            slot = match.operational_slot_id or match.published_slot_id
            if not slot and match.operational_status not in ("postponed", "cancelled"):
                continue
            rows.append(
                {
                    "match": match,
                    "slot": slot,
                    "status": match.operational_status or "as_published",
                }
            )
        rows.sort(
            key=lambda row: (
                (row["slot"].start_datetime if row["slot"] else fields.Datetime.now()),
                row["slot"].court_id.id if row["slot"] else 0,
                row["match"].id,
            )
        )
        courts = sorted(
            {row["slot"].court_id for row in rows if row["slot"]},
            key=lambda c: (c.name or "", c.id),
        )
        times = sorted({row["slot"].start_datetime for row in rows if row["slot"]})
        grid = {
            (row["slot"].start_datetime, row["slot"].court_id.id): row
            for row in rows
            if row["slot"]
        }
        by_time = defaultdict(list)
        for row in rows:
            by_time[row["slot"].start_datetime if row["slot"] else False].append(row)
        return {
            "publication": publication,
            "matches": rows,
            "courts": courts,
            "times": times,
            "grid": grid,
            "by_time": list(by_time.items()),
        }

    def edition_matchdays(self, edition):
        return (
            self.env["federation.matchday"]
            .sudo()
            .search(
                [
                    ("edition_id", "=", edition.id),
                    ("current_publication_id.state", "=", "live"),
                ],
                order="date,id",
            )
        )
