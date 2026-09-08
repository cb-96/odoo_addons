"""Shared, deliberately narrow workflow transition foundation."""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationWorkflowTransition(models.AbstractModel):
    _name = "federation.workflow.transition"
    _description = "Federation Workflow Transition"

    @api.model
    def execute(
        self,
        records,
        target_state,
        allowed_from,
        values=None,
        state_field="state",
        reason=False,
        reason_required=False,
        expected_revision=None,
        revision_field="revision",
        forbidden_actor_fields=None,
        writer=None,
        event_type=False,
        description=False,
    ):
        """Validate and apply one explicit transition to a recordset.

        Domain services retain responsibility for eligibility. This helper owns
        the mechanics shared by workflows: source-state checks, mandatory
        reasons, optimistic revision checks, separation-of-duty predicates,
        actor/timestamp values supplied by the caller, writes, and audit output.
        """
        records = records.exists()
        if not records:
            raise ValidationError(_("The workflow record no longer exists."))
        allowed_from = set(allowed_from)
        invalid = records.filtered(
            lambda record: record[state_field] not in allowed_from
        )
        if invalid:
            raise ValidationError(
                _(
                    "The transition to %(target)s is not allowed from %(states)s.",
                    target=target_state,
                    states=", ".join(sorted(set(invalid.mapped(state_field)))),
                )
            )
        reason = (reason or "").strip()
        if reason_required and not reason:
            raise ValidationError(_("A reason is required for this transition."))
        if expected_revision is not None:
            stale = records.filtered(
                lambda record: record[revision_field] != int(expected_revision)
            )
            if stale:
                raise ValidationError(
                    _("The record changed in another session. Refresh and retry.")
                )
        forbidden_actor_fields = tuple(forbidden_actor_fields or ())
        actor = self.env.user
        for field_name in forbidden_actor_fields:
            if records.filtered(lambda record: record[field_name] == actor):
                raise ValidationError(
                    _("Separation of duties prevents this transition.")
                )

        previous_states = {record.id: record[state_field] for record in records}
        transition_values = dict(values or {})
        transition_values[state_field] = target_state
        if writer:
            writer(transition_values)
        else:
            records.write(transition_values)

        if event_type:
            self.env["federation.audit.event"].log_record_events(
                event_family="workflow_transition",
                event_type=event_type,
                description=description or _("Workflow transition completed."),
                records=records,
                actor=actor,
                action_name=event_type,
                changed_fields=transition_values.keys(),
                event_on=fields.Datetime.now(),
            )
        return {
            "record_model": records._name,
            "record_ids": records.ids,
            "previous_states": previous_states,
            "current_state": target_state,
            "actor_id": actor.id,
            "reason": reason or False,
        }
