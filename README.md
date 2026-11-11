# Intelligent CI/CD Pipeline Failure Assistant

Agentic AI course assignment. Six agents (Simple Reflex, Model-Based Reflex, Goal-Based, Utility-Based, Learning, and an LLM agent using local Ollama tool calling) investigate the **same** failed-pipeline data and recommend the next troubleshooting step. The assistant **never changes code or deploys**.

## Project structure
| File | Purpose |
|---|---|
| `scenarios.py` | Scenarios A-D (one dict per scenario, passed unchanged to every agent) |
| `tools.py` | Read-only tools for the LLM: `get_pipeline_status`, `read_build_logs`, `get_test_results`, `get_recent_change_summary`, `get_dependency_info`, `get_deployment_health` |
| `agents.py` | The five classical agents + shared helpers |
| `llm_agent.py` | Ollama tool-calling agent (requires >= 2 distinct tool calls before answering) |
| `app.py` | Streamlit UI |
| `run_tests.py` | Runs all scenarios, writes `test_results.md` |
| `experience.json` | Created on first feedback click; stores the Learning agent's success/failure counts |

## Setup
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Install Ollama from https://ollama.com, then:
ollama pull qwen3:8b          # any tool-capable model works (qwen3, llama3.1, ...)
ollama serve                  # if not already running
```

## Run
```bash
streamlit run app.py                       # UI: choose scenario -> "Run all agents"
python run_tests.py                        # classical agents + learning-update test
python run_tests.py --llm --model qwen3:8b # also checks LLM category and >= 2 tool calls
```

## Scenarios
| ID | Type | Description | Expected category |
|---|---|---|---|
| A | Normal | Two cart discount tests fail after a refactor of `cart/pricing.py` | TEST_FAILURE |
| B | Critical / mixed signals | Build blocked: `pandas==2.4.0` unavailable and conflicts with `numpy<2.0` (error worded unusually), while a parallel job also reports a known flaky test failure | DEPENDENCY_ISSUE |
| C | Post-release | 120/120 tests pass, but `/healthz` returns 503; `PAYMENT_API_URL` env var missing | DEPLOYMENT_HEALTH |
| D | Edge / ambiguous | One timeout in a test unrelated to the change (README edit), with flaky history | TEST_FAILURE |

## How each agent works
- **Simple Reflex**: fixed condition-action rules on the current percept (log keywords, failed stage, failed test count). No memory.
- **Model-Based Reflex**: keeps internal state (last good commit, commits since, failure streak, flaky-test history) and uses it in its rules.
- **Goal-Based**: goal = a root-cause hypothesis supported by >= 2 independent evidence sources. Picks the best-supported hypothesis and takes step 1 of its plan.
- **Utility-Based**: `utility = P(useful) x 10 x severity - time cost - risk` for every action; highest wins.
- **Learning**: scores actions as `P(useful) x Laplace success rate`, using success/failure counts from `experience.json`. It explains the counts in its reasoning. The UI buttons record feedback, which changes future decisions (verified in `run_tests.py`).
- **LLM (Ollama)**: calls tools, then answers in JSON (category, evidence, cause, action, checklist, reasoning) grounded in the tool results. The UI shows every tool call and its result.

## Comparison (classical agents; actual results from `run_tests.py`)
| Scenario | Simple Reflex | Model-Based | Goal-Based | Utility | Learning |
|---|---|---|---|---|---|
| A | inspect_test_failures | inspect_test_failures | inspect_test_failures | inspect_test_failures | inspect_test_failures |
| B | inspect_test_failures (TEST_FAILURE) | rerun_failed_tests (TEST_FAILURE) | check_dependency_pins | check_dependency_pins | check_dependency_pins |
| C | inspect_deploy_health | inspect_deploy_health | inspect_deploy_health | inspect_deploy_health | inspect_deploy_health |
| D | inspect_test_failures | **rerun_failed_tests** | inspect_test_failures | **rerun_failed_tests** | inspect_test_failures |

(Add the LLM column after running with your Ollama model.)

### Why decisions differ
In A and C the evidence is unambiguous, so all agents agree. In **B** and **D** the evidence is mixed. In **D**: a test failed (suggesting "inspect"), but it is a known flaky test and the only commit was a README edit.
- Simple Reflex and Goal-Based see only "a test failed", so they inspect it. Neither uses flaky history or cost.
- Model-Based uses its internal state (flaky history, no overlapping files) and recommends a rerun.
- Utility-Based reaches the same rerun because P(useful) for inspecting drops when flakiness is likely, and a rerun has the higher expected utility.
- Learning chooses inspect because its seeded experience says reruns rarely resolved failures (1 success / 4 failures). After 6 recorded failures for inspect it switches to rerun, showing experience changing the decision.

### Scenario B (mixed signals)
The real cause is the dependency conflict, but the log wording does not match the keyword rule, and a flaky test failure is visible in the same run.
- **Simple Reflex** has no dependency keyword to fire on, so the next rule matches "a test failed" and it recommends `inspect_test_failures` (misdiagnosis).
- **Model-Based** also misses the dependency wording, but its flaky-test history makes it conclude the failure is flaky and recommend `rerun_failed_tests` (different action, still a misdiagnosis).
- **Goal-Based** compares evidence sources per hypothesis; the dependency hypothesis is better supported (dependencies + changes), so it picks `check_dependency_pins`.
- **Utility-Based** and **Learning** both weigh the evidence scores (dependency 3 vs test 1) and also pick `check_dependency_pins`.

These two misdiagnoses are intentional and are listed as `EXPECTED_OVERRIDES` in `scenarios.py`, so `run_tests.py` records them as documented limitations of rule-based agents.

## Screenshots (to add before submission)
Run the UI and capture one screenshot per scenario (A, B, C, plus D) showing the decision cards and comparison table. Also capture the LLM agent's "Tool calls" expander and the Learning agent's experience table. Save them in `screenshots/`.

## Test results
See `test_results.md` (generated by `run_tests.py`). Classical-agent tests pass (4 scenarios x 5 agents, plus the learning-update test). Re-run with `--llm` on your machine to include the LLM results.