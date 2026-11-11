"""Five classical agents for CI/CD failure triage.
All agents take the same scenario dict and return a Decision. None of them changes code or deploys."""
import copy
import json
import os
import re
from dataclasses import dataclass, field

CATEGORIES = ["TEST_FAILURE", "DEPENDENCY_ISSUE", "DEPLOYMENT_HEALTH"]

ACTIONS = {
    "inspect_test_failures": dict(cat="TEST_FAILURE", cost=1.5, risk=0.0,
        text="Open the failing tests and diff them against the recent change"),
    "rerun_failed_tests": dict(cat="TEST_FAILURE", cost=2.5, risk=0.0,
        text="Re-run only the failing test(s) in isolation 3x on the same commit to rule out flakiness"),
    "check_dependency_pins": dict(cat="DEPENDENCY_ISSUE", cost=1.5, risk=0.0,
        text="Verify the pinned versions exist on the package index and resolve together; compare with the last good lockfile"),
    "inspect_deploy_health": dict(cat="DEPLOYMENT_HEALTH", cost=2.0, risk=0.5,
        text="Read app startup logs and compare release config/env vars with the last healthy release"),
    "collect_more_info": dict(cat="UNKNOWN", cost=1.0, risk=0.0,
        text="Collect full logs and re-run the pipeline with debug logging"),
}

CHECKLISTS = {
    "TEST_FAILURE": ["Failing tests pass locally and in CI", "Full unit suite is green (no new failures)",
                     "Fix reviewed against the commit that introduced the change", "Pipeline re-run reaches deploy stage"],
    "DEPENDENCY_ISSUE": ["Pinned version exists on the index (pip index versions <pkg>)",
                         "Clean install succeeds with the lockfile", "Build and unit tests pass with resolved versions",
                         "No new conflicts reported by pip check"],
    "DEPLOYMENT_HEALTH": ["Required env vars/secrets exist in the target environment", "App starts without errors in startup logs",
                          "/healthz returns 200 on all instances", "Smoke test of the changed feature passes",
                          "Rollback plan confirmed before any re-release"],
    "UNKNOWN": ["Full logs collected", "Failure reproduced or ruled out", "Category assigned and re-triaged"],
}

PLANS = {  # goal-based agent: ordered sub-goals toward 'root cause confirmed'
    "TEST_FAILURE": [("inspect_test_failures", "Read failing test assertions and stack traces"),
                     (None, "Diff the changed files against the code the tests cover"),
                     (None, "Confirm cause by checking the test on the last green commit")],
    "DEPENDENCY_ISSUE": [("check_dependency_pins", "Check the unresolved package/version on the index"),
                         (None, "Compare requirements with the last good lockfile"),
                         (None, "Find the newest compatible version range")],
    "DEPLOYMENT_HEALTH": [("inspect_deploy_health", "Read startup/app logs behind the failing health check"),
                          (None, "Diff config/env requirements of this release with the last healthy one"),
                          (None, "Confirm missing or invalid settings in the target environment")],
}

DEP_PATTERN = re.compile(r"could not find a version|no matching distribution|resolutionimpossible", re.I)

SEED_EXPERIENCE = {  # historical outcomes of recommended actions (success / failure counts)
    "inspect_test_failures": {"success": 8, "failure": 2},
    "rerun_failed_tests": {"success": 1, "failure": 4},
    "check_dependency_pins": {"success": 6, "failure": 1},
    "inspect_deploy_health": {"success": 5, "failure": 2},
    "collect_more_info": {"success": 2, "failure": 3},
}
EXP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "experience.json")


@dataclass
class Decision:
    agent: str
    category: str
    action: str
    next_step: str
    cause: str
    evidence: list
    reasoning: str
    checklist: list
    confidence: float = 0.0
    extra: dict = field(default_factory=dict)


# ---------- shared helpers (feature extraction from the scenario) ----------
def changed_files(s):
    return [f for c in s["changes"] for f in c["files"]]


def signals(s):
    t, h, d = s["tests"], s["health"], s["dependencies"]
    files = changed_files(s)
    overlap = any(f["covers"] in files for f in t["failures"])
    flaky = bool(t["failures"]) and all(f["id"] in s["history"]["flaky_tests"] for f in t["failures"])
    dep = 3 * bool(DEP_PATTERN.search(s["logs"])) + 2 * bool(d["unresolved"]) \
        + 1 * any(f.endswith(("requirements.txt", ".lock", "pyproject.toml")) for f in files)
    test = (3 if t["failed"] else 0) + (2 if overlap else 0) - (2 if flaky and not overlap else 0)
    dep_ = 3 * bool(h["checked"] and (h["status_code"] or 0) >= 500) \
        + 2 * (s["pipeline"]["failed_stage"] == "deploy") \
        + 1 * any(("config" in f or ".env" in f or "settings" in f) for f in files)
    return {"scores": {"TEST_FAILURE": test, "DEPENDENCY_ISSUE": dep, "DEPLOYMENT_HEALTH": dep_},
            "flaky": flaky, "overlap": overlap}


def evidence_for(cat, s):
    t, h, d = s["tests"], s["health"], s["dependencies"]
    lines = s["logs"].splitlines()
    ev = []
    if cat == "TEST_FAILURE":
        ev.append(f"[tests] {t['failed']}/{t['total']} tests failed")
        ev += [f"[tests] {f['id']}: {f['error']}" for f in t["failures"]]
        for f in t["failures"]:
            for c in s["changes"]:
                if f["covers"] in c["files"]:
                    ev.append(f"[changes] {c['sha']} '{c['msg']}' modified {f['covers']} covered by the failing test")
        if signals(s)["flaky"]:
            ev.append("[history] failing test is in the flaky-test history")
    elif cat == "DEPENDENCY_ISSUE":
        ev += [f"[logs] {l}" for l in lines if DEP_PATTERN.search(l)][:2]
        ev += [f"[dependencies] unresolved: {u}" for u in d["unresolved"]]
        ev += [f"[dependencies] changed: {c}" for c in d["changed"]]
        ev += [f"[changes] {c['sha']} '{c['msg']}'" for c in s["changes"] if any("requirements" in f for f in c["files"])]
    elif cat == "DEPLOYMENT_HEALTH":
        if h["checked"]:
            ev.append(f"[health] status {h['status_code']} after {h['retries']} retries: {h['error']}")
        ev += [f"[logs] {l}" for l in lines if re.search(r"health check|keyerror|startup", l, re.I)][:2]
        if t["ran"] and not t["failed"]:
            ev.append(f"[tests] all {t['total']} tests passed, so the failure appeared only after release")
        ev += [f"[changes] {c['sha']} '{c['msg']}' touched config" for c in s["changes"]
               if any("config" in f or "settings" in f for f in c["files"])]
    return ev or ["[logs] no strong signal"]


def likely_cause(cat, s):
    sig = signals(s)
    if cat == "TEST_FAILURE":
        if sig["overlap"]:
            c = next(c for c in s["changes"] if any(f["covers"] in c["files"] for f in s["tests"]["failures"]))
            return f"Commit {c['sha']} ('{c['msg']}') changed code the failing tests exercise"
        if sig["flaky"]:
            return "Failure is unrelated to the recent change; likely a flaky/timing-sensitive test"
        return "Test failure with no clear link to recent changes"
    if cat == "DEPENDENCY_ISSUE":
        u = s["dependencies"]["unresolved"]
        return f"Requested package version is unavailable or incompatible: {u[0] if u else 'see logs'}"
    if cat == "DEPLOYMENT_HEALTH":
        return f"Release fails at startup in the target environment: {s['health']['error']}"
    return "Insufficient evidence to determine a cause"


def make(agent, action, s, reasoning, confidence, cat=None, extra=None):
    cat = cat or ACTIONS[action]["cat"]
    return Decision(agent, cat, action, ACTIONS[action]["text"], likely_cause(cat, s), evidence_for(cat, s),
                    reasoning, CHECKLISTS[cat], round(confidence, 2), extra or {})


def probs(sig):
    w = {c: max(v, 0) + 0.5 for c, v in sig["scores"].items()}
    t = sum(w.values())
    return {c: v / t for c, v in w.items()}


def p_useful(a, p, sig):
    cat = ACTIONS[a]["cat"]
    if a == "collect_more_info":
        return 0.2
    if a == "rerun_failed_tests":
        return p[cat] * (0.8 if sig["flaky"] else 0.25)
    if a == "inspect_test_failures":
        return p[cat] * (0.4 if sig["flaky"] else 0.9)
    return p[cat] * 0.9


def severity(s):
    return {"deploy": 1.5, "build": 1.2}.get(s["pipeline"]["failed_stage"], 1.0)


# ---------- 1. Simple reflex ----------
class SimpleReflexAgent:
    name = "Simple Reflex"

    def decide(self, s):
        log, stage = s["logs"].lower(), s["pipeline"]["failed_stage"]
        if DEP_PATTERN.search(log):
            rule, a = "IF log contains a version-resolution error THEN check dependency pins", "check_dependency_pins"
        elif stage == "deploy" or "health check" in log:
            rule, a = "IF deploy stage failed / health check in log THEN inspect deployment health", "inspect_deploy_health"
        elif s["tests"]["failed"] > 0:
            rule, a = "IF unit tests failed THEN inspect the failing tests", "inspect_test_failures"
        else:
            rule, a = "IF no rule matches THEN collect more information", "collect_more_info"
        return make(self.name, a, s, f"Condition-action rule fired on the CURRENT percept only (no memory/history): {rule}.", 0.6)


# ---------- 2. Model-based reflex ----------
class ModelBasedReflexAgent:
    name = "Model-Based Reflex"

    def __init__(self):
        self.state = {}

    def update_state(self, s):
        runs = s["history"]["recent_runs"]
        streak = 0
        for r in reversed(runs):
            if r == "fail":
                streak += 1
            else:
                break
        self.state = {"last_good": s["history"]["last_success_sha"],
                      "suspects": [c["sha"] for c in s["changes"]],
                      "flaky": set(s["history"]["flaky_tests"]),
                      "alternating": runs.count("fail") >= 2 and "pass" in runs[-3:],
                      "streak": streak, "overlap": signals(s)["overlap"]}

    def decide(self, s):
        self.update_state(s)
        st = self.state
        failing = {f["id"] for f in s["tests"]["failures"]}
        model = (f"Internal state: last good={st['last_good']}, commits since={st['suspects']}, "
                 f"fail streak={st['streak']}, known flaky={sorted(st['flaky']) or 'none'}.")
        if DEP_PATTERN.search(s["logs"]):
            a, why = "check_dependency_pins", "Resolution error and dependency files changed since the last good commit."
        elif s["pipeline"]["failed_stage"] == "deploy":
            a, why = "inspect_deploy_health", "Tests were green in the model, so the fault is environment/config after release."
        elif failing and failing <= st["flaky"] and not st["overlap"]:
            a, why = "rerun_failed_tests", "Failing test is in the flaky history, was passing/failing alternately, and no changed file affects it."
        else:
            a, why = "inspect_test_failures", "Failing tests overlap with files changed since the last good commit."
        return make(self.name, a, s, f"{model} {why}", 0.75, extra={"internal_state": {
            k: (sorted(v) if isinstance(v, set) else v) for k, v in st.items()}})


# ---------- 3. Goal-based ----------
class GoalBasedAgent:
    name = "Goal-Based"
    GOAL = "Identify a root-cause hypothesis supported by >=2 independent evidence sources, with a verification-ready next step."

    def decide(self, s):
        sig = signals(s)
        hyps = {c: evidence_for(c, s) for c in CATEGORIES}
        src = {c: len({e.split("]")[0] for e in ev}) if sig["scores"][c] > 0 else 0 for c, ev in hyps.items()}
        best = max(CATEGORIES, key=lambda c: (src[c], sig["scores"][c]))
        if src[best] == 0:
            return make(self.name, "collect_more_info", s, f"Goal: {self.GOAL} No hypothesis has evidence, so gather more data.", 0.3, "UNKNOWN")
        plan = PLANS[best]
        a = plan[0][0]
        steps = " -> ".join(f"({i + 1}) {t}" for i, (_, t) in enumerate(plan))
        met = "met" if src[best] >= 2 else "not yet met"
        r = (f"Goal: {self.GOAL} Evidence sources per hypothesis: {src}. Best hypothesis = {best} with {src[best]} sources "
             f"(evidence goal {met}). Plan: {steps}. Step 1 is the next action.")
        return make(self.name, a, s, r, min(0.4 + 0.15 * src[best], 0.9), extra={"plan": [t for _, t in plan]})


# ---------- 4. Utility-based ----------
class UtilityBasedAgent:
    name = "Utility-Based"

    def decide(self, s):
        sig = signals(s)
        p = probs(sig)
        sev = severity(s)
        rows = {}
        for a, m in ACTIONS.items():
            pu = p_useful(a, p, sig)
            rows[a] = round(pu * 10 * sev - m["cost"] - m["risk"], 2)
        best = max(rows, key=rows.get)
        table = ", ".join(f"{a}={u}" for a, u in sorted(rows.items(), key=lambda x: -x[1]))
        r = (f"Utility = P(useful) x 10 x severity({sev}) - time cost - risk. "
             f"P(category) = { {c: round(v, 2) for c, v in p.items()} }. Utilities: {table}. Highest utility wins.")
        return make(self.name, best, s, r, p[ACTIONS[best]["cat"]], extra={"utilities": rows})


# ---------- 5. Learning agent ----------
class LearningAgent:
    name = "Learning"

    def __init__(self, path=EXP_PATH):
        self.path = path
        self.exp = copy.deepcopy(SEED_EXPERIENCE)
        if path and os.path.exists(path):
            with open(path) as f:
                self.exp.update(json.load(f))

    def rate(self, a):
        e = self.exp[a]
        return (e["success"] + 1) / (e["success"] + e["failure"] + 2)  # Laplace smoothing

    def record(self, action, success):
        self.exp[action]["success" if success else "failure"] += 1
        if self.path:
            with open(self.path, "w") as f:
                json.dump(self.exp, f, indent=2)

    def decide(self, s):
        sig = signals(s)
        p = probs(sig)
        top = max(sig["scores"], key=sig["scores"].get)  # experience re-ranks actions only within the evidence-supported category
        vals = {a: round(p_useful(a, p, sig) * self.rate(a), 3) for a, m in ACTIONS.items()
                if m["cat"] == top or a == "collect_more_info"}
        best = max(vals, key=vals.get)
        e = self.exp[best]
        exp_txt = "; ".join(f"{a}: {x['success']}S/{x['failure']}F (rate {self.rate(a):.0%})" for a, x in self.exp.items())
        r = (f"Score = evidence-based P(useful) x learned success rate (Laplace). Experience -> {exp_txt}. "
             f"Candidates limited to evidence-supported category {top} (+ fallback). Scores: {vals}. '{best}' wins; its history is {e['success']} successes / {e['failure']} failures "
             f"({self.rate(best):.0%}), which {'supports' if self.rate(best) >= 0.5 else 'weakens'} the choice. "
             f"Feedback on this recommendation updates these counts for next time.")
        return make(self.name, best, s, r, self.rate(best), extra={"scores": vals, "experience": copy.deepcopy(self.exp)})


def classical_agents(learning_path=EXP_PATH):
    return [SimpleReflexAgent(), ModelBasedReflexAgent(), GoalBasedAgent(), UtilityBasedAgent(), LearningAgent(learning_path)]


AGENT_REASONS = {
    "Simple Reflex": "uses fixed condition-action rules on the current percept only, so it cannot see flaky history or weigh trade-offs.",
    "Model-Based Reflex": "keeps an internal model (last good commit, flaky history, failure streak), so it reacts to hidden state.",
    "Goal-Based": "plans toward a goal (root cause with >=2 evidence sources) and takes the first plan step, ignoring cost/experience.",
    "Utility-Based": "scores every action by expected usefulness, severity, time cost and risk, so cheap/safe actions can win.",
    "Learning": "weights evidence by past success/failure counts, so earlier outcomes can override the evidence-only choice.",
    "LLM (Ollama)": "reasons over tool results in natural language; its choice depends on which evidence it retrieves and how it interprets it.",
}
