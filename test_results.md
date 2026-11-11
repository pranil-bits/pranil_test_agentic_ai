# Test Results

## Scenario A: Unit tests fail after a code change (normal)

| Agent | Category | Action | Category check |
|---|---|---|---|
| Simple Reflex | TEST_FAILURE | inspect_test_failures | PASS (expected TEST_FAILURE) |
| Model-Based Reflex | TEST_FAILURE | inspect_test_failures | PASS (expected TEST_FAILURE) |
| Goal-Based | TEST_FAILURE | inspect_test_failures | PASS (expected TEST_FAILURE) |
| Utility-Based | TEST_FAILURE | inspect_test_failures | PASS (expected TEST_FAILURE) |
| Learning | TEST_FAILURE | inspect_test_failures | PASS (expected TEST_FAILURE) |

Likely cause (Utility-Based): Commit a1b2c3d ('Refactor discount calculation') changed code the failing tests exercise

## Scenario B: Build blocked by dependency conflict, with a flaky test nearby (critical, mixed signals)

| Agent | Category | Action | Category check |
|---|---|---|---|
| Simple Reflex | TEST_FAILURE | inspect_test_failures | PASS (documented misdiagnosis) (expected TEST_FAILURE) |
| Model-Based Reflex | TEST_FAILURE | rerun_failed_tests | PASS (documented misdiagnosis) (expected TEST_FAILURE) |
| Goal-Based | DEPENDENCY_ISSUE | check_dependency_pins | PASS (expected DEPENDENCY_ISSUE) |
| Utility-Based | DEPENDENCY_ISSUE | check_dependency_pins | PASS (expected DEPENDENCY_ISSUE) |
| Learning | DEPENDENCY_ISSUE | check_dependency_pins | PASS (expected DEPENDENCY_ISSUE) |

Likely cause (Utility-Based): Requested package version is unavailable or incompatible: pandas==2.4.0 (latest on index: 2.2.3)

## Scenario C: Tests pass, deployment health checks fail (post-release)

| Agent | Category | Action | Category check |
|---|---|---|---|
| Simple Reflex | DEPLOYMENT_HEALTH | inspect_deploy_health | PASS (expected DEPLOYMENT_HEALTH) |
| Model-Based Reflex | DEPLOYMENT_HEALTH | inspect_deploy_health | PASS (expected DEPLOYMENT_HEALTH) |
| Goal-Based | DEPLOYMENT_HEALTH | inspect_deploy_health | PASS (expected DEPLOYMENT_HEALTH) |
| Utility-Based | DEPLOYMENT_HEALTH | inspect_deploy_health | PASS (expected DEPLOYMENT_HEALTH) |
| Learning | DEPLOYMENT_HEALTH | inspect_deploy_health | PASS (expected DEPLOYMENT_HEALTH) |

Likely cause (Utility-Based): Release fails at startup in the target environment: KeyError: 'PAYMENT_API_URL' during startup

## Scenario D: Intermittent timeout in unrelated test (edge / ambiguous)

| Agent | Category | Action | Category check |
|---|---|---|---|
| Simple Reflex | TEST_FAILURE | inspect_test_failures | PASS (expected TEST_FAILURE) |
| Model-Based Reflex | TEST_FAILURE | rerun_failed_tests | PASS (expected TEST_FAILURE) |
| Goal-Based | TEST_FAILURE | inspect_test_failures | PASS (expected TEST_FAILURE) |
| Utility-Based | TEST_FAILURE | rerun_failed_tests | PASS (expected TEST_FAILURE) |
| Learning | TEST_FAILURE | inspect_test_failures | PASS (expected TEST_FAILURE) |

Likely cause (Utility-Based): Failure is unrelated to the recent change; likely a flaky/timing-sensitive test

## Learning agent experience update (scenario D)

- Before: `inspect_test_failures`
- Recorded 6 failures for `inspect_test_failures`
- After: `rerun_failed_tests`  -> decision changed: PASS

After-update reasoning: Score = evidence-based P(useful) x learned success rate (Laplace). Experience -> inspect_test_failures: 8S/8F (rate 50%); rerun_failed_tests: 1S/4F (rate 29%); check_dependency_pins: 6S/1F (rate 78%); inspect_deploy_health: 5S/2F (rate 67%); collect_more_info: 2S/3F (rate 43%). Candidates limited to evidence-supported category TEST_FAILURE (+ fallback). Scores: {'inspect_test_failures': 0.12, 'rerun_failed_tests': 0.137, 'collect_more_info': 0.086}. 'rerun_failed_tests' wins; its history is 1 successes / 4 failures (29%), which weakens the choice. Feedback on this recommendation updates these counts for next time.

**Total failures: 0**