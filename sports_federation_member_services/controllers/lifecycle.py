import base64
from urllib.parse import urlencode
from odoo import http
from odoo.http import request, content_disposition
from odoo.exceptions import AccessError, ValidationError
from .portal import MemberPortal
from ..models.lifecycle import lock


def feedback(text):
    return request.redirect("/my/family?" + urlencode({"feedback": text}))


class FamilyLifecyclePortal(MemberPortal):
    @http.route()
    def family(self, person_id=None, **kw):
        try:
            people = request.env["federation.family.summary"]._rows(person_id)
        except (AccessError, ValueError, TypeError):
            raise request.not_found()
        seasons = (
            request.env["federation.season"].sudo().search([("state", "=", "open")])
        )
        clubs = request.env["federation.club"].sudo().search([("active", "=", True)])
        claims = (
            request.env["federation.guardian.claim"]
            .sudo()
            .search(
                [
                    ("submitted_by_id", "=", request.env.uid),
                    ("company_id", "in", request.env.companies.ids),
                ]
            )
        )
        response = request.render(
            "sports_federation_member_services.family_lifecycle",
            {
                "people": people,
                "seasons": [
                    {"id": s.id, "name": s.name, "start": s.date_start} for s in seasons
                ],
                "clubs": [{"id": c.id, "name": c.name} for c in clubs],
                "claims": [
                    {"id": c.id, "state": c.state, "note": c.decision_note or ""}
                    for c in claims
                ],
                "feedback": kw.get("feedback", ""),
            },
        )
        response.headers["Cache-Control"] = "no-store, private"
        return response

    @http.route()
    def renew(
        self, membership_id, season_id=None, person_id=None, confirmed=None, **kw
    ):
        try:
            with request.env.cr.savepoint():
                if confirmed != "yes" or person_id is None:
                    raise ValidationError("Confirm the named family member.")
                row = request.env["federation.person.membership"].browse(membership_id)
                row._assert_person(person_id)
                row._renew(season_id)
        except (AccessError, ValidationError, ValueError, TypeError):
            return feedback(
                "Renewal not accepted. Refresh the named member and check the current season/status."
            )
        return feedback(
            "Renewal requested. Federation review is next; membership, licence and eligibility are not activated."
        )

    @http.route()
    def upload(self, request_id, person_id=None, confirmed=None, **kw):
        try:
            with request.env.cr.savepoint():
                doc = request.env["federation.person.request"].browse(request_id)
                if confirmed != "yes" or person_id is None or not doc.sudo().exists():
                    raise AccessError("Confirm the named family member.")
                lock(doc.sudo().person_id)
                if doc.sudo().person_id.id != int(person_id) or not doc._allowed():
                    raise AccessError(
                        "Document does not belong to the selected member."
                    )
                doc._upload(request.httprequest.files.get("document"))
        except (AccessError, ValidationError, ValueError, TypeError):
            return feedback(
                "Upload not accepted. Refresh the named member and check current access and document status."
            )
        return feedback(
            "Uploaded for the named member. Federation review is next; upload is not approval or eligibility."
        )

    @http.route(
        "/my/family/memberships/<int:membership_id>/licence",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def licence(self, membership_id, person_id=None, confirmed=None, **kw):
        try:
            with request.env.cr.savepoint():
                if confirmed != "yes" or person_id is None:
                    raise AccessError("Confirm the named member.")
                request.env["federation.person.membership"].browse(
                    membership_id
                )._request_licence(person_id)
        except (AccessError, ValidationError, ValueError, TypeError):
            return feedback(
                "Licence request not accepted. Ask the club/federation to check identity, club and season."
            )
        return feedback(
            "Licence request recorded or reused. Federation activation remains separate."
        )

    @http.route(
        "/my/family/memberships/<int:membership_id>/change",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def change(
        self,
        membership_id,
        person_id=None,
        confirmed=None,
        kind=None,
        reason=None,
        target_club_id=None,
        **kw
    ):
        try:
            with request.env.cr.savepoint():
                if confirmed != "yes" or person_id is None:
                    raise AccessError("Confirm the named member.")
                request.env["federation.person.membership"].browse(
                    membership_id
                )._request_change(kind, person_id, reason, target_club_id)
        except (AccessError, ValidationError, ValueError, TypeError):
            return feedback(
                "Lifecycle request not accepted. Check current status and any pending federation decision."
            )
        return feedback(
            "Membership lifecycle request recorded. Federation owns the next decision; licences, invoices and rosters are unchanged."
        )

    @http.route(
        "/my/family/guardian-request",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def guardian_request(self, reference=None, reason=None, **kw):
        try:
            with request.env.cr.savepoint():
                request.env["federation.guardian.claim"]._submit_claim(
                    reference, reason, request.httprequest.files.get("document")
                )
        except (AccessError, ValidationError, ValueError, TypeError):
            return feedback(
                "Relationship request not accepted. Ask the federation to check the reference and evidence."
            )
        return feedback(
            "Relationship request received. No dependant access is granted until independent federation verification."
        )

    @http.route(
        "/my/family/requests/<int:request_id>/download",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def download(self, request_id, person_id=None, **kw):
        doc = request.env["federation.person.request"].browse(request_id)
        if not doc.sudo().exists():
            raise request.not_found()
        lock(doc.sudo().person_id)
        try:
            if (
                person_id is None
                or int(person_id) != doc.sudo().person_id.id
                or not doc._allowed()
            ):
                raise AccessError("Current document scope required.")
        except (AccessError, ValueError, TypeError):
            raise request.not_found()
        row = doc.sudo()
        if not row.document:
            raise request.not_found()
        return request.make_response(
            base64.b64decode(row.document),
            headers=[
                ("Content-Type", "application/octet-stream"),
                (
                    "Content-Disposition",
                    content_disposition(row.filename or "evidence"),
                ),
                ("Cache-Control", "no-store, private"),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )
