import importlib.util
import tempfile
import textwrap
import unittest
from pathlib import Path


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules_check = load("check_portal_record_rules")
version_check = load("check_migration_versions")


class PortalRecordRuleTests(unittest.TestCase):
    def addon(self, root, acl_rows, rule_xml="", name="sports_federation_x"):
        security = root / name / "security"
        security.mkdir(parents=True)
        header = "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
        (security / "ir.model.access.csv").write_text(
            header + "\n".join(acl_rows) + "\n"
        )
        (security / "rules.xml").write_text(
            "<odoo>%s</odoo>" % textwrap.dedent(rule_xml)
        )

    def rule(
        self, model, groups="'group_federation_portal_club'", domain="[]", perms=""
    ):
        group_field = (
            "<field name='groups' eval=\"[(4, ref(%s))]\"/>" % groups if groups else ""
        )
        return (
            "<record id='r_%s' model='ir.rule'>"
            "<field name='model_id' ref='model_%s'/>"
            "<field name='domain_force'>%s</field>%s%s</record>"
            % (model, model, domain, group_field, perms)
        )

    ACL = (
        "a1,a,model_thing,sports_federation_portal.group_federation_portal_club,1,0,1,0"
    )

    def test_acl_without_rule_is_reported_per_operation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(root, [self.ACL])
            errors = rules_check.check(root, {})
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("read every record" in e for e in errors))
        self.assertTrue(any("create every record" in e for e in errors))

    def test_rule_for_the_same_group_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(root, [self.ACL], self.rule("thing"))
            self.assertEqual(rules_check.check(root, {}), [])

    def test_global_rule_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(root, [self.ACL], self.rule("thing", groups=""))
            self.assertEqual(rules_check.check(root, {}), [])

    def test_rule_for_another_group_does_not_cover(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(
                root,
                [self.ACL],
                self.rule("thing", groups="'group_federation_portal_official'"),
            )
            self.assertEqual(len(rules_check.check(root, {})), 2)

    def test_rule_that_switches_off_an_operation_does_not_cover_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(
                root,
                [self.ACL],
                self.rule("thing", perms="<field name='perm_create' eval='False'/>"),
            )
            errors = rules_check.check(root, {})
        self.assertEqual(len(errors), 1)
        self.assertIn("create every record", errors[0])

    def test_internal_groups_are_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(
                root,
                [
                    "a2,a,model_thing,sports_federation_base.group_federation_user,1,1,1,1"
                ],
            )
            self.assertEqual(rules_check.check(root, {}), [])

    def test_raw_representative_scope_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(
                root,
                [self.ACL],
                self.rule(
                    "thing",
                    domain="[('club_id', 'in', user.representative_ids.mapped('club_id').ids)]",
                ),
            )
            errors = rules_check.check(root, {})
        self.assertEqual(len(errors), 1)
        self.assertIn("user.representative_ids", errors[0])

    def test_unneeded_public_exception_is_reported(self):
        exception = {("model_thing", "group_federation_portal_club"): "x"}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(root, [self.ACL], self.rule("thing"))
            errors = rules_check.check(root, exception)
        self.assertEqual(len(errors), 1)
        self.assertIn("not needed any more", errors[0])

    def test_public_read_only_exception_is_honoured(self):
        exception = {("model_thing", "group_federation_portal_club"): "public data"}
        read_only = "a3,a,model_thing,sports_federation_portal.group_federation_portal_club,1,0,0,0"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(root, [read_only])
            self.assertEqual(rules_check.check(root, exception), [])

    def test_public_exception_never_covers_write(self):
        exception = {("model_thing", "group_federation_portal_club"): "public data"}
        read_write = "a4,a,model_thing,sports_federation_portal.group_federation_portal_club,1,1,0,0"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(root, [read_write])
            errors = rules_check.check(root, exception)
        self.assertTrue(any("write every record" in e for e in errors))

    def test_repository_is_clean(self):
        self.assertEqual(rules_check.check(rules_check.ROOT), [])


class MigrationVersionTests(unittest.TestCase):
    def addon(self, root, version, migrations=()):
        addon = root / "sports_federation_x"
        addon.mkdir()
        (addon / "__manifest__.py").write_text(repr({"version": version}))
        for name in migrations:
            folder = addon / "migrations" / name
            folder.mkdir(parents=True)
            (folder / "post-migrate.py").write_text(
                "def migrate(cr, version):\n    pass\n"
            )

    def test_manifest_behind_its_migrations_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(root, "19.0.1.4.0", ["19.0.2.2.0", "19.0.2.6.0"])
            errors = version_check.check(root)
        self.assertEqual(len(errors), 1)
        self.assertIn("older than its newest migration 19.0.2.6.0", errors[0])

    def test_numeric_not_textual_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(root, "19.0.1.10.0", ["19.0.1.9.0"])
            self.assertEqual(version_check.check(root), [])

    def test_manifest_equal_or_newer_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(root, "19.0.2.6.0", ["19.0.2.6.0", "19.0.1.1.0"])
            self.assertEqual(version_check.check(root), [])

    def test_malformed_folder_and_empty_folder_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(root, "19.0.1.0.0", ["19.0.1.0.0"])
            (root / "sports_federation_x" / "migrations" / "next").mkdir()
            (root / "sports_federation_x" / "migrations" / "19.0.0.9.0").mkdir()
            errors = version_check.check(root)
        self.assertEqual(len(errors), 2)

    def test_repository_is_clean(self):
        self.assertEqual(version_check.check(version_check.ROOT), [])


if __name__ == "__main__":
    unittest.main()
