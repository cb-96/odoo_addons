# Testing Guide

Last updated: 2026-05-18
Owner: Federation Platform Team

This guide explains the project's test taxonomy, how to write tests for each
category, and how to keep query-budget assertions current.

---

## 1. Test Taxonomy

The project uses three test classes depending on what is being tested:

### `TransactionCase` — ORM-level unit and integration tests

Used for: model methods, computed fields, `@api.constrains` validators,
wizards, services, and controller methods that are tested by injecting a mock
`request` object (no real HTTP).

Each test runs inside a savepoint that is rolled back after the test, so data
does not carry between tests. It is the **default choice** for new tests.

```python
from odoo.tests.common import TransactionCase

class TestFederationClub(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create({
            "name": "Test Club",
            "code": "TC01",
        })

    def test_code_must_be_unique(self):
        with self.assertRaises(Exception):
            self.env["federation.club"].create({"name": "Dup", "code": "TC01"})
            self.env.cr.flush()
```

**Put shared fixtures in `setUpClass`.** Fixtures created there are shared
across all test methods (and rolled back as a unit at the end of the class).
Fixtures created inside individual test methods are rolled back after each
method.

### `HttpCase` — end-to-end HTTP smoke tests

Used for: verifying that routes return the expected HTTP status code, CSRF
token handling, portal login flows.

Requires a real database and a running Odoo HTTP server. These tests must be
tagged `@tagged("-at_install", "post_install")` so they run after all modules
are loaded.

```python
from odoo.tests.common import HttpCase, tagged

@tagged("-at_install", "post_install")
class TestPublicSiteHttpSmoke(HttpCase):

    def test_tournaments_list_returns_200(self):
        response = self.url_open("/tournaments")
        self.assertEqual(response.status_code, 200)
```

HTTP tests are significantly slower than `TransactionCase` tests and require
`sports_federation_portal` to be installed. Use the
`unittest.SkipTest` pattern to skip gracefully when optional modules are absent:

```python
@classmethod
def setUpClass(cls):
    super().setUpClass()
    with cls.registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        if not env.ref("sports_federation_portal.group_federation_portal_club",
                       raise_if_not_found=False):
            raise unittest.SkipTest("sports_federation_portal not installed")
```

### `TransactionCase` with a mock `request` — controller unit tests

Used for: testing controller methods that call `request.env` without running an
HTTP server. Inject a `SimpleNamespace` as the request stub and patch the
`request` module attribute.

```python
from types import SimpleNamespace
from unittest.mock import patch

class TestCompetitionsApiJson(TransactionCase):

    def test_rate_limit_blocks_after_limit(self):
        request_stub = SimpleNamespace(
            env=self.env,
            httprequest=SimpleNamespace(remote_addr="198.51.100.1", headers={}),
        )
        controller = PublicTournamentHubController()
        with patch(
            "odoo.addons.sports_federation_public_site"
            ".controllers.public_competitions.request",
            request_stub,
        ):
            result = controller.competitions_api_json()
        self.assertIn("tournaments", result)
```

---

## 2. Shared Fixture Patterns

### Basic club/team/season fixture

This fixture appears in almost every module's test. Copy it as a starting point
rather than re-inventing it.

```python
@classmethod
def setUpClass(cls):
    super().setUpClass()
    cls.club = cls.env["federation.club"].create({
        "name": "Fixture Club", "code": "FXC",
    })
    cls.team_a = cls.env["federation.team"].create({
        "name": "Team A", "club_id": cls.club.id, "code": "TFA",
    })
    cls.team_b = cls.env["federation.team"].create({
        "name": "Team B", "club_id": cls.club.id, "code": "TFB",
    })
    cls.season = cls.env["federation.season"].create({
        "name": "Test Season",
        "code": "TS26",
        "date_start": "2026-01-01",
        "date_end": "2026-12-31",
    })
    cls.tournament = cls.env["federation.tournament"].create({
        "name": "Test Tournament",
        "code": "TT26",
        "season_id": cls.season.id,
        "date_start": "2026-06-01",
        "state": "open",
    })
```

### Portal ownership fixture

When testing portal access, create users with the portal club group and link
them to a club via `federation.club.representative`. This pattern is used
throughout `sports_federation_portal/tests/`.

```python
from odoo import SUPERUSER_ID, api
from odoo.tests.common import TransactionCase

class TestPortalOwnership(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.club_a = cls.env["federation.club"].create(
            {"name": "Portal Club A", "code": "PCA"}
        )
        cls.club_b = cls.env["federation.club"].create(
            {"name": "Portal Club B", "code": "PCB"}
        )

        def _make_user(name, login):
            return (
                cls.env["res.users"]
                .with_context(no_reset_password=True)
                .create({
                    "name": name,
                    "login": login,
                    "email": login,
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                })
            )

        cls.user_a = _make_user("User A", "usera@example.com")
        cls.user_b = _make_user("User B", "userb@example.com")

        # Link users to clubs via representative records
        for user, club in ((cls.user_a, cls.club_a), (cls.user_b, cls.club_b)):
            cls.env["federation.club.representative"].create({
                "club_id": club.id,
                "user_id": user.id,
                "role_type_id": cls.env.ref(
                    "sports_federation_portal.role_type_competition_contact"
                ).id,
            })

    def test_club_a_cannot_see_club_b_roster(self):
        """Portal user A must not be able to reach a roster belonging to club B."""
        privilege = self.env["federation.portal.privilege"]
        with self.assertRaises(AccessError):
            privilege.with_user(self.user_a).portal_search_by_id(
                "federation.team.roster",
                self.club_b_roster.id,
            )
```

See `sports_federation_portal/tests/test_portal_ownership_guard.py` for a
complete working example.

### Frozen-time fixture for time-sensitive logic

For rate limiting, deadlines, and scheduling logic, freeze time with
`unittest.mock.patch.object`:

```python
from datetime import datetime
from unittest.mock import patch

def test_consume_blocks_after_limit(self):
    service = self.env["federation.request.rate.limit"].sudo()
    frozen_time = datetime(2026, 6, 1, 12, 0, 0)
    with patch.object(type(service), "_get_now", return_value=frozen_time):
        first = service.consume("public_competitions_json", "ip:10.0.0.1")
        second = service.consume("public_competitions_json", "ip:10.0.0.1")
    self.assertTrue(first["allowed"])
    self.assertFalse(second["allowed"])  # limit is 1 in this test
```

---

## 3. Query-Count Budgets

Several test suites assert exact query counts to catch N+1 regressions:

```python
def test_public_discovery_helpers_stay_within_query_budget(self):
    with self.assertQueryCount(1):
        featured = self.env["federation.tournament"].get_public_featured_tournaments(limit=4)
    with self.assertQueryCount(3):
        recent = self.env["federation.tournament"].get_public_recent_result_tournaments(limit=4)
```

**Rules:**
- `assertQueryCount(N)` fails if the block executes more or fewer than `N`
  queries. Fewer queries is also a failure because it may indicate a test
  regression (e.g., empty dataset masking missing queries).
- Budgets live in `PERFORMANCE_BASELINES.md`. If you lower a budget, update
  that file.
- If your change legitimately increases a query count, update the assertion
  and add a comment explaining why, and update `PERFORMANCE_BASELINES.md`.

---

## 4. EXPLAIN Snapshot Tests

For critical query paths, the CI runs `ci/check_explain_snapshots.py`, which
compares `EXPLAIN` output against stored snapshots in `ci/explain_snapshots/`.

To add a new snapshot:

```bash
# Connect to the CI database and run EXPLAIN
docker compose exec db psql -U odoo -d odoo_ci_test -c \
  "EXPLAIN SELECT ... FROM federation_tournament WHERE ..."
# Save the output to ci/explain_snapshots/<descriptive_name>.txt
```

A snapshot regression (e.g., a sequential scan replacing an index scan) fails
CI. Review the output, add the necessary index, or update the snapshot with
a comment explaining the regression is acceptable.

---

## 5. What to Test for Each Change Type

| Change type | Required test |
|---|---|
| New model field | `test_<model>_<field>_<rule>` validating the constraint or default |
| New `@api.constrains` | One passing case + one failing case |
| New computed field | Verify the value before and after the triggering field changes |
| New wizard | End-to-end test: create input records → call wizard → assert output records (counts, states) |
| New controller route | Either an HTTP smoke test (200/404) or a mock-request unit test |
| Portal write | Always add a cross-club access-denial test in addition to the happy path |
| Standings / schedule logic | `assertQueryCount` + correctness assertion for a minimal dataset |
| Rate limiting | Frozen-time test: N requests pass, N+1 is blocked; verify `Retry-After` header |

---

## 6. Running Tests in CI

```bash
# Run the suite that covers your changed module
bash addons/ci/run_tests.sh --suite competition_core

# Run just one module (faster when iterating)
bash addons/ci/run_tests.sh --module sports_federation_standings

# Run participant readiness discovery guard (fails if post-tests are not discovered)
bash addons/ci/run_tests.sh --suite rosters_readiness_guard

# Equivalent explicit form when you need direct control
bash addons/ci/run_tests.sh --module sports_federation_rosters --test-tags sf_rosters_participant_readiness --require-post-tests 1

# Skip browser bootstrap when the run has no HttpCase/browser coverage
CI_SKIP_BROWSER_BOOTSTRAP=1 bash addons/ci/run_tests.sh --module sports_federation_competition_engine --test-tags sf_competition_workspace --require-post-tests 1

# Run dedicated competition workspace contract suites
CI_SKIP_BROWSER_BOOTSTRAP=1 bash addons/ci/run_tests.sh --module sports_federation_competition_engine --contract-suite ws_read_model
CI_SKIP_BROWSER_BOOTSTRAP=1 bash addons/ci/run_tests.sh --module sports_federation_competition_engine --contract-suite ws_write_guards
CI_SKIP_BROWSER_BOOTSTRAP=1 bash addons/ci/run_tests.sh --module sports_federation_competition_engine --contract-suite ws_extensions
CI_SKIP_BROWSER_BOOTSTRAP=1 bash addons/ci/run_tests.sh --module sports_federation_competition_engine --contract-suite ws_concurrency
CI_SKIP_BROWSER_BOOTSTRAP=1 bash addons/ci/run_tests.sh --module sports_federation_competition_engine --contract-suite ws_acl

# Run all suites (used in final PR validation)
bash addons/ci/run_tests.sh
```

The CI runner produces a results block at the end:

```
════════════════════════════════
  RESULTS
════════════════════════════════
  Exit code:     0
  Tests run:     62
  Tests passed:  62
  Tests failed:  0
  Test errors:   0
════════════════════════════════
```

A non-zero exit code means the CI gate failed. Check the container logs for
the failing test name and traceback:

```bash
docker logs <container-name> 2>&1 | grep -A 20 "FAIL\|ERROR"
```

### Discovery-safe tag convention

For high-risk regression suites, add an explicit class-level tag in addition to the usual install timing tags:

```python
from odoo.tests.common import TransactionCase, tagged

@tagged("-at_install", "post_install", "sf_<module>_<feature>")
class TestFeature(TransactionCase):
    ...
```

Use lowercase snake-case tags prefixed with `sf_` (example: `sf_rosters_participant_readiness`).
This enables deterministic CI selection and allows `--require-post-tests` gating to detect discovery regressions early.

### Critical suite registry

The CI runner enforces a minimum discovered post-test count for critical suites.
This prevents false-green runs where discovery is broken and no tests execute.

| Suite | Default minimum post-tests | Notes |
|---|---|---|
| `competition_core` | 1 | Core workflow sanity gate |
| `portal_public_ops` | 1 | Portal/public ownership and route guard |
| `finance_reporting` | 1 | Finance and reporting guard |
| `release_surfaces` | 1 | Broad release surface guard |
| `people_rosters_rules` | 1 | Domain rules and roster workflow guard |
| `ops_and_notifications` | 1 | Operations and notification guard |
| `rosters_readiness_guard` | 1 | Explicit tag `sf_rosters_participant_readiness` |
| `ws_read_model` | 1 | Explicit tag `sf_ws_read_model_contract` |
| `ws_write_guards` | 1 | Explicit tag `sf_ws_write_guard_contract` |
| `ws_extensions` | 1 | Explicit tag `sf_ws_extension_contract` |
| `ws_concurrency` | 1 | Explicit tag `sf_ws_concurrency_contract` |
| `ws_acl` | 1 | Explicit tag `sf_ws_acl_contract` |

---

## 7. Test File Conventions

- One test file per logical area in `tests/` (e.g., `test_round_robin.py`,
  `test_knockout.py` — not one giant `test_all.py`).
- File names: `test_<noun>.py` (noun = model name, workflow name, or feature).
- Class name: `Test<Topic>` (e.g., `TestRoundRobin`, `TestPortalOwnershipGuard`).
- `setUpClass` creates shared fixtures; individual test methods create only what
  they uniquely need.
- Test method names: `test_<what>_<expected_outcome>` (e.g.,
  `test_duplicate_code_raises_validation_error`).
- Register new test files in `tests/__init__.py` with `from . import test_myfile`.
