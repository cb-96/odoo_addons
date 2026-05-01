from odoo import api, models


class FederationComplianceTargetMixin(models.AbstractModel):
    _name = "federation.compliance.target.mixin"
    _description = "Federation Compliance Target Mixin"

    TARGET_MODEL_SELECTION = [
        ("federation.club", "Club"),
        ("federation.player", "Player"),
        ("federation.referee", "Referee"),
        ("federation.venue", "Venue"),
        ("federation.club.representative", "Club Representative"),
    ]

    TARGET_FIELD_MAP = {
        "federation.club": "club_id",
        "federation.player": "player_id",
        "federation.referee": "referee_id",
        "federation.venue": "venue_id",
        "federation.club.representative": "club_representative_id",
    }

    @api.model
    def _compliance_target_model_selection(self):
        """Return the supported compliance target models."""
        return list(self.TARGET_MODEL_SELECTION)

    @api.model
    def _compliance_target_label_map(self):
        """Return compliance target labels keyed by model name."""
        return dict(self._compliance_target_model_selection())

    @api.model
    def _compliance_target_field_map(self):
        """Return compliance target fields keyed by model name."""
        return dict(self.TARGET_FIELD_MAP)

    @api.model
    def _compliance_get_target_field_name(self, target_model):
        """Return the field name used for a compliance target model."""
        return self._compliance_target_field_map().get(target_model)

    def _compliance_get_target_record(self, target_model=None):
        """Return the resolved target record for the current record."""
        self.ensure_one()
        if target_model:
            field_name = self._compliance_get_target_field_name(target_model)
            return getattr(self, field_name, False) if field_name else False

        for field_name in self._compliance_target_field_map().values():
            target_record = getattr(self, field_name, False)
            if target_record:
                return target_record
        return False

    def _compliance_get_target_display(self, target_model=None):
        """Return a normalized display value for the resolved target."""
        self.ensure_one()
        target_record = self._compliance_get_target_record(target_model=target_model)
        if not target_record:
            return "Not set"
        return (
            target_record.display_name
            or getattr(target_record, "name", False)
            or "Not set"
        )
