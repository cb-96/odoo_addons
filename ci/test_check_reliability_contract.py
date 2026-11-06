import unittest

from check_reliability_contract import SQL


class TestReliabilitySqlDetection(unittest.TestCase):
    def test_database_cursor_execute_is_detected(self):
        for source in (
            "self.env.cr.execute(query)",
            "event.env.cr.execute(query, params)",
            "cr.execute(query, params)",
        ):
            with self.subTest(source=source):
                self.assertIsNotNone(SQL.search(source))

    def test_orm_service_execute_is_not_misclassified_as_raw_sql(self):
        self.assertIsNone(SQL.search("transition.execute(command)"))


if __name__ == "__main__":
    unittest.main()
