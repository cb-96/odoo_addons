from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from ..lifecycle_policy import membership_label, licence_valid


class FamilySummary(models.AbstractModel):
    _name = "federation.family.summary"
    _description = "Current Scoped Family Lifecycle Summary"

    @api.model
    def _rows(self, person_id=None):
        membership_model = self.env["federation.person.membership"]
        personal_ids = membership_model._person_ids()
        ids = membership_model._membership_person_ids()
        if person_id is not None:
            if int(person_id) not in ids:
                raise AccessError(
                    _("This family member is no longer in your current scope.")
                )
            ids = [int(person_id)]
        people = self.env["res.partner"].sudo().browse(ids).exists()
        result = []
        for person in people:
            memberships = membership_model.sudo().search(
                [
                    ("company_id", "in", self.env.companies.ids),
                    ("person_id", "=", person.id),
                ],
                order="id desc",
                limit=200,
            )
            requests = (
                self.env["federation.person.request"]
                .sudo()
                .search(
                    [
                        ("company_id", "in", self.env.companies.ids),
                        ("person_id", "=", person.id),
                    ],
                    order="id desc",
                    limit=200,
                )
            )
            request_rows = []
            for doc in requests:
                if not doc.with_user(self.env.user)._allowed():
                    continue
                request_rows.append(
                    {
                        "id": doc.id,
                        "person_id": person.id,
                        "name": doc.name,
                        "purpose": doc.purpose,
                        "state": "verified" if doc._current_verified() else doc.state,
                        "deadline": doc.deadline,
                        "note": doc.review_note or "",
                        "revision": doc.document_revision,
                        "can_upload": doc.state in ("requested", "returned"),
                        "owner": (
                            _("Member or verified guardian")
                            if doc.state in ("requested", "returned")
                            else _("Federation document reviewer")
                        ),
                    }
                )
            member_rows = []
            for row in memberships:
                if not row.with_user(self.env.user)._member_allowed():
                    continue
                player = (
                    self.env["federation.player"]
                    .sudo()
                    .search([("person_id", "=", person.id)], limit=1)
                )
                licence = (
                    self.env["federation.player.license"]
                    .sudo()
                    .search(
                        [
                            ("player_id", "=", player.id),
                            ("season_id", "=", row.season_id.id),
                        ],
                        limit=1,
                    )
                    if player
                    else self.env["federation.player.license"].browse()
                )
                valid = (
                    licence_valid(
                        {
                            "state": licence.state,
                            "club_id": licence.club_id.id,
                            "season_id": licence.season_id.id,
                            "issue_date": licence.issue_date,
                            "expiry_date": licence.expiry_date,
                        },
                        fields.Date.today(),
                        row.club_id.id,
                        row.season_id.id,
                    )
                    if licence
                    else False
                )
                lines = (
                    self.env["federation.team.roster.line"]
                    .sudo()
                    .search(
                        [
                            ("player_id", "=", player.id),
                            ("roster_id.season_id", "=", row.season_id.id),
                            ("roster_id.team_id.club_id", "=", row.club_id.id),
                        ]
                    )
                    if player
                    else self.env["federation.team.roster.line"].browse()
                )
                blockers = []
                for line in lines:
                    blockers.extend(line._get_eligibility_reasons())
                if player and player.state != "active":
                    blockers.append(_("Player is not active."))
                if row.role == "player" and not valid:
                    blockers.append(
                        _(
                            "An active date-valid licence for this club and season is missing."
                        )
                    )
                payment = _(
                    "Not linked or not available in your billing scope. Finance staff own billing; payment does not activate membership or eligibility."
                )
                invoice_url = False
                event = row.finance_event_id
                if (
                    event
                    and "account_move_id" in event._fields
                    and event.account_move_id
                ):
                    invoice = event.account_move_id.with_user(self.env.user)
                    try:
                        invoice.check_access("read")
                        if (
                            invoice.partner_id.commercial_partner_id
                            == self.env.user.partner_id.commercial_partner_id
                        ):
                            payment = _(
                                "%(state)s; remaining %(amount)s %(currency)s",
                                state=invoice.payment_state,
                                amount=invoice.amount_residual,
                                currency=invoice.currency_id.name,
                            )
                            invoice_url = "/my/invoices/%s" % invoice.id
                    except AccessError:
                        pass
                changes = (
                    self.env["federation.member.change"]
                    .sudo()
                    .search(
                        [
                            ("membership_id", "=", row.id),
                            ("company_id", "in", self.env.companies.ids),
                        ],
                        order="id desc",
                        limit=20,
                    )
                )
                member_rows.append(
                    {
                        "id": row.id,
                        "person_id": person.id,
                        "person": person.name,
                        "club": row.club_id.name,
                        "season": row.season_id.name,
                        "season_start": row.season_id.date_start,
                        "role": row.role,
                        "state": row.state,
                        "membership": _(membership_label(row.state)),
                        "note": row.review_note or "",
                        "licence": (
                            _("Active for this club/season/date")
                            if valid
                            else (
                                _("Request awaiting federation activation")
                                if licence and licence.state == "draft"
                                else _("Missing, expired, cancelled or different club")
                            )
                        ),
                        "payment": payment,
                        "invoice_url": invoice_url,
                        "eligibility": (
                            _("Action needed")
                            if blockers
                            else (
                                _(
                                    "Action needed: choose the relevant roster and competition so eligibility can be checked"
                                )
                                if not lines
                                else _(
                                    "Current roster checks passed; match-day approval remains separate"
                                )
                            )
                        ),
                        "blockers": list(dict.fromkeys(blockers)),
                        "can_licence": row.state == "active"
                        and row.role == "player"
                        and bool(player)
                        and not licence,
                        "owner": (
                            _("Federation membership reviewer")
                            if row.state == "draft"
                            else _(
                                "Member or guardian for requests; club/federation for sporting requirements"
                            )
                        ),
                        "changes": [
                            {
                                "kind": change.kind,
                                "state": change.state,
                                "note": change.decision_note or "",
                                "result": change.result_membership_id.id,
                            }
                            for change in changes
                        ],
                    }
                )
            result.append(
                {
                    "id": person.id,
                    "name": person.name,
                    "self": person == self.env.user.partner_id,
                    "personal": person.id in personal_ids,
                    "memberships": member_rows,
                    "requests": request_rows,
                }
            )
        return result
