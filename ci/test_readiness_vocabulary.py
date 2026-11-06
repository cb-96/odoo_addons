import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "readiness_vocabulary",
    Path(__file__).resolve().parents[1]
    / "sports_federation_base/readiness_vocabulary.py",
)
vocabulary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vocabulary)


def destination():
    return vocabulary.make_destination("federation.matchday", res_id=1)


def blocker(key="b", status=vocabulary.ACTION_NEEDED, **kw):
    values = dict(
        key=key,
        status=status,
        problem="Something is missing.",
        action="Fix it.",
        destination=destination(),
    )
    values.update(kw)
    return vocabulary.make_blocker(**values)


class VocabularyTests(unittest.TestCase):
    def test_exactly_six_user_facing_labels(self):
        self.assertEqual(
            [label for _code, label in vocabulary.SELECTION],
            [
                "Ready",
                "Action needed",
                "Waiting for review",
                "Blocked",
                "Complete",
                "Not applicable",
            ],
        )

    def test_every_status_has_label_and_badge(self):
        for status in vocabulary.STATUSES:
            self.assertIn(status, vocabulary.LABELS)
            self.assertIn(status, vocabulary.BADGE_CLASSES)

    def test_legacy_wording_is_not_part_of_the_vocabulary(self):
        self.assertFalse(vocabulary.LEGACY_LABELS & set(vocabulary.LABELS.values()))

    def test_every_mapping_targets_a_shared_status(self):
        for domain, mapping in vocabulary.STATE_MAPPINGS.items():
            for state, status in mapping.items():
                self.assertIn(status, vocabulary.STATUSES, (domain, state))

    def test_unknown_states_are_never_ready(self):
        for domain in vocabulary.STATE_MAPPINGS:
            self.assertEqual(
                vocabulary.status_for(domain, "something-new"),
                vocabulary.ACTION_NEEDED,
            )
        self.assertEqual(
            vocabulary.status_for("not-a-domain", "ready"), vocabulary.ACTION_NEEDED
        )

    def test_cannot_determine_is_not_eligible(self):
        self.assertEqual(
            vocabulary.status_for("eligibility", "review_required"),
            vocabulary.WAITING_REVIEW,
        )
        self.assertNotEqual(
            vocabulary.status_for("eligibility", "review_required"), vocabulary.READY
        )

    def test_failed_eligibility_and_compliance_block(self):
        self.assertEqual(
            vocabulary.status_for("eligibility", "fail"), vocabulary.BLOCKED
        )
        self.assertEqual(
            vocabulary.status_for("compliance", "non_compliant"), vocabulary.BLOCKED
        )

    def test_internal_states_keep_their_detail(self):
        coverage = vocabulary.STATE_MAPPINGS["coverage"]
        self.assertEqual(
            set(coverage),
            {"unchecked", "not_required", "uncovered", "needs_action", "ready"},
        )
        self.assertEqual(coverage["uncovered"], coverage["needs_action"])


class AggregateTests(unittest.TestCase):
    def test_blocked_wins(self):
        self.assertEqual(
            vocabulary.aggregate(["ready", "action_needed", "blocked"]),
            vocabulary.BLOCKED,
        )

    def test_action_needed_beats_waiting(self):
        self.assertEqual(
            vocabulary.aggregate(["waiting_review", "action_needed", "ready"]),
            vocabulary.ACTION_NEEDED,
        )

    def test_waiting_beats_ready(self):
        self.assertEqual(
            vocabulary.aggregate(["ready", "waiting_review"]),
            vocabulary.WAITING_REVIEW,
        )

    def test_ready_ignores_not_applicable(self):
        self.assertEqual(
            vocabulary.aggregate(["ready", "not_applicable"]), vocabulary.READY
        )

    def test_nothing_applicable(self):
        self.assertEqual(vocabulary.aggregate([]), vocabulary.NOT_APPLICABLE)
        self.assertEqual(
            vocabulary.aggregate(["not_applicable"]), vocabulary.NOT_APPLICABLE
        )

    def test_complete_only_when_all_applicable_are_complete(self):
        self.assertEqual(
            vocabulary.aggregate(["complete", "not_applicable"]),
            vocabulary.COMPLETE,
        )
        self.assertEqual(vocabulary.aggregate(["complete", "ready"]), vocabulary.READY)

    def test_unknown_status_is_rejected(self):
        with self.assertRaises(ValueError):
            vocabulary.aggregate(["ready", "fine"])

    def test_ratio_status(self):
        self.assertEqual(vocabulary.ratio_status(8, 8), vocabulary.READY)
        self.assertEqual(vocabulary.ratio_status(7, 8), vocabulary.ACTION_NEEDED)
        self.assertEqual(
            vocabulary.ratio_status(7, 8, waiting=1), vocabulary.WAITING_REVIEW
        )
        self.assertEqual(vocabulary.ratio_status(7, 8, blocked=1), vocabulary.BLOCKED)
        self.assertEqual(vocabulary.ratio_status(0, 0), vocabulary.NOT_APPLICABLE)
        self.assertEqual(vocabulary.format_ratio(7, 8), "7 / 8 ready")


class BlockerContractTests(unittest.TestCase):
    def test_blocker_states_problem_owner_deadline_action_destination(self):
        item = blocker(owner="Club representative", deadline="2026-11-08")
        for field in ("problem", "owner", "deadline", "action", "destination"):
            self.assertIn(field, item)
        self.assertEqual(item["owner_state"], vocabulary.OWNER_ASSIGNED)

    def test_missing_owner_and_deadline_stay_visible(self):
        item = blocker()
        self.assertIsNone(item["owner"])
        self.assertIsNone(item["deadline"])
        self.assertEqual(item["owner_state"], vocabulary.OWNER_UNASSIGNED)

    def test_problem_action_and_destination_are_required(self):
        with self.assertRaises(ValueError):
            blocker(problem=" ")
        with self.assertRaises(ValueError):
            blocker(action="")
        with self.assertRaises(ValueError):
            blocker(destination=None)
        with self.assertRaises(ValueError):
            blocker(destination={"model": ""})

    def test_blocker_needs_an_attention_status(self):
        with self.assertRaises(ValueError):
            blocker(status=vocabulary.READY)

    def test_destination_needs_a_record_or_domain(self):
        with self.assertRaises(ValueError):
            vocabulary.make_destination("federation.match")
        with self.assertRaises(ValueError):
            vocabulary.make_destination("", res_id=1)
        with self.assertRaises(ValueError):
            vocabulary.make_destination("federation.match", res_id=1, view="kanban")
        listed = vocabulary.make_destination(
            "federation.match", domain=[("id", "in", [1, 2])], view="list"
        )
        self.assertEqual(listed["domain"], [["id", "in", [1, 2]]])

    def test_attention_component_must_explain_itself(self):
        for status in vocabulary.ATTENTION:
            with self.assertRaises(ValueError):
                vocabulary.make_component("rosters", status, "7 / 8 ready")
            vocabulary.make_component(
                "rosters", status, "7 / 8 ready", blockers=[blocker(status=status)]
            )

    def test_quiet_components_need_no_blocker(self):
        for status in (
            vocabulary.READY,
            vocabulary.COMPLETE,
            vocabulary.NOT_APPLICABLE,
        ):
            vocabulary.make_component("courts", status, "Ready")


class ProjectionTests(unittest.TestCase):
    def component(self, key, status, **kw):
        blockers = (
            [blocker(key=key, status=status, **kw)]
            if status in vocabulary.ATTENTION
            else []
        )
        return vocabulary.make_component(key, status, status, blockers=blockers)

    def test_all_ready_game_day_can_run(self):
        result = vocabulary.project(
            [self.component(key, "ready") for key in vocabulary.COMPONENT_ORDER]
        )
        self.assertEqual(result["overall"], vocabulary.READY)
        self.assertTrue(result["can_run"])
        self.assertEqual(result["blockers"], [])

    def test_one_open_component_stops_the_game_day(self):
        result = vocabulary.project(
            [
                self.component("schedule", "ready"),
                self.component("lineups", "action_needed"),
                self.component("courts", "ready"),
            ]
        )
        self.assertEqual(result["overall"], vocabulary.ACTION_NEEDED)
        self.assertFalse(result["can_run"])
        self.assertEqual([b["key"] for b in result["blockers"]], ["lineups"])

    def test_waiting_for_review_does_not_run(self):
        result = vocabulary.project([self.component("schedule", "waiting_review")])
        self.assertEqual(result["overall"], vocabulary.WAITING_REVIEW)
        self.assertFalse(result["can_run"])

    def test_nothing_to_check_is_not_runnable(self):
        result = vocabulary.project([])
        self.assertEqual(result["overall"], vocabulary.NOT_APPLICABLE)
        self.assertFalse(result["can_run"])

    def test_components_follow_the_canonical_order(self):
        result = vocabulary.project(
            [
                self.component("compliance", "ready"),
                self.component("courts", "ready"),
                self.component("schedule", "ready"),
                self.component("extra", "ready"),
                self.component("rosters", "ready"),
            ]
        )
        self.assertEqual(
            [item["key"] for item in result["components"]],
            ["schedule", "rosters", "courts", "compliance", "extra"],
        )

    def test_blockers_are_sorted_by_severity_then_deadline(self):
        result = vocabulary.project(
            [
                self.component("rosters", "action_needed", deadline="2026-11-01"),
                self.component("officials", "action_needed", deadline="2026-10-01"),
                self.component("eligibility", "blocked", deadline="2026-12-01"),
                self.component("schedule", "waiting_review"),
            ]
        )
        self.assertEqual(
            [item["key"] for item in result["blockers"]],
            ["eligibility", "officials", "rosters", "schedule"],
        )

    def test_duplicate_components_are_rejected(self):
        with self.assertRaises(ValueError):
            vocabulary.project(
                [self.component("rosters", "ready"), self.component("rosters", "ready")]
            )

    def test_example_from_the_backlog(self):
        result = vocabulary.project(
            [
                vocabulary.make_component("schedule", "ready", "Ready"),
                vocabulary.make_component(
                    "rosters", "ready", "8 / 8 ready", ready=8, total=8
                ),
                vocabulary.make_component(
                    "lineups",
                    "action_needed",
                    "7 / 8 ready",
                    blockers=[blocker("lineups")],
                    ready=7,
                    total=8,
                ),
                vocabulary.make_component(
                    "officials",
                    "action_needed",
                    "22 / 24 ready",
                    blockers=[blocker("officials")],
                    ready=22,
                    total=24,
                ),
                vocabulary.make_component("courts", "ready", "Ready"),
                vocabulary.make_component("eligibility", "ready", "Ready"),
                vocabulary.make_component("compliance", "ready", "Ready"),
            ]
        )
        self.assertEqual(result["overall"], vocabulary.ACTION_NEEDED)
        self.assertEqual(len(result["blockers"]), 2)


if __name__ == "__main__":
    unittest.main()
