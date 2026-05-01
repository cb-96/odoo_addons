from collections import Counter
from pathlib import Path

from lxml import etree

from odoo.tests.common import TransactionCase


class TestDemoDataPack(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        demo_path = (
            Path(__file__).resolve().parents[1] / "demo" / "demo_federation_data.xml"
        )
        cls.demo_path = demo_path
        cls.demo_root = etree.parse(str(demo_path)).getroot()
        cls.records = cls.demo_root.xpath(".//record")
        cls.record_ids = {
            record.get("id") for record in cls.records if record.get("id")
        }

    def test_demo_pack_uses_known_models_and_fields(self):
        registry_models = self.env.registry.models
        model_data = self.env["ir.model.data"]

        for record in self.records:
            model_name = record.get("model")
            record_id = record.get("id")

            self.assertIn(
                model_name,
                registry_models,
                f"Demo record {record_id} uses unknown model {model_name}.",
            )

            model = self.env[model_name]
            for field_node in record.xpath("./field"):
                field_name = field_node.get("name")
                field = model._fields.get(field_name)
                self.assertTrue(
                    field,
                    f"Demo record {record_id} uses unknown field {field_name} on {model_name}.",
                )

                ref_value = field_node.get("ref")
                if ref_value:
                    self.assertIn(
                        field.type,
                        {"many2one", "many2many", "one2many", "reference"},
                        f"Field {field_name} on {model_name} does not support XML refs.",
                    )
                    if "." in ref_value:
                        model_ref = model_data._xmlid_lookup(ref_value)
                        self.assertTrue(
                            model_ref,
                            f"Demo record {record_id} references unknown external id {ref_value}.",
                        )
                    else:
                        self.assertIn(
                            ref_value,
                            self.record_ids,
                            f"Demo record {record_id} references unknown local id {ref_value}.",
                        )

                if (
                    field.type == "selection"
                    and field_node.text
                    and not field_node.get("eval")
                ):
                    selection = field.selection
                    if isinstance(selection, (list, tuple)):
                        allowed_values = {value for value, _label in selection}
                        self.assertIn(
                            field_node.text,
                            allowed_values,
                            (
                                f"Demo record {record_id} uses invalid selection value "
                                f"{field_node.text} for {model_name}.{field_name}."
                            ),
                        )

    def test_demo_pack_has_expected_record_counts(self):
        expected_counts = {
            "federation.club": 3,
            "federation.team": 6,
            "federation.season": 1,
            "federation.rule.set": 1,
            "federation.player": 15,
            "federation.player.license": 15,
            "federation.season.registration": 3,
            "federation.competition": 1,
            "federation.competition.edition": 1,
            "federation.tournament": 1,
            "federation.tournament.stage": 1,
            "federation.tournament.group": 1,
            "federation.tournament.participant": 3,
            "federation.tournament.round": 3,
            "federation.match": 3,
            "federation.team.roster": 3,
            "federation.team.roster.line": 12,
            "federation.match.sheet": 2,
            "federation.match.sheet.line": 8,
        }
        actual_counts = Counter(record.get("model") for record in self.records)
        self.assertEqual(actual_counts, expected_counts)

    def test_demo_pack_covers_match_day_walkthrough(self):
        records_by_id = {
            record.get("id"): record for record in self.records if record.get("id")
        }
        sheet_records = [
            record
            for record in self.records
            if record.get("model") == "federation.match.sheet"
        ]
        match_records = [
            record
            for record in self.records
            if record.get("model") == "federation.match"
        ]

        submitted_sides = {
            record.xpath("./field[@name='side']/text()")[0] for record in sheet_records
        }
        match_states = Counter(
            record.xpath("./field[@name='state']/text()")[0] for record in match_records
        )

        self.assertEqual(submitted_sides, {"home", "away"})
        self.assertEqual(match_states["done"], 1)
        self.assertEqual(match_states["scheduled"], 2)

        for sheet_record in sheet_records:
            roster_ref = sheet_record.xpath("./field[@name='roster_id']/@ref")
            match_ref = sheet_record.xpath("./field[@name='match_id']/@ref")
            self.assertTrue(
                roster_ref, "Every match sheet should point to a demo roster."
            )
            self.assertTrue(
                match_ref, "Every match sheet should point to a demo match."
            )
            self.assertIn(roster_ref[0], records_by_id)
            self.assertIn(match_ref[0], records_by_id)
