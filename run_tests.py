"""Runs all agents on all scenarios, checks expectations, writes test_results.md.
Usage: python run_tests.py [--llm] [--model qwen3:8b]"""
import sys

from agents import classical_agents
from scenarios import EXPECTED_CATEGORY, EXPECTED_OVERRIDES, SCENARIOS

use_llm = "--llm" in sys.argv
model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "qwen3:8b"
out, failures = ["# Test Results", ""], 0

for sid, s in SCENARIOS.items():
    agents = classical_agents(learning_path=None)  # in-memory experience: tests never modify experience.json
    decisions = [a.decide(s) for a in agents]
    if use_llm:
        from llm_agent import run_llm_agent
        d = run_llm_agent(s, model)
        decisions.append(d)
        ok_tools = len(d.extra.get("tools_called", [])) >= 2
        out.append(f"LLM tools called in scenario {sid}: {d.extra.get('tools_called')} -> {'PASS' if ok_tools else 'FAIL'}")
        failures += not ok_tools
    out += [f"## Scenario {sid}: {s['title']}", "",
            "| Agent | Category | Action | Category check |", "|---|---|---|---|"]
    for d in decisions:
        exp = EXPECTED_OVERRIDES.get((sid, d.agent), EXPECTED_CATEGORY[sid])
        note = ' (documented misdiagnosis)' if (sid, d.agent) in EXPECTED_OVERRIDES else ''
        ok = d.category == exp
        failures += not ok
        out.append(f"| {d.agent} | {d.category} | {d.action} | {'PASS' if ok else 'FAIL'}{note} (expected {exp}) |")
    out += ["", f"Likely cause (Utility-Based): {decisions[3].cause}", ""]

# Learning agent: experience must change the decision
s = SCENARIOS["D"]
la = classical_agents(learning_path=None)[4]
before = la.decide(s)
for _ in range(6):
    la.record(before.action, False)
after = la.decide(s)
changed = before.action != after.action and after.category == before.category
failures += not changed
out += ["## Learning agent experience update (scenario D)", "",
        f"- Before: `{before.action}`", f"- Recorded 6 failures for `{before.action}`",
        f"- After: `{after.action}`  -> decision changed: {'PASS' if changed else 'FAIL'}", "",
        f"After-update reasoning: {after.reasoning}", ""]

out.append(f"**Total failures: {failures}**")
open("test_results.md", "w").write("\n".join(out))
print("\n".join(out))
sys.exit(1 if failures else 0)
