from collections import defaultdict

from odoo import _, fields, models


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
        # Public requests cannot read the company contact through the public user.
        # Use the schedule configuration with controlled elevation.
        public_timezone = (
            self.env.company.sudo().partner_id.tz or self.env.user.tz or "UTC"
        )
        localized = self.with_context(tz=public_timezone)
        rows = []
        for match in matches:
            slot = match.operational_slot_id or match.published_slot_id
            if not slot and match.operational_status not in ("postponed", "cancelled"):
                continue
            local_start = (
                fields.Datetime.context_timestamp(localized, slot.start_datetime)
                if slot
                else False
            )
            local_end = (
                fields.Datetime.context_timestamp(localized, slot.end_datetime)
                if slot
                else False
            )
            rows.append(
                {
                    "match": match,
                    "slot": slot,
                    "start_local": local_start,
                    "end_local": local_end,
                    "division_label": self._division_label(match),
                    "status": match.operational_status or "as_published",
                }
            )
        rows.sort(
            key=lambda row: (
                (row["start_local"] if row["slot"] else fields.Datetime.now()),
                row["slot"].court_id.id if row["slot"] else 0,
                row["match"].id,
            )
        )
        courts = sorted(
            {row["slot"].court_id for row in rows if row["slot"]},
            key=lambda c: (c.name or "", c.id),
        )
        times = sorted({row["start_local"] for row in rows if row["slot"]})
        grid = {
            (row["start_local"], row["slot"].court_id.id): row
            for row in rows
            if row["slot"]
        }
        by_time = defaultdict(list)
        for row in rows:
            by_time[row["start_local"] if row["slot"] else False].append(row)
        return {
            "publication": publication,
            "matches": rows,
            "courts": courts,
            "times": times,
            "grid": grid,
            "by_time": list(by_time.items()),
        }

    def _division_label(self, match):
        fixture = match.logical_fixture_id
        division = fixture.division_id if fixture else False
        if not division:
            return False
        label = division.name or division.display_name
        gender_labels = {
            "male": _("Men"),
            "female": _("Women"),
            "mixed": _("Mixed"),
        }
        gender = gender_labels.get(division.gender)
        if gender and gender.lower() not in (label or "").lower():
            return _("%(division)s · %(gender)s", division=label, gender=gender)
        return label


    def edition_recent_results(self, edition, division=None, limit=None):
        """Return approved results intended for public competition pages."""
        divisions = edition.tournament_ids.filtered(
            lambda item: item.active
            and item.website_published
            and item.show_public_results
            and item.edition_id == edition
            and (not division or item == division)
        )
        rows = []
        for item in divisions:
            for match in item.get_public_recent_result_matches():
                rows.append(
                    {
                        "match": match,
                        "division": item,
                        "division_label": self._division_label(match),
                    }
                )
        rows.sort(
            key=lambda row: (
                row["match"].date_scheduled
                or fields.Datetime.from_string("1970-01-01"),
                row["match"].id,
            ),
            reverse=True,
        )
        return rows[: max(0, int(limit))] if limit is not None else rows

    def edition_upcoming_matches(self, edition, division=None, limit=6):
        """Return the next spectator-relevant matches from live publications."""
        localized = self.with_context(
            tz=self.env.company.sudo().partner_id.tz or self.env.user.tz or "UTC"
        )
        now_local = fields.Datetime.context_timestamp(localized, fields.Datetime.now())
        rows = []
        for matchday in self.edition_matchdays(edition):
            for row in self.matchday_board(matchday)["matches"]:
                fixture = row["match"].logical_fixture_id
                if division and fixture.division_id != division:
                    continue
                if not row["start_local"] or row["start_local"] < now_local:
                    continue
                public_row = dict(row)
                public_row["matchday"] = matchday
                rows.append(public_row)
        rows.sort(key=lambda row: (row["start_local"], row["match"].id))
        return rows[: max(0, int(limit))]

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
