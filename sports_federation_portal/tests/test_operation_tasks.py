from odoo.tests.common import TransactionCase


class TestFederationOperationTasks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager_group = cls.env.ref(
            "sports_federation_base.group_federation_manager"
        )
        cls.manager = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Action Queue Manager",
                    "login": "action.queue.manager@example.com",
                    "group_ids": [(6, 0, [cls.manager_group.id])],
                }
            )
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Action Queue Club", "code": "AQC"}
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Action Queue Team",
                "club_id": cls.club.id,
                "code": "AQCT",
                "category": "senior",
                "gender": "mixed",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Action Queue Season",
                "code": "AQS",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Action Queue Tournament",
                "code": "AQT",
                "season_id": cls.season.id,
                "date_start": "2026-06-01",
                "state": "open",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {"name": "Action Queue Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Action Queue Edition",
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
            }
        )
        cls.tournament.write(
            {
                "edition_id": cls.edition.id,
                "competition_id": cls.competition.id,
            }
        )
        cls.window = cls.env["federation.registration.window"].create(
            {
                "name": "Action Queue Window",
                "edition_id": cls.edition.id,
                "division_id": cls.tournament.id,
                "state": "open",
            }
        )

    def test_blocking_task_cannot_be_manually_acknowledged(self):
        task = self.env["federation.operation.task"].create(
            {
                "name": "Blocking readiness task",
                "task_type": "roster_readiness",
                "audience": "manager",
                "blocking": True,
                "source_model": "test.source",
                "source_record_id": 1,
                "source_key": "test.source:1:roster_readiness",
            }
        )
        with self.assertRaisesRegex(Exception, "Blocking tasks"):
            task.action_acknowledge()
