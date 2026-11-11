"""Simulated CI/CD failure scenarios. Every agent receives the SAME dict."""

SCENARIOS = {
    "A": {
        "id": "A",
        "title": "Unit tests fail after a code change (normal)",
        "pipeline": {"run_id": 1042, "branch": "main", "status": "failed", "failed_stage": "test"},
        "logs": (
            "[build] pip install -r requirements.txt ... OK\n"
            "[build] Build succeeded in 48s\n"
            "[test] pytest -q\n"
            "[test] FAILED tests/test_cart.py::test_discount_applied - AssertionError: expected 90.0, got 100.0\n"
            "[test] FAILED tests/test_cart.py::test_bulk_discount - AssertionError: expected 255.0, got 300.0\n"
            "[test] 2 failed, 118 passed in 31s\n"
            "[pipeline] Stage 'test' failed; deploy skipped"
        ),
        "tests": {"ran": True, "total": 120, "passed": 118, "failed": 2, "failures": [
            {"id": "tests/test_cart.py::test_discount_applied",
             "error": "AssertionError: expected 90.0, got 100.0", "covers": "cart/pricing.py"},
            {"id": "tests/test_cart.py::test_bulk_discount",
             "error": "AssertionError: expected 255.0, got 300.0", "covers": "cart/pricing.py"}]},
        "changes": [{"sha": "a1b2c3d", "author": "dev1", "msg": "Refactor discount calculation",
                     "files": ["cart/pricing.py"]}],
        "dependencies": {"changed": [], "unresolved": [], "warnings": []},
        "health": {"checked": False, "status_code": None, "retries": 0, "error": None},
        "history": {"last_success_sha": "9f8e7d6", "recent_runs": ["pass", "pass", "pass", "fail"],
                    "flaky_tests": []},
    },
    "B": {
        "id": "B",
        "title": "Build blocked by dependency conflict, with a flaky test nearby (critical, mixed signals)",
        "pipeline": {"run_id": 1051, "branch": "release/2.4", "status": "failed", "failed_stage": "build"},
        "logs": (
            "[build] pip install -r requirements.txt\n"
            "[build] ERROR: Cannot install pandas==2.4.0 and numpy<2.0 because these package versions have conflicting dependencies.\n"
            "[build] ERROR: pandas 2.4.0 is not available on the configured index (latest: 2.2.3)\n"
            "[quick-tests] FAILED tests/test_sync.py::test_async_timeout - TimeoutError: no response in 5s\n"
            "[quick-tests] 1 failed, 119 passed in 36s (parallel job, independent of the build)\n"
            "[pipeline] Stage 'build' failed; release blocked"
        ),
        "tests": {"ran": True, "total": 120, "passed": 119, "failed": 1, "failures": [
            {"id": "tests/test_sync.py::test_async_timeout",
             "error": "TimeoutError: no response in 5s", "covers": "sync/worker.py"}]},
        "changes": [{"sha": "b7c8d9e", "author": "dev2", "msg": "Bump pandas to 2.4.0",
                     "files": ["requirements.txt"]}],
        "dependencies": {"changed": ["pandas 2.1.4 -> 2.4.0"],
                         "unresolved": ["pandas==2.4.0 (latest on index: 2.2.3)"],
                         "warnings": ["numpy<2.0 pin conflicts with newer pandas"]},
        "health": {"checked": False, "status_code": None, "retries": 0, "error": None},
        "history": {"last_success_sha": "5a4b3c2", "recent_runs": ["pass", "fail", "pass", "fail"],
                    "flaky_tests": ["tests/test_sync.py::test_async_timeout"]},
    },
    "C": {
        "id": "C",
        "title": "Tests pass, deployment health checks fail (post-release)",
        "pipeline": {"run_id": 1063, "branch": "main", "status": "failed", "failed_stage": "deploy"},
        "logs": (
            "[build] Build succeeded in 52s\n"
            "[test] 120 passed in 33s\n"
            "[deploy] Rolling out v2.5.0 to production\n"
            "[deploy] Health check GET /healthz -> 503 (attempt 3/3)\n"
            "[app] KeyError: 'PAYMENT_API_URL' during startup\n"
            "[pipeline] Stage 'deploy' failed health verification"
        ),
        "tests": {"ran": True, "total": 120, "passed": 120, "failed": 0, "failures": []},
        "changes": [{"sha": "c4d5e6f", "author": "dev3",
                     "msg": "Add payment gateway client; new env var PAYMENT_API_URL",
                     "files": ["payments/client.py", "config/settings.py"]}],
        "dependencies": {"changed": [], "unresolved": [], "warnings": []},
        "health": {"checked": True, "status_code": 503, "retries": 3,
                   "error": "KeyError: 'PAYMENT_API_URL' during startup", "environment": "production"},
        "history": {"last_success_sha": "1e2d3c4", "recent_runs": ["pass", "pass", "pass", "fail"],
                    "flaky_tests": []},
    },
    "D": {
        "id": "D",
        "title": "Intermittent timeout in unrelated test (edge / ambiguous)",
        "pipeline": {"run_id": 1077, "branch": "main", "status": "failed", "failed_stage": "test"},
        "logs": (
            "[build] Build succeeded in 47s\n"
            "[build] DeprecationWarning: urllib3 v1 support will be removed\n"
            "[test] FAILED tests/test_sync.py::test_async_timeout - TimeoutError: no response in 5s\n"
            "[test] 1 failed, 119 passed in 38s\n"
            "[pipeline] Stage 'test' failed; deploy skipped"
        ),
        "tests": {"ran": True, "total": 120, "passed": 119, "failed": 1, "failures": [
            {"id": "tests/test_sync.py::test_async_timeout",
             "error": "TimeoutError: no response in 5s", "covers": "sync/worker.py"}]},
        "changes": [{"sha": "d0e1f2a", "author": "dev4", "msg": "Update README badges",
                     "files": ["README.md"]}],
        "dependencies": {"changed": [], "unresolved": [], "warnings": ["urllib3 deprecation warning"]},
        "health": {"checked": False, "status_code": None, "retries": 0, "error": None},
        "history": {"last_success_sha": "7c6b5a4", "recent_runs": ["pass", "fail", "pass", "fail"],
                    "flaky_tests": ["tests/test_sync.py::test_async_timeout"]},
    },
}

EXPECTED_CATEGORY = {"A": "TEST_FAILURE", "B": "DEPENDENCY_ISSUE",
                     "C": "DEPLOYMENT_HEALTH", "D": "TEST_FAILURE"}

# Documented limitations: agents whose rules are misled by the mixed signals in scenario B
EXPECTED_OVERRIDES = {("B", "Simple Reflex"): "TEST_FAILURE", ("B", "Model-Based Reflex"): "TEST_FAILURE"}
