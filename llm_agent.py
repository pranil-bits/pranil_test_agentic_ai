"""LLM-based agent: local Ollama model (e.g. qwen3) with tool calling. Read-only investigation."""
import inspect
import json
import re

from agents import ACTIONS, CATEGORIES, CHECKLISTS, Decision
from tools import make_tools

SYSTEM = f"""You are a CI/CD pipeline failure assistant. Investigate a failed pipeline using the tools.
Rules:
- Call AT LEAST TWO different tools and base every claim on the returned evidence.
- All tools take NO arguments. Call them with empty arguments.
- Never suggest changing code or deploying automatically; only recommend the next troubleshooting step.
- When done, reply with ONLY one JSON object (no markdown) with keys:
  failure_category (one of {CATEGORIES}),
  supporting_evidence (list of short strings quoting tool results),
  likely_cause (string),
  recommended_action_id (one of {list(ACTIONS)}),
  recommended_next_step (string),
  verification_checklist (list of strings),
  reasoning (string explaining how the evidence led to the decision)."""


def _parse(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else None


def _call_tool(fn, args):
    """Call a tool, dropping any arguments it does not accept (small models often invent them)."""
    allowed = set(inspect.signature(fn).parameters)
    clean = {k: v for k, v in (args or {}).items() if k in allowed}
    try:
        return fn(**clean)
    except Exception as e:
        return {"error": f"tool call failed: {e}"}


def run_llm_agent(s, model="qwen3:8b", max_turns=8):
    name = "LLM (Ollama)"
    try:
        import ollama
        tools = make_tools(s)
        fns = {f.__name__: f for f in tools}
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "The latest pipeline run failed. Investigate and recommend the next step."}]
        trace = []
        for _ in range(max_turns):
            m = ollama.chat(model=model, messages=msgs, tools=tools).message
            msgs.append(m)
            if m.tool_calls:
                for tc in m.tool_calls:
                    n = tc.function.name
                    out = _call_tool(fns[n], tc.function.arguments) if n in fns else {"error": "unknown tool"}
                    trace.append({"tool": n, "result": out})
                    msgs.append({"role": "tool", "tool_name": n, "content": json.dumps(out)})
                continue
            if len({t["tool"] for t in trace}) < 2:
                msgs.append({"role": "user", "content": "Call at least two different tools before answering."})
                continue
            data = _parse(m.content)
            if not data:
                msgs.append({"role": "user", "content": "Reply with ONLY the JSON object."})
                continue
            cat = data.get("failure_category", "UNKNOWN")
            cat = cat if cat in CATEGORIES else "UNKNOWN"
            act = data.get("recommended_action_id")
            act = act if act in ACTIONS else "collect_more_info"
            return Decision(name, cat, act, data.get("recommended_next_step", ACTIONS[act]["text"]),
                            data.get("likely_cause", ""), data.get("supporting_evidence", []),
                            data.get("reasoning", ""), data.get("verification_checklist") or CHECKLISTS[cat],
                            0.0, {"tool_trace": trace, "model": model,
                                  "tools_called": sorted({t["tool"] for t in trace})})
        raise RuntimeError("LLM did not produce a final answer within the turn limit")
    except Exception as e:  # Ollama not running, model missing, bad output...
        return Decision(name, "UNKNOWN", "collect_more_info", "LLM agent unavailable", f"Error: {e}", [],
                        f"Could not run model '{model}'. Is Ollama running and the model pulled?", [], 0.0,
                        {"error": str(e), "tool_trace": []})