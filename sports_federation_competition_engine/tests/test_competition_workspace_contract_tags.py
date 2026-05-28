from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("-at_install", "post_install", "sf_ws_read_model_contract")
class TestCompetitionWorkspaceReadModelContractTag(TransactionCase):
    def test_read_model_contract_tag_is_discoverable(self):
        self.assertIsNotNone(
            self.env["federation.competition.workspace.read.model.service"]
        )


@tagged("-at_install", "post_install", "sf_ws_write_guard_contract")
class TestCompetitionWorkspaceWriteGuardContractTag(TransactionCase):
    def test_write_guard_contract_tag_is_discoverable(self):
        self.assertIsNotNone(self.env["federation.competition.workspace.service"])


@tagged("-at_install", "post_install", "sf_ws_extension_contract")
class TestCompetitionWorkspaceExtensionContractTag(TransactionCase):
    def test_extension_contract_tag_is_discoverable(self):
        self.assertIsNotNone(self.env["federation.competition.workspace.service"])


@tagged("-at_install", "post_install", "sf_ws_concurrency_contract")
class TestCompetitionWorkspaceConcurrencyContractTag(TransactionCase):
    def test_concurrency_contract_tag_is_discoverable(self):
        self.assertIsNotNone(self.env["federation.competition.workspace.service"])


@tagged("-at_install", "post_install", "sf_ws_acl_contract")
class TestCompetitionWorkspaceAclContractTag(TransactionCase):
    def test_acl_contract_tag_is_discoverable(self):
        self.assertIsNotNone(self.env["federation.competition.workspace.service"])
